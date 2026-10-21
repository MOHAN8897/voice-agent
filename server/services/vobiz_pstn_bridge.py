"""Vobiz media stream bridge — WebSocket audio streaming ↔ STT/Brain/TTS voice core."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect

from server.services.audio_transcode import (
    StreamingPcmResampler,
    alaw_to_pcm16,
    encode_mulaw_base64,
    mulaw_to_pcm16,
    pcm16_chunk_to_mulaw_frames,
    pcm16_to_alaw,
    pcm16_to_mulaw,
)
from server.services.pstn_debug import log_pstn, mark
from server.services.pstn_media_flow import CallMediaConfig, new_ws_id, pstn_media_flow
from server.services.pstn_playback import EstimatedPlaybackTracker
from server.services.pstn_voice_core import pstn_call_options
from server.services.pstn_voice_flow import create_pstn_voice_loop
from server.services.vobiz_client import (
    VOBIZ_DEFAULT_CODEC,
    VOBIZ_DEFAULT_SAMPLE_RATE,
    vobiz_call_registry,
)

if TYPE_CHECKING:
    from server.services.pstn_prewarm import PstnPrewarmBundle

logger = logging.getLogger(__name__)

active_vobiz_bridges: dict[str, "VobizPstnBridge"] = {}
_vobiz_admission_lock = asyncio.Lock()


class VobizPstnBridge:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.call_uuid: str | None = None
        self.stream_id: str | None = None
        self.call_id: str | None = None
        self.agent_id: str | None = None
        self.tier: str | None = None
        self.session_id: str = "pstn"
        self.caller_id: str | None = None
        self._called_id: str | None = None
        self._voice = None
        self._playback: EstimatedPlaybackTracker | None = None
        self._closed = False
        self._wire_sample_rate = VOBIZ_DEFAULT_SAMPLE_RATE
        self._wire_codec = VOBIZ_DEFAULT_CODEC
        self._media_frames_in = 0
        self._media_frames_out = 0
        self.ws_id = new_ws_id()
        self._configured_media = CallMediaConfig(
            codec="L16",
            sample_rate=16000,
            channels=1,
        )
        self._negotiated_media = self._configured_media
        self._ws_send_lock = asyncio.Lock()
        self._send_wire_lock = asyncio.Lock()
        self._hangup_lock = asyncio.Lock()
        self._checkpoint_sequence = 0
        self._pending_checkpoint: str | None = None
        self._token_meta: dict[str, Any] = {}
        self._start_handled = False
        self._owns_call = False
        self._cleanup_done = False
        self._prewarm_bundle = None
        self._early_greeting_task: asyncio.Task | None = None
        self._stream_started_at: float | None = None
        self._inbound_greeting: str | None = None

    async def run(self, *, agent_id: str | None, tier: str | None, token_meta: dict[str, Any] | None) -> None:
        self._token_meta = dict(token_meta or {})
        self._start_voice_task: asyncio.Task | None = None
        self.agent_id = agent_id or self._token_meta.get("agent_id")
        self.tier = tier or self._token_meta.get("tier")
        exit_reason = "media_disconnected"
        # Track consecutive timeouts for keep-alive logic.
        _consecutive_timeouts = 0
        # Wait up to 120s for next media/event frame.
        _RECV_TIMEOUT_BEFORE_START = 90.0
        _RECV_TIMEOUT_AFTER_START = 120.0
        _MAX_CONSECUTIVE_TIMEOUTS = 3
        try:
            while not self._closed:
                recv_timeout = _RECV_TIMEOUT_BEFORE_START if not self._start_handled else _RECV_TIMEOUT_AFTER_START
                try:
                    message = await asyncio.wait_for(self.ws.receive(), timeout=recv_timeout)
                    _consecutive_timeouts = 0  # reset on successful receive
                except asyncio.TimeoutError:
                    if not self._start_handled:
                        logger.warning("[VOBIZ] WS timed out before start event")
                        exit_reason = "start_timeout"
                        break
                    _consecutive_timeouts += 1
                    if _consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
                        logger.warning(
                            "[VOBIZ] %d consecutive recv timeouts (%.0fs each) on call %s — treating as dead session",
                            _consecutive_timeouts,
                            _RECV_TIMEOUT_AFTER_START,
                            self.call_uuid,
                        )
                        exit_reason = "session_timeout"
                        break
                    log_pstn(
                        "vobiz.ws.keepalive",
                        call_uuid=self.call_uuid,
                        consecutive=_consecutive_timeouts,
                        timeout_s=_RECV_TIMEOUT_AFTER_START,
                    )
                    try:
                        async with self._ws_send_lock:
                            if not self._closed:
                                await self.ws.send_text(json.dumps({"event": "ping"}))
                    except (WebSocketDisconnect, RuntimeError):
                        exit_reason = "client_disconnected"
                        break
                    except Exception as ping_exc:
                        logger.warning("[VOBIZ] keep-alive ping non-fatal notice: %s", ping_exc)
                    continue
                except (WebSocketDisconnect, RuntimeError):
                    exit_reason = "client_disconnected"
                    break

                if message.get("type") == "websocket.disconnect":
                    exit_reason = "client_disconnected"
                    break

                text = message.get("text")
                if not text:
                    continue

                try:
                    data = json.loads(text)
                except Exception:
                    continue

                if not isinstance(data, dict):
                    continue

                event = str(data.get("event") or data.get("type") or "").lower()

                if event == "start":
                    if self._start_handled:
                        continue
                    self._start_handled = True
                    try:
                        await self._on_start(data)
                    except Exception:
                        self._start_handled = False
                        raise
                elif event == "media":
                    await self._on_media(data)
                elif event == "playedstream":
                    self._on_played_stream(data)
                elif event == "clearedaudio":
                    # The estimate was cleared when clearAudio was sent. A late
                    # acknowledgement must not erase a newer response's audio.
                    pass
                elif event == "pong":
                    pass
                elif event in ("stop", "hangup"):
                    logger.info("[VOBIZ] stream stop received")
                    exit_reason = "provider_stop"
                    break
        except Exception as exc:
            # A failed media leg must be cleaned up and diagnosed per call.
            # Provider payloads/URLs and exception text can contain secrets.
            exit_reason = "media_error"
            log_pstn("vobiz.media_failed", call_id=self.call_id, error_type=type(exc).__name__)
        finally:
            try:
                await asyncio.shield(self._cleanup(exit_reason))
            except asyncio.CancelledError:
                await self._cleanup(exit_reason)
                raise

    async def _on_start(self, ev: dict[str, Any]) -> None:
        self._stream_started_at = time.monotonic()
        start = ev.get("start") or ev
        started_call = str(
            start.get("callId") or start.get("callUUID") or start.get("call_uuid")
            or ev.get("callId") or ev.get("callUUID") or ev.get("call_uuid") or ""
        )
        bound_call = str(self._token_meta.get("call_uuid") or "")
        if started_call and bound_call and not bound_call.startswith("vobiz-") and started_call != bound_call:
            raise ValueError("Media start does not match the authorized call")
        self.call_uuid = started_call or bound_call or str(uuid.uuid4())
        self.stream_id = str(start.get("streamId") or start.get("stream_id") or ev.get("streamId") or ev.get("stream_id") or "")

        self.caller_id = str(start.get("from") or start.get("caller") or self._token_meta.get("from_number") or self._token_meta.get("from") or "")
        self._called_id = str(start.get("to") or start.get("called") or self._token_meta.get("to_number") or self._token_meta.get("to") or "")

        request_uuid = str(self._token_meta.get("request_uuid") or "")
        outbound_id = str(self._token_meta.get("outbound_id") or "")

        media = start.get("mediaFormat") or start.get("media_format") or {}
        raw_codec = str(media.get("encoding") or media.get("codec") or VOBIZ_DEFAULT_CODEC).lower()
        sr = media.get("sampleRate") or media.get("sample_rate") or media.get("rate")
        if "l16" in raw_codec or "linear" in raw_codec or "pcm" in raw_codec:
            self._wire_codec = "linear16"
            self._wire_sample_rate = int(sr) if sr else 16000
            flow_codec = "L16"
        elif "alaw" in raw_codec or "pcma" in raw_codec:
            self._wire_codec = "alaw"
            self._wire_sample_rate = int(sr) if sr else 8000
            flow_codec = "PCMA"
        elif "mulaw" in raw_codec or "pcmu" in raw_codec or "ulaw" in raw_codec:
            self._wire_codec = "mulaw"
            self._wire_sample_rate = int(sr) if sr else 8000
            flow_codec = "PCMU"
        else:
            self._wire_codec = VOBIZ_DEFAULT_CODEC
            self._wire_sample_rate = int(sr) if sr else VOBIZ_DEFAULT_SAMPLE_RATE
            flow_codec = "L16" if self._wire_codec == "linear16" else "PCMU"

        if self._wire_codec in {"mulaw", "alaw"} and self._wire_sample_rate != 8000:
            raise ValueError("Vobiz G.711 media must use an 8 kHz sample rate")

        self._negotiated_media = CallMediaConfig(
            codec=flow_codec,
            sample_rate=self._wire_sample_rate,
            channels=1,
        )

        from server.config.env import get_settings

        max_calls = max(1, int(getattr(get_settings(), "vobiz_max_concurrent_calls", 50) or 50))
        async with _vobiz_admission_lock:
            active_count = len({id(bridge) for bridge in active_vobiz_bridges.values()})
            if active_count >= max_calls:
                log_pstn("admission.rejected", provider="vobiz", active=active_count, max=max_calls)
                raise RuntimeError(f"Vobiz concurrent call limit reached ({max_calls})")
            active_vobiz_bridges[self.call_uuid or self.ws_id] = self
            if request_uuid:
                active_vobiz_bridges[request_uuid] = self
            if outbound_id:
                active_vobiz_bridges[outbound_id] = self
            active_vobiz_bridges[self.ws_id] = self
            self._owns_call = True

        # The socket token and distributed admission were already checked by
        # vobiz_stream_ws. Send cached audio before post-answer DB/registry work.
        prewarm = None
        if self.agent_id and self._token_meta.get("direction") == "outbound":
            prewarm = await self._claim_prepared_opening((outbound_id, request_uuid))
            if prewarm:
                if prewarm.greeting_wire_frames:
                    from server.services.audio_transcode import transcode_audio_frames

                    # Voice loops emit L16 for linear media and PCMU for G.711.
                    # Convert the cached greeting to that exact source format;
                    # _send_agent_wire handles any PCMU→PCMA carrier conversion.
                    target_codec = "linear16" if self._wire_codec == "linear16" else "mulaw"
                    target_rate = self._wire_sample_rate if target_codec == "linear16" else 8000
                    prewarm.greeting_wire_frames = transcode_audio_frames(
                        prewarm.greeting_wire_frames,
                        source_codec=prewarm.greeting_codec,
                        source_rate=prewarm.greeting_sample_rate,
                        target_codec=target_codec,
                        target_rate=target_rate,
                    )
                    if not prewarm.greeting_wire_frames:
                        raise RuntimeError("Prepared opening audio could not be adapted to negotiated media")
                    prewarm.greeting_codec = target_codec
                    prewarm.greeting_sample_rate = target_rate
                from server.realtime.models import is_gemini_live_voice_model
                from server.realtime.voice_manager import realtime_voice_manager

                adapter = realtime_voice_manager.get(prewarm.realtime_key)
                if (is_gemini_live_voice_model(prewarm.greeting_model or "")
                        and prewarm.greeting_wire_frames and adapter is not None
                        and adapter.is_open() and getattr(adapter, "opening_generated_on_session", False)):
                    self._playback = EstimatedPlaybackTracker(frame_ms=20.0)
                    self._early_greeting_task = asyncio.create_task(
                        self._send_prepared_opening(prewarm.greeting_wire_frames),
                        name=f"vobiz-opening-{self.call_uuid}",
                    )

        await asyncio.to_thread(vobiz_call_registry.upsert,
            self.call_uuid,
            {"stream_connected": True, "stream_failed": False, "stream_state": "connected"},
        )
        if request_uuid and request_uuid != self.call_uuid:
            await asyncio.to_thread(vobiz_call_registry.alias, request_uuid, self.call_uuid)
        if outbound_id and outbound_id != self.call_uuid:
            await asyncio.to_thread(vobiz_call_registry.alias, outbound_id, self.call_uuid)

        pstn_media_flow.start(
            external_id=self.call_uuid or self.ws_id,
            ws_id=self.ws_id,
            configured=self._configured_media,
        )
        pstn_media_flow.negotiate(self.call_uuid or self.ws_id, self._negotiated_media)

        # 1. Resolve local metadata and options from registry / tokens
        local = await asyncio.to_thread(vobiz_call_registry.get, self.call_uuid or "") or {}
        if not local and request_uuid:
            local = await asyncio.to_thread(vobiz_call_registry.get, request_uuid) or {}
        if not local and outbound_id:
            local = await asyncio.to_thread(vobiz_call_registry.get, outbound_id) or {}

        self.agent_id = self.agent_id or local.get("agent_id") or self._token_meta.get("agent_id")
        self.tier = self.tier or local.get("tier") or self._token_meta.get("tier")
        self._inbound_greeting = local.get("greeting")

        call_opts_dict = {
            "agent_id": self.agent_id,
            "tier": self.tier,
            "direction": str(self._token_meta.get("direction") or local.get("direction") or "outbound"),
            "caller_phone": self.caller_id,
            "called_phone": self._called_id,
            "source_session_id": self._token_meta.get("source_session_id") or local.get("source_session_id"),
            "language": self._token_meta.get("language") or local.get("language"),
            "stack_override": self._token_meta.get("stack_override") or local.get("stack_override"),
        }
        pstn_opts = pstn_call_options(call_opts_dict)

        # 2. Prewarm adoption
        if prewarm is None:
            prewarm = await self._claim_prepared_opening(
                (outbound_id, request_uuid, local.get("outbound_id"), local.get("request_uuid")),
            )
        if prewarm is None and self._token_meta.get("prewarm_required"):
            # A lost/misrouted prepared session must not silently become a
            # second cold Gemini request on an already billable answered call.
            raise RuntimeError("Prepared phone session is unavailable")

        # 3. Start agent session in lifecycle service
        if self.agent_id:
            from server.call.call_lifecycle_service import call_lifecycle_service

            agent_lang = pstn_opts.get("language")
            started = await call_lifecycle_service.start(
                agent_id=self.agent_id,
                contact=self._token_meta.get("contact") or local.get("contact"),
                campaign_id=(self._token_meta.get("contact") or local.get("contact") or {}).get("campaign_id"),
                session_id=f"pstn-vobiz-{self.call_uuid}",
                config_session_id=pstn_opts.get("config_session_id"),
                channel="pstn",
                direction=str(call_opts_dict["direction"]),
                tier=self.tier,
                caller_id=self.caller_id,
                stack_override=pstn_opts.get("stack_override"),
                language=str(agent_lang) if agent_lang else None,
                realtime_prewarm_key=prewarm.realtime_key if prewarm else None,
                prepared_brain=(prewarm.compiled_brain_version, prewarm.compiled_brain_text)
                if prewarm and prewarm.compiled_brain_text else None,
            )
            self.call_id = started["call_id"]
            self.session_id = started["session_id"]
            admission_key = self._token_meta.get("admission_key") or local.get("admission_key")
            admission_tenant_id = self._token_meta.get("admission_tenant_id") or local.get("admission_tenant_id")
            if admission_key and admission_tenant_id:
                from server.services.saas.call_admission import provider_event
                await provider_event(tenant_id=uuid.UUID(str(admission_tenant_id)), key=admission_key,
                                     status="answered", call_id=self.call_id)
            from server.call.billing_timing import mark_call_connected
            from server.call.call_ledger import call_ledger

            mark_call_connected(self.call_id, self._token_meta.get("answered_at") or local.get("answered_at"))
            billing_meta = call_ledger.read_meta(self.call_id)
            billing_meta.update({"telephony_provider": "vobiz", "vobiz_call_uuid": self.call_uuid})
            for key in ("tenant_id", "vobiz_account_scope", "vobiz_account_tenant_id"):
                billing_meta[key] = self._token_meta.get(key) or local.get(key)
            call_ledger.write_meta(self.call_id, billing_meta)
            await asyncio.to_thread(vobiz_call_registry.upsert,
                self.call_uuid,
                {"internal_call_id": self.call_id, "agent_id": self.agent_id, "status": "streaming"},
            )

        # 4. Create playback tracker and voice loop
        self._playback = self._playback or EstimatedPlaybackTracker(frame_ms=20.0)
        self._voice = create_pstn_voice_loop(
            stack_override=pstn_opts.get("stack_override"),
            session_id=self.session_id,
            call_id=self.call_id or self.call_uuid,
            on_agent_wire=self._send_agent_wire,
            sample_rate=self._wire_sample_rate,
            tts_session_id=pstn_opts.get("tts_session_id"),
            config_session_id=pstn_opts.get("config_session_id"),
            tts_output_codec="linear16" if self._wire_codec == "linear16" else "mulaw",
            is_agent_audio_active=self._playback.is_active,
            playback=self._playback,
        )
        self._voice.set_barge_handler(self._barge_in)
        self._voice.set_hangup_handler(self.hangup)
        if hasattr(self._voice, "set_turn_audio_done_handler"):
            self._voice.set_turn_audio_done_handler(self._mark_turn_end)
        self._start_voice_task = asyncio.create_task(self._start_voice_loop())

        logger.info(
            "[VOBIZ] Bridge connected call_uuid=%s call_id=%s codec=%s rate=%s prewarm=%s",
            self.call_uuid,
            self.call_id,
            self._wire_codec,
            self._wire_sample_rate,
            bool(prewarm),
        )

    async def _claim_prepared_opening(self, fallback_ids: tuple[str | None, ...]) -> PstnPrewarmBundle | None:
        from server.services.pstn_prewarm import _destroy_realtime, take_prewarm_for_answer

        bundle = await take_prewarm_for_answer(
            "vobiz", self.call_uuid or "", fallback_external_ids=fallback_ids,
        )
        if bundle and bundle.agent_id != self.agent_id:
            await _destroy_realtime(bundle.realtime_key)
            raise RuntimeError("Prepared agent does not match the connected call")
        self._prewarm_bundle = bundle
        if bundle and self._token_meta.get("prewarm_required"):
            from server.realtime.models import is_gemini_live_voice_model
            from server.realtime.voice_manager import realtime_voice_manager

            if is_gemini_live_voice_model(bundle.greeting_model or ""):
                adapter = realtime_voice_manager.get(bundle.realtime_key)
                if adapter is None or not adapter.is_open():
                    raise RuntimeError("Prepared Gemini session is no longer connected")
        return bundle

    async def _send_prepared_opening(self, frames: list[bytes]) -> None:
        for frame in frames:
            if self._closed:
                return
            await self._send_agent_wire(frame)

    async def _start_voice_loop(self) -> None:
        if not self._voice:
            return
        try:
            prewarm = getattr(self, "_prewarm_bundle", None)
            inbound_greeting = getattr(self, "_inbound_greeting", None)
            greeting_text = inbound_greeting or ((prewarm.greeting_transcript or prewarm.greeting_text) if prewarm else None)
            greeting_frames = None if inbound_greeting else (prewarm.greeting_wire_frames if prewarm else None)
            from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
            greeting_options = {"play_greeting": bool(self.call_id or self.agent_id),
                                "greeting_wire_frames": greeting_frames, "greeting_text": greeting_text}
            if isinstance(self._voice, PstnRealtimeVoiceLoop):
                greeting_options["immediate_greeting"] = True
                if self._early_greeting_task is not None:
                    await asyncio.wait_for(asyncio.shield(self._early_greeting_task), timeout=15.0)
                    from server.realtime.voice_manager import realtime_voice_manager
                    adopted = realtime_voice_manager.get(self.call_id)
                    if adopted is None or not adopted.is_open() or not getattr(adopted, "opening_generated_on_session", False):
                        raise RuntimeError("Prepared Gemini session was not adopted")
                    greeting_options["greeting_already_sent"] = True
            await asyncio.wait_for(self._voice.start_call(**greeting_options), timeout=60.0)
            if prewarm and self.call_id:
                from server.services.pstn_prewarm import record_bundle_greeting_usage

                await record_bundle_greeting_usage(self.call_id, prewarm)
        except Exception as exc:
            logger.exception("[VOBIZ] Voice loop greeting start failed: %s", exc)
            # A failed startup must not leave a billable, silent connected call.
            await self.hangup(reason="voice_start_failed")

    async def _on_media(self, ev: dict[str, Any]) -> None:
        if not self._voice or self._closed:
            return
        media = ev.get("media") or {}
        payload_b64 = media.get("payload") or media.get("chunk") or ev.get("payload")
        if not payload_b64:
            return

        try:
            raw_bytes = base64.b64decode(payload_b64)
        except Exception:
            return

        self._media_frames_in += 1
        if self._media_frames_in == 1:
            log_pstn("media.in.first", provider="vobiz", call_uuid=self.call_uuid, bytes=len(raw_bytes))

        # Transcode wire format to PCM16 for our voice core
        if self._wire_codec == "mulaw":
            pcm = mulaw_to_pcm16(raw_bytes, target_rate=self._wire_sample_rate)
        elif self._wire_codec == "alaw":
            pcm = alaw_to_pcm16(raw_bytes, target_rate=self._wire_sample_rate)
        else:
            pcm = raw_bytes

        await self._voice.feed_user_pcm16(pcm)

    async def _send_agent_wire(self, wire: bytes) -> None:
        """Paces synthesized agent audio frames back to caller via Vobiz playAudio events."""
        if self._closed or not wire:
            return

        async with self._send_wire_lock:
            generation_id = self._voice.current_generation_id if self._voice else None
            playback = getattr(self, "_playback", None)
            if playback is not None and not playback.is_generation_valid(generation_id):
                return
            # An acknowledgement for the previous turn cannot drain this audio.
            self._pending_checkpoint = None

            if self._wire_codec == "linear16":
                # Match the negotiated rate used by the voice loop's resampler.
                frame_bytes = self._wire_sample_rate * 2 // 50
                frames = [wire[i : i + frame_bytes] for i in range(0, len(wire), frame_bytes)]
                content_type = "audio/x-l16"
                sample_rate = self._wire_sample_rate
            else:
                # Voice loops emit PCMU for both G.711 carrier formats; encode
                # the carrier's requested A-law explicitly instead of relabeling.
                frames = [wire[i : i + 160] for i in range(0, len(wire), 160) if wire[i : i + 160]]
                if self._wire_codec == "alaw":
                    from server.services.audio_transcode import convert_g711

                    frames = [convert_g711(frame, "PCMU", "PCMA") for frame in frames]
                    content_type = "audio/x-alaw;rate=8000"
                else:
                    content_type = "audio/x-mulaw;rate=8000"
                sample_rate = 8000

            # Register queued frames in playback tracker so farewell / hangup logic knows audio is playing
            if playback is not None and hasattr(playback, "note_sent_frames"):
                playback.note_sent_frames(len(frames))

            first_out = self._media_frames_out == 0
            next_frame_time = time.monotonic()
            for i, frame in enumerate(frames):
                if self._closed:
                    return
                if playback is not None and not playback.is_generation_valid(generation_id):
                    return
                b64_audio = base64.b64encode(frame).decode("ascii")
                msg: dict[str, Any] = {
                    "event": "playAudio",
                    "media": {
                        "contentType": content_type,
                        "sampleRate": sample_rate,
                        "payload": b64_audio,
                    },
                }
                if self.stream_id:
                    msg["streamId"] = self.stream_id

                async with self._ws_send_lock:
                    if not self._closed:
                        await self.ws.send_text(json.dumps(msg))

                if i + 1 < len(frames):
                    next_frame_time += 0.02
                    delay = next_frame_time - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)

            self._media_frames_out += len(frames)
            if first_out:
                log_pstn("media.out.first", provider="vobiz", call_uuid=self.call_uuid, frames=len(frames),
                         stream_to_audio_ms=int((time.monotonic() - self._stream_started_at) * 1000)
                         if self._stream_started_at is not None else None)

    async def _mark_turn_end(self) -> None:
        """Mark completion of an agent turn with checkpoint event."""
        if not self.stream_id or self._closed:
            return
        try:
            async with self._ws_send_lock:
                if not self._closed:
                    self._checkpoint_sequence += 1
                    self._pending_checkpoint = f"turn-{self._checkpoint_sequence}"
                    await self.ws.send_text(
                        json.dumps(
                            {
                                "event": "checkpoint",
                                "streamId": self.stream_id,
                                "name": self._pending_checkpoint,
                            }
                        )
                    )
        except Exception:
            pass

    def _on_played_stream(self, event: dict[str, Any]) -> None:
        if not self._pending_checkpoint or event.get("name") != self._pending_checkpoint:
            return
        if event.get("streamId") and event["streamId"] != self.stream_id:
            return
        self._pending_checkpoint = None
        if self._playback:
            self._playback.clear()
        if self._voice and hasattr(self._voice, "on_playback_drained"):
            self._voice.on_playback_drained()

    async def _barge_in(self) -> None:
        """Interruption detected: clear playback tracker and tell Vobiz to drop buffered audio."""
        self._pending_checkpoint = None
        generation_id = self._voice.current_generation_id if self._voice else None
        playback = getattr(self, "_playback", None)
        if playback is not None:
            playback.invalidate_generation(generation_id)
            drained = playback.clear()
            log_pstn(
                "PROVIDER_CLEAR",
                provider="vobiz",
                call_uuid=self.call_uuid,
                frames=drained,
                generation_id=generation_id,
            )

        msg: dict[str, Any] = {"event": "clearAudio"}
        if self.stream_id:
            msg["streamId"] = self.stream_id
        try:
            async with self._ws_send_lock:
                if not self._closed:
                    await self.ws.send_text(json.dumps(msg))
        except Exception:
            pass

    async def hangup(self, reason: str = "agent_ended") -> None:
        """Bound carrier teardown; closing the socket also advances XML to Hangup."""
        async with self._hangup_lock:
            if self._closed:
                return
            self._closed = True
            disconnected = False
            try:
                log_pstn("vobiz.hangup.initiated", call_uuid=self.call_uuid, reason=reason)
                target_uuid = self.call_uuid
                local = await asyncio.to_thread(vobiz_call_registry.get, self.call_uuid or "") or {}
                if target_uuid and target_uuid.startswith("vobiz-"):
                    target_uuid = local.get("call_uuid") or local.get("request_uuid") or target_uuid
                try:
                    from server.services.saas.voice_kyc_service import vobiz_client_for_call
                    from server.services.vobiz_client import vobiz_enabled
                    meta = {**local, **self._token_meta}
                    client = await vobiz_client_for_call(meta) if meta.get("vobiz_account_scope") == "tenant" or vobiz_enabled() else None
                    if target_uuid and client:
                        result = await asyncio.wait_for(client.hangup_call(target_uuid), timeout=5.0)
                        disconnected = True
                        # A successful carrier disconnect must release the durable
                        # admission even if its HTTP callback never reaches us.
                        from server.services.saas.call_admission import provider_event
                        tenant_id = self._token_meta.get("admission_tenant_id") or local.get("admission_tenant_id")
                        if tenant_id and (not result.get("already_ended") or result.get("status") == 404):
                            await asyncio.wait_for(provider_event(tenant_id=uuid.UUID(str(tenant_id)),
                                key=self._token_meta.get("admission_key") or local.get("admission_key"),
                                carrier_ids=(target_uuid, self.call_uuid), status="ended"), timeout=2)
                except Exception as exc:
                    log_pstn("vobiz.hangup.api_failed", call_uuid=target_uuid, error=type(exc).__name__)
                finally:
                    try:
                        await asyncio.wait_for(self.ws.close(), timeout=2.0)
                        disconnected = True
                    except Exception as exc:
                        log_pstn("vobiz.hangup.stream_failed", call_uuid=target_uuid, error=type(exc).__name__)
                if not disconnected:
                    raise RuntimeError("Carrier and media disconnect both failed")
            finally:
                # The voice-loop watchdog can retry an unsuccessful disconnect.
                self._closed = disconnected

    async def _cleanup(self, reason: str) -> None:
        if self._cleanup_done:
            return
        self._cleanup_done = True
        self._closed = True
        from server.call.billing_timing import mark_call_disconnected
        mark_call_disconnected(self.call_id)
        if self.call_id:
            from server.call.call_ledger import call_ledger
            try:
                meta = call_ledger.read_meta(self.call_id) or {}
                meta["media_disconnect"] = {
                    "reason": reason,
                    "frames_in": self._media_frames_in,
                    "frames_out": self._media_frames_out,
                }
                call_ledger.write_meta(self.call_id, meta)
            except Exception as exc:
                log_pstn("vobiz.disconnect_diagnostics_failed", error_type=type(exc).__name__)

        startup = getattr(self, "_start_voice_task", None)
        if startup and startup is not asyncio.current_task() and not startup.done():
            startup.cancel()
            await asyncio.gather(startup, return_exceptions=True)
        opening = self._early_greeting_task
        if opening:
            if not opening.done():
                opening.cancel()
            await asyncio.gather(opening, return_exceptions=True)
        if self._prewarm_bundle:
            from server.services.pstn_prewarm import _destroy_realtime
            await _destroy_realtime(self._prewarm_bundle.realtime_key)

        if self._voice:
            try:
                await self._voice.close()
            except Exception:
                pass

        if self.call_id:
            from server.call.call_lifecycle_service import call_lifecycle_service

            try:
                # An unknown reason is normalized to user_stop, which previously
                # made broken media connections look like deliberate hangups.
                lifecycle_reason = {
                    "provider_stop": "pstn_hangup", "media_error": "provider_failure",
                    "call_hangup_notified": "pstn_hangup",
                    "session_timeout": "timeout", "start_timeout": "timeout",
                }.get(reason, "ws_disconnect")
                await call_lifecycle_service.end(self.call_id, reason=lifecycle_reason)
            except Exception:
                pass

        if self._owns_call:
            for k in (
                self.call_uuid,
                self.ws_id,
                self._token_meta.get("request_uuid"),
                self._token_meta.get("outbound_id"),
            ):
                if k:
                    if active_vobiz_bridges.get(str(k)) is self:
                        active_vobiz_bridges.pop(str(k), None)

        await asyncio.to_thread(vobiz_call_registry.upsert,
            self.call_uuid,
            {
                "ended": True,
                "stream_state": "closed",
                "exit_reason": reason,
                "media_frames_in": self._media_frames_in,
                "media_frames_out": self._media_frames_out,
                "bidirectional_ok": self._media_frames_in > 0 and self._media_frames_out > 0,
            },
        )
        pstn_media_flow.finish(self.call_uuid or self.ws_id)
        try:
            await self.ws.close()
        except Exception:
            pass
        logger.info(
            "[VOBIZ] Bridge closed call=%s reason=%s in=%d out=%d",
            self.call_uuid,
            reason,
            self._media_frames_in,
            self._media_frames_out,
        )
