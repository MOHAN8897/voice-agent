"""Telnyx media stream bridge — L16 RTP over WebSocket ↔ STT/Brain/TTS."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from server.services.audio_transcode import (
    StreamingPcmResampler,
    alaw_to_pcm16,
    chunk_mulaw_frames,
    convert_g711,
    g711_dbfs,
    mulaw_to_pcm16,
    pcm16_chunk_to_mulaw_frames,
    pcm16_to_mulaw,
)
from server.services.pstn_debug import log_pstn, log_pstn_summary, mark
from server.services.pstn_media_flow import CallMediaConfig, new_ws_id, pstn_media_flow
from server.services.pstn_voice_core import (
    PstnVoiceLoop,
    pstn_call_options,
)
from server.services.telnyx_client import TELNYX_RTP_CODEC, TELNYX_RTP_SAMPLE_RATE
from server.utils.logger import log_tts, log_ws

logger = logging.getLogger(__name__)

# Telnyx L16 wire @ 16 kHz — matches Sarvam linear16 and avoids G.711 transcoding.
_WIRE_SAMPLE_RATE = TELNYX_RTP_SAMPLE_RATE
MAX_AUDIO_QUEUE_FRAMES = 50  # ~1 s at 20 ms/frame — absorb bursts without long barge lag.
active_telnyx_bridges: dict[str, "TelnyxPstnBridge"] = {}
_admission_lock = asyncio.Lock()


def _pstn_direction(raw: Any, *, default: str = "outbound") -> str:
    value = str(raw or "").strip().lower()
    if value in ("outbound", "outgoing", "outbound-api"):
        return "outbound"
    if value in ("inbound", "incoming"):
        return "inbound"
    return default


@dataclass(frozen=True)
class OutboundFrame:
    payload: bytes
    codec: str
    turn_id: str | None
    generation_id: str | None


class TelnyxPstnBridge:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.call_control_id: str | None = None
        self.call_id: str | None = None
        self.agent_id: str | None = None
        self.tier: str | None = None
        self.session_id: str = "pstn"
        self.caller_id: str | None = None
        self._voice: PstnVoiceLoop | None = None
        self._closed = False
        self._wire_sample_rate = _WIRE_SAMPLE_RATE
        self._wire_codec = TELNYX_RTP_CODEC
        self._media_frames_in = 0
        self._media_frames_out = 0
        self.ws_id = new_ws_id()
        self._configured_media = CallMediaConfig(
            codec=TELNYX_RTP_CODEC,
            sample_rate=TELNYX_RTP_SAMPLE_RATE,
            channels=1,
        )
        self._negotiated_media = self._configured_media
        self._ws_send_lock = asyncio.Lock()
        self._out_queue: asyncio.Queue[OutboundFrame] = asyncio.Queue(maxsize=MAX_AUDIO_QUEUE_FRAMES)
        self._out_task: asyncio.Task | None = None
        self._logged_first_out = False
        self._client_meta: dict[str, Any] = {}
        self._token_meta: dict[str, Any] = {}
        self._start_handled = False
        self._owns_call = False
        self._invalid_generations: set[str] = set()
        self._bidirectional_mode = "rtp"
        self._mp3_sending = False
        self._out_sending = False
        self._source_audio_buf = bytearray()
        self._source_audio_generation: str | None = None
        self._last_mp3_sent_at = 0.0
        self._outbound_l16_to_8k: StreamingPcmResampler | None = None
        self._inbound_l16_resampler: StreamingPcmResampler | None = None
        self._outbound_pcm8k_buf = bytearray()
        self._outbound_8k_to_l16: StreamingPcmResampler | None = None
        self._outbound_l16_buf = bytearray()
        self._invalid_generation_order: list[str] = []
        self._voice_loop_task: asyncio.Task | None = None
        self._playback = None
        self._cleanup_done = False
        self._cleaned_voice_loop = False
        self._cleaned_out_task = False
        self._cleaned_voice = False
        self._cleaned_lifecycle = False
        self._cleaned_registry = False

    async def run(self, *, agent_id: str | None, tier: str | None, token_meta: dict[str, Any] | None) -> None:
        self._token_meta = dict(token_meta or {})
        self.agent_id = agent_id or self._token_meta.get("agent_id")
        self.tier = tier or self._token_meta.get("tier")
        try:
            while not self._closed:
                # Before media `start`, Telnyx may hold the socket open through the full
                # ring window (timeout_secs) with only a `connected` frame. Closing on a
                # 35s idle here killed outbound streams while the phone was still ringing.
                recv_timeout = 90.0 if not self._start_handled else 35.0
                try:
                    message = await asyncio.wait_for(self.ws.receive(), timeout=recv_timeout)
                except asyncio.TimeoutError:
                    if not self._start_handled:
                        log_pstn(
                            "stream.wait_start",
                            control=self.call_control_id,
                            call_id=self.call_id,
                            timeout_s=recv_timeout,
                        )
                        logger.info(
                            "[TELNYX] waiting for stream start control=%s (%.0fs quiet)",
                            self.call_control_id,
                            recv_timeout,
                        )
                        continue
                    # After start, Telnyx with send_silence_when_idle should keep media flowing.
                    # Prolonged silence => dead socket without a close frame (2.7).
                    log_pstn(
                        "stream.idle_timeout",
                        control=self.call_control_id,
                        call_id=self.call_id,
                        timeout_s=recv_timeout,
                    )
                    logger.warning(
                        "[TELNYX] websocket idle timeout control=%s",
                        self.call_control_id,
                    )
                    break
                except WebSocketDisconnect as exc:
                    logger.info("[TELNYX] websocket closed code=%s", exc.code)
                    break
                if message.get("type") == "websocket.disconnect":
                    break
                raw = message.get("text")
                if not raw:
                    if message.get("bytes") is not None and not self._start_handled:
                        log_pstn(
                            "stream.binary_frame",
                            control=self.call_control_id,
                            bytes=len(message.get("bytes") or b""),
                        )
                    continue
                ev = json.loads(raw)
                event = ev.get("event") or ""
                if not self._start_handled and event not in {"media"}:
                    log_pstn(
                        "stream.frame",
                        control=self.call_control_id,
                        event=event,
                        keys=sorted(ev.keys())[:12],
                    )
                if event == "connected":
                    log_pstn("stream.connected", control=self.call_control_id)
                    log_ws("Telnyx stream connected", control=self.call_control_id)
                    continue
                if event == "start":
                    if self._start_handled:
                        continue
                    self._start_handled = True
                    try:
                        await self._on_start(ev)
                        # Media WS start is the ground-truth stream_connected signal.
                        if self.call_control_id:
                            from server.services.telnyx_client import telnyx_call_registry

                            telnyx_call_registry.upsert(
                                self.call_control_id,
                                {
                                    "stream_connected": True,
                                    "stream_started": True,
                                    "stream_failed": False,
                                    "stream_state": "connected",
                                    "status": "streaming",
                                },
                            )
                            log_pstn(
                                "PSTN_STREAM",
                                call_id=self.call_id,
                                control=self.call_control_id,
                                event="stream_connected",
                                source="ws_start",
                            )
                    except Exception:
                        self._start_handled = False
                        raise
                elif event == "media":
                    await self._on_media(ev)
                elif event == "error":
                    payload = ev.get("payload") or {}
                    log_pstn(
                        "stream.error",
                        timer_key=self.call_control_id,
                        control=self.call_control_id,
                        call_id=self.call_id,
                        code=payload.get("code"),
                        title=payload.get("title"),
                        detail=str(payload.get("detail") or ev)[:200],
                    )
                    logger.warning("[TELNYX] stream error %s", payload or ev)
                elif event == "mark":
                    # Telnyx returns queued marks after clear — used as barge clear ACK (4.6).
                    name = (ev.get("mark") or {}).get("name") or ev.get("name")
                    log_pstn(
                        "stream.mark",
                        control=self.call_control_id,
                        call_id=self.call_id,
                        name=str(name or "")[:80],
                    )
                    if self._playback is not None and hasattr(self._playback, "on_provider_mark"):
                        try:
                            self._playback.on_provider_mark(name)
                        except Exception:
                            pass
                elif event == "stop":
                    log_pstn("stream.stop", timer_key=self.call_control_id, control=self.call_control_id)
                    logger.info("[TELNYX] stream stop")
                    break
        finally:
            try:
                await asyncio.shield(self._cleanup("stop"))
            except asyncio.CancelledError:
                await self._cleanup("stop")
                raise

    async def _decode_client_state(self, start: dict[str, Any]) -> None:
        raw = start.get("client_state")
        if not raw:
            return
        try:
            meta = json.loads(base64.b64decode(str(raw)).decode())
            if not isinstance(meta, dict):
                return
            self._client_meta = {**self._client_meta, **meta}
            self.agent_id = self.agent_id or meta.get("agent_id")
            self.tier = self.tier or meta.get("tier")
        except Exception:
            pass

    async def _on_start(self, ev: dict[str, Any]) -> None:
        start = ev.get("start") or ev
        self.call_control_id = start.get("call_control_id") or ev.get("call_control_id")
        if not self.call_control_id:
            raise ValueError("Telnyx start is missing call_control_id")
        expected_control = self._token_meta.get("call_control_id")
        if expected_control and expected_control != self.call_control_id:
            raise ValueError("Stream token does not belong to this call")
        self.caller_id = start.get("from") or start.get("caller")
        media = start.get("media_format") or {}
        raw_codec = str(media.get("encoding") or media.get("codec") or "L16").upper()
        if "L16" in raw_codec:
            self._wire_codec = "L16"
        elif "PCMA" in raw_codec or "ALAW" in raw_codec:
            self._wire_codec = "PCMA"
        elif "PCMU" in raw_codec or "MULAW" in raw_codec or "ULAW" in raw_codec:
            self._wire_codec = "PCMU"
        else:
            self._wire_codec = raw_codec
        self._wire_sample_rate = int(media.get("sample_rate") or (16000 if self._wire_codec == "L16" else 8000))
        channels = int(media.get("channels") or 1)
        await self._decode_client_state(start)
        self._negotiated_media = CallMediaConfig(
            codec=self._wire_codec,
            sample_rate=self._wire_sample_rate,
            channels=channels,
        )
        from server.config.env import get_settings

        settings = get_settings()
        max_calls = max(1, int(getattr(settings, "telnyx_max_concurrent_calls", 50) or 50))
        async with _admission_lock:
            if self.call_control_id in active_telnyx_bridges:
                raise RuntimeError("A media session already owns this call")
            if len(active_telnyx_bridges) >= max_calls:
                log_pstn(
                    "admission.rejected",
                    control=self.call_control_id,
                    active=len(active_telnyx_bridges),
                    max=max_calls,
                )
                raise RuntimeError(f"telnyx concurrent call limit reached ({max_calls})")
            active_telnyx_bridges[self.call_control_id or self.ws_id] = self
            self._owns_call = True
        from server.services.telnyx_client import telnyx_call_registry

        # Receipt of WS start is media proof even while lifecycle/provider setup runs.
        # Otherwise a slow cold start triggers the connect watchdog on a healthy socket.
        telnyx_call_registry.upsert(self.call_control_id, {
            "stream_connected": True, "stream_failed": False, "stream_state": "connected",
        })
        pstn_media_flow.start(
            external_id=self.call_control_id or self.ws_id,
            ws_id=self.ws_id,
            configured=self._configured_media,
        )
        mismatches = pstn_media_flow.negotiate(self.call_control_id or self.ws_id, self._negotiated_media)
        if mismatches:
            log_pstn(
                "media.negotiation.mismatch",
                control=self.call_control_id,
                ws_id=self.ws_id,
                configured=self._configured_media.codec,
                negotiated=self._negotiated_media.codec,
                failures=mismatches,
            )

        from server.services.telnyx_client import telnyx_call_registry

        local = telnyx_call_registry.get(self.call_control_id or "") or {}
        merged_local = {**self._client_meta, **self._token_meta, **local}
        self.agent_id = self.agent_id or merged_local.get("agent_id")
        if not self.agent_id:
            from server.brain.agent_service import agent_service

            self.agent_id = await agent_service.resolve_default_agent_id()
        if not self.agent_id:
            raise RuntimeError("No PSTN agent could be resolved")
        self.tier = self.tier or merged_local.get("tier")
        merged_local["agent_id"] = self.agent_id
        if _pstn_direction(merged_local.get("direction"), default="inbound") == "inbound":
            merged_local["inherit_test_studio_config"] = True
        pstn_opts = pstn_call_options(merged_local)
        self.tier = pstn_opts.get("tier") or self.tier
        log_pstn(
            "stream.start",
            timer_key=self.call_control_id,
            control=self.call_control_id,
            agent_id=self.agent_id,
            from_e164=self.caller_id,
            sample_rate=self._wire_sample_rate,
            codec=self._wire_codec,
            channels=channels,
            ws_id=self.ws_id,
            config_session=pstn_opts.get("config_session_id"),
        )

        try:
            prewarm = None
            if self.agent_id and self.call_control_id:
                from server.services.pstn_prewarm import take_prewarm_for_answer

                try:
                    prewarm = await take_prewarm_for_answer("telnyx", self.call_control_id)
                except Exception as exc:
                    log_pstn("prewarm.adopt_failed", control=self.call_control_id, error=str(exc)[:160])
            self._prewarm_bundle = prewarm
            if self.agent_id:
                from server.call.call_lifecycle_service import call_lifecycle_service

                started = await call_lifecycle_service.start(
                    agent_id=self.agent_id,
                    session_id=f"pstn-telnyx-{self.call_control_id}",
                    config_session_id=pstn_opts.get("config_session_id"),
                    channel="pstn",
                    direction=_pstn_direction(merged_local.get("direction"), default="inbound"),
                    tier=self.tier,
                    caller_id=self.caller_id,
                    stack_override=pstn_opts.get("stack_override"),
                    language=str(pstn_opts.get("language") or "te-IN"),
                    realtime_prewarm_key=prewarm.realtime_key if prewarm else None,
                )
                self.call_id = started["call_id"]
                pstn_media_flow.bind_call_id(self.call_control_id or self.ws_id, self.call_id)
                self.session_id = started["session_id"]
                mark(self.call_id)
                log_pstn(
                    "call.started",
                    timer_key=self.call_control_id,
                    control=self.call_control_id,
                    call_id=self.call_id,
                    combo=started.get("combination_id"),
                )
                if self.call_control_id:
                    telnyx_call_registry.upsert(
                        self.call_control_id,
                        {"internal_call_id": self.call_id, "status": "streaming", "last_event": "stream-start"},
                    )
                logger.info("[TELNYX] stream started call_id=%s control=%s", self.call_id, self.call_control_id)

            self._out_task = asyncio.create_task(self._out_worker())
            from server.services.pstn_playback import TelnyxQueuePlayback

            def _drain_queue() -> int:
                interrupted = 0
                while True:
                    try:
                        self._out_queue.get_nowait()
                        interrupted += 1
                    except asyncio.QueueEmpty:
                        break
                return interrupted

            self._playback = TelnyxQueuePlayback(
                queue_size=lambda: self._out_queue.qsize(),
                drain=_drain_queue,
                frame_ms=20.0,
                sending=lambda: self._mp3_sending or self._out_sending,
            )
            self._voice = PstnVoiceLoop(
                session_id=self.session_id,
                call_id=self.call_id,
                on_agent_wire=self._send_agent_wire,
                sample_rate=_WIRE_SAMPLE_RATE,
                tts_session_id=pstn_opts.get("tts_session_id"),
                config_session_id=pstn_opts.get("config_session_id"),
                tts_output_codec="mp3" if self._bidirectional_mode == "mp3" else "linear16",
                is_agent_audio_active=self._playback.is_active,
                playback=self._playback,
            )
            self._voice.set_barge_handler(self._barge_in)
            self._voice.set_hangup_handler(self._provider_hangup)
            self._voice_loop_task = asyncio.create_task(self._start_voice_loop())
        except Exception as exc:
            logger.exception("[TELNYX] stream start failed control=%s: %s", self.call_control_id, exc)
            if self.call_control_id:
                telnyx_call_registry.upsert(
                    self.call_control_id,
                    {"status": "stream-error", "last_event": "stream-error", "error": str(exc)[:200]},
                )
                await self._provider_hangup()
            raise

    async def _start_voice_loop(self) -> None:
        if not self._voice:
            return
        try:
            skip_greeting = bool(
                self._client_meta.get("skip_greeting")
                or self._client_meta.get("test_mode") == "cartesia_bilingual"
            )
            prewarm = getattr(self, "_prewarm_bundle", None)
            await self._voice.start_call(
                play_greeting=bool(self.call_id) and not skip_greeting,
                greeting_wire_frames=prewarm.greeting_wire_frames if prewarm else None,
                greeting_text=prewarm.greeting_text if prewarm else None,
            )
            if self._client_meta.get("test_mode") == "cartesia_bilingual":
                await self._run_cartesia_bilingual_test()
        except Exception as exc:
            log_pstn(
                "lifecycle.failed",
                timer_key=self.call_control_id,
                control=self.call_control_id,
                call_id=self.call_id,
                error=str(exc)[:200],
            )
            logger.exception("[TELNYX] voice loop failed control=%s: %s", self.call_control_id, exc)
            # A failed startup must not leave an answered, billable silent call.
            try:
                await asyncio.wait_for(self._provider_hangup(), timeout=4.0)
            except Exception:
                logger.warning("[TELNYX] startup failure hangup did not complete", exc_info=True)
            finally:
                await self._cleanup("voice_start_failed")
                try:
                    await self.ws.close(code=1011)
                except Exception:
                    pass

    async def _on_media(self, ev: dict[str, Any]) -> None:
        if not self._voice:
            return
        media = ev.get("media") or {}
        track = str(media.get("track") or "").lower()
        # both_tracks echoes our TTS on outbound — only feed caller audio to STT.
        if track == "outbound":
            return
        payload = media.get("payload") or media.get("chunk")
        if not payload:
            return
        wire = base64.b64decode(payload)
        if self._wire_codec == "L16":
            pcm = wire
            if self._wire_sample_rate != _WIRE_SAMPLE_RATE:
                if (
                    self._inbound_l16_resampler is None
                    or self._inbound_l16_resampler.from_rate != self._wire_sample_rate
                    or self._inbound_l16_resampler.to_rate != _WIRE_SAMPLE_RATE
                ):
                    self._inbound_l16_resampler = StreamingPcmResampler(
                        self._wire_sample_rate, _WIRE_SAMPLE_RATE
                    )
                pcm = self._inbound_l16_resampler.feed(pcm)
                if not pcm:
                    return
        elif self._wire_codec == "PCMU":
            if self._inbound_l16_resampler is None:
                self._inbound_l16_resampler = StreamingPcmResampler(8000, _WIRE_SAMPLE_RATE)
            pcm = self._inbound_l16_resampler.feed(mulaw_to_pcm16(wire, target_rate=8000))
        elif self._wire_codec == "PCMA":
            if self._inbound_l16_resampler is None:
                self._inbound_l16_resampler = StreamingPcmResampler(8000, _WIRE_SAMPLE_RATE)
            pcm = self._inbound_l16_resampler.feed(alaw_to_pcm16(wire, target_rate=8000))
        else:  # guarded by CallMediaConfig, defensive for future codecs
            raise ValueError(f"unsupported negotiated codec {self._wire_codec}")
        self._media_frames_in += 1
        level = None if self._wire_codec == "L16" else g711_dbfs(wire, self._wire_codec)
        pstn_media_flow.emit(
            self.call_control_id or self.ws_id,
            "inbound_audio",
            "inbound",
            codec=self._wire_codec,
            sample_rate=self._wire_sample_rate,
            channels=self._negotiated_media.channels,
            bytes=len(wire),
            frames=1,
            duration_ms=self._negotiated_media.duration_ms(len(wire)),
            queue_size=self._out_queue.qsize(),
            level_dbfs=level,
        )
        if self._media_frames_in == 1:
            log_pstn(
                "media.in.first",
                timer_key=self.call_control_id,
                control=self.call_control_id,
                call_id=self.call_id,
                bytes=len(pcm),
            )
            log_ws("Telnyx first inbound media", control=self.call_control_id, bytes=len(pcm))
        await self._voice.feed_user_pcm16(pcm)
        pstn_media_flow.emit(
            self.call_control_id or self.ws_id,
            "stt_audio",
            "inbound",
            turn_id=self._voice.current_turn_id,
            codec="PCM16",
            sample_rate=_WIRE_SAMPLE_RATE,
            channels=1,
            bytes=len(pcm),
            frames=1,
            duration_ms=len(pcm) * 1000 / (_WIRE_SAMPLE_RATE * 2),
            queue_size=self._out_queue.qsize(),
        )

    async def _out_worker(self) -> None:
        """Send one RTP frame every 20ms with monotonic clock correction (no drift)."""
        frame_period = 0.02
        next_send_at: float | None = None
        try:
            while not self._closed:
                self._out_sending = False
                try:
                    frame = await asyncio.wait_for(self._out_queue.get(), timeout=0.04)
                except asyncio.TimeoutError:
                    next_send_at = None
                    if self._voice is not None and hasattr(self._voice, "on_playback_drained"):
                        self._voice.on_playback_drained()
                    continue
                self._out_sending = True
                chunk = frame.payload
                playback = getattr(self, "_playback", None)
                if frame.generation_id and frame.generation_id in self._invalid_generations:
                    pstn_media_flow.increment(
                        self.call_control_id or self.ws_id, "dropped_frames", 1
                    )
                    log_pstn(
                        "DROP_STALE_GEN",
                        control=self.call_control_id,
                        old=frame.generation_id,
                        current=self._voice.current_generation_id if self._voice else None,
                    )
                    continue
                if playback is not None and not playback.is_generation_valid(frame.generation_id):
                    pstn_media_flow.increment(
                        self.call_control_id or self.ws_id, "dropped_frames", 1
                    )
                    log_pstn(
                        "DROP_STALE_GEN",
                        control=self.call_control_id,
                        old=frame.generation_id,
                        current=playback.current_generation(),
                    )
                    continue
                if frame.codec != self._negotiated_media.codec:
                    log_pstn(
                        "outbound.frame.drop",
                        control=self.call_control_id,
                        reason="codec_mismatch",
                        got=frame.codec,
                        expected=self._negotiated_media.codec,
                    )
                    continue
                if len(chunk) != self._negotiated_media.frame_bytes:
                    log_pstn(
                        "outbound.frame.drop",
                        control=self.call_control_id,
                        reason="frame_size",
                        got=len(chunk),
                        expected=self._negotiated_media.frame_bytes,
                    )
                    continue
                now = time.monotonic()
                if next_send_at is None:
                    # Two frames of startup headroom absorb upstream chunk jitter.
                    next_send_at = now + 0.04
                delay = next_send_at - now
                if delay > 0:
                    while time.monotonic() < next_send_at:
                        await asyncio.sleep(max(0.001, next_send_at - time.monotonic()))
                elif delay < -frame_period:
                    next_send_at = time.monotonic()
                encoded = base64.b64encode(chunk).decode("ascii")
                message = json.dumps({"event": "media", "media": {"payload": encoded}})
                async with self._ws_send_lock:
                    # A barge can invalidate this frame during pacing or lock acquisition.
                    # Recheck at the actual wire boundary, after every preceding await.
                    if self._closed or (
                        frame.generation_id in self._invalid_generations
                        or (playback is not None and not playback.is_generation_valid(frame.generation_id))
                    ):
                        pstn_media_flow.increment(self.call_control_id or self.ws_id, "dropped_frames", 1)
                        continue
                    await self.ws.send_text(message)
                    if self._voice is not None and hasattr(self._voice, "_promote_queued_tts_to_heard"):
                        self._voice._promote_queued_tts_to_heard()
                next_send_at = (next_send_at or time.monotonic()) + frame_period
                self._media_frames_out += 1
                pstn_media_flow.emit(
                    self.call_control_id or self.ws_id,
                    "outbound_sent",
                    "outbound",
                    turn_id=frame.turn_id,
                    generation_id=frame.generation_id,
                    codec=frame.codec,
                    sample_rate=self._negotiated_media.sample_rate,
                    channels=self._negotiated_media.channels,
                    bytes=len(chunk),
                    frames=1,
                    duration_ms=self._negotiated_media.duration_ms(len(chunk)),
                    queue_size=self._out_queue.qsize(),
                    level_dbfs=g711_dbfs(chunk, frame.codec) if frame.codec in {"PCMU", "PCMA"} else None,
                    extra={"base64_length": len(encoded), "json_length": len(message)},
                )
                if not self._logged_first_out:
                    self._logged_first_out = True
                    log_pstn(
                        "media.out.first",
                        timer_key=self.call_control_id,
                        control=self.call_control_id,
                        call_id=self.call_id,
                        frames=1,
                        bytes=len(chunk),
                        codec=self._wire_codec,
                    )
                    log_tts(
                        "Telnyx first outbound audio",
                        control=self.call_control_id,
                        frames=1,
                        bytes=len(chunk),
                    )
                if self._media_frames_out in (50, 200, 500):
                    log_pstn(
                        "media.out.progress",
                        timer_key=self.call_control_id,
                        call_id=self.call_id,
                        frames_out=self._media_frames_out,
                        queue_qsize=self._out_queue.qsize(),
                    )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            pstn_media_flow.emit(
                self.call_control_id or self.ws_id,
                "outbound_sent",
                "outbound",
                status="failed",
                detail=str(exc)[:200],
                queue_size=self._out_queue.qsize(),
            )
            log_pstn("media.out.failed", call_id=self.call_id, error=str(exc)[:200])
            logger.exception("[TELNYX] outbound worker failed: %s", str(exc)[:200])
            self._closed = True
            await self.ws.close(code=1011)
        finally:
            self._out_sending = False

    async def _send_agent_mp3(self, mp3: bytes) -> None:
        """Telnyx mp3 bidirectional mode — one base64 MP3 blob per message (1 msg/sec limit)."""
        if not mp3:
            return
        generation_id = self._voice.current_generation_id if self._voice else None
        if generation_id and generation_id in self._invalid_generations:
            pstn_media_flow.increment(self.call_control_id or self.ws_id, "dropped_frames", 1)
            return
        elapsed = time.monotonic() - self._last_mp3_sent_at
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        if generation_id and generation_id in self._invalid_generations:
            return
        encoded = base64.b64encode(mp3).decode("ascii")
        message = json.dumps({"event": "media", "media": {"payload": encoded}})
        self._mp3_sending = True
        try:
            async with self._ws_send_lock:
                await self.ws.send_text(message)
        finally:
            self._mp3_sending = False
        self._last_mp3_sent_at = time.monotonic()
        self._media_frames_out += 1
        pstn_media_flow.emit(
            self.call_control_id or self.ws_id,
            "outbound_sent",
            "outbound",
            turn_id=self._voice.current_turn_id if self._voice else None,
            generation_id=generation_id,
            codec="MP3",
            sample_rate=24000,
            channels=1,
            bytes=len(mp3),
            frames=1,
            queue_size=0,
            status="healthy",
            extra={"base64_length": len(encoded), "json_length": len(message), "mode": "mp3"},
        )
        if not self._logged_first_out:
            self._logged_first_out = True
            log_pstn(
                "media.out.first",
                timer_key=self.call_control_id,
                control=self.call_control_id,
                call_id=self.call_id,
                frames=1,
                bytes=len(mp3),
                codec="MP3",
                mode="mp3",
            )

    def _l16_chunks_to_pcmu(self, chunks: list[bytes]) -> list[bytes]:
        """Resample L16→8 kHz with continuous ratecv state, then μ-law frame."""
        l16_rate = int(self._negotiated_media.sample_rate or 16000)
        if self._outbound_l16_to_8k is None or self._outbound_l16_to_8k.from_rate != l16_rate:
            self._outbound_l16_to_8k = StreamingPcmResampler(l16_rate, 8000)
            self._outbound_pcm8k_buf = bytearray()
        out: list[bytes] = []
        for chunk in chunks:
            self._outbound_pcm8k_buf.extend(self._outbound_l16_to_8k.feed(chunk))
            while len(self._outbound_pcm8k_buf) >= 320:
                frame = bytes(self._outbound_pcm8k_buf[:320])
                del self._outbound_pcm8k_buf[:320]
                out.append(pcm16_to_mulaw(frame, sample_rate=8000))
        return out

    async def _send_agent_wire(self, wire: bytes) -> None:
        """Enqueue Telnyx RTP payloads — or send MP3 blobs in mp3 bidirectional mode."""
        if self._bidirectional_mode == "mp3":
            await self._send_agent_mp3(wire)
            return
        source_codec = self._voice.current_output_codec if self._voice else "PCMU"
        target_codec = self._negotiated_media.codec
        generation_id = self._voice.current_generation_id if self._voice else None
        turn_id = self._voice.current_turn_id if self._voice else None
        if generation_id != self._source_audio_generation:
            self._source_audio_buf.clear()
            self._source_audio_generation = generation_id
        # Chunk boundaries are arbitrary. Pad only at TTS finish, never each callback.
        self._source_audio_buf.extend(wire)
        source_frame_bytes = 640 if source_codec == "L16" else 160
        complete = len(self._source_audio_buf) // source_frame_bytes * source_frame_bytes
        wire = bytes(self._source_audio_buf[:complete])
        del self._source_audio_buf[:complete]
        if source_codec == "PCMU":
            source_chunks = chunk_mulaw_frames(wire, sample_rate=8000)
        elif source_codec == "L16":
            source_chunks = _chunk_l16_rtp(wire, _WIRE_SAMPLE_RATE)
        else:
            raise ValueError(f"unsupported TTS output codec {source_codec}")

        if source_codec in {"PCMU", "PCMA"} and target_codec in {"PCMU", "PCMA"}:
            chunks = [convert_g711(chunk, source_codec, target_codec) for chunk in source_chunks]
        elif source_codec == "L16" and target_codec in {"PCMU", "PCMA"}:
            # Stateful 16k→8k across frames — one-shot ratecv per frame caused crackle.
            pcmu_chunks = self._l16_chunks_to_pcmu(source_chunks)
            chunks = [convert_g711(chunk, "PCMU", target_codec) for chunk in pcmu_chunks]
        elif source_codec == "PCMU" and target_codec == "L16":
            chunks = []
            for chunk in source_chunks:
                pcm = mulaw_to_pcm16(chunk, 8000)
                if self._outbound_8k_to_l16 is None:
                    self._outbound_8k_to_l16 = StreamingPcmResampler(8000, 16000)
                    # ratecv has one output-sample startup latency. Hold the first
                    # sample once, then preserve all subsequent samples across frames.
                    self._outbound_l16_buf.extend(pcm[:2])
                self._outbound_l16_buf.extend(self._outbound_8k_to_l16.feed(pcm))
                while len(self._outbound_l16_buf) >= 640:
                    chunks.append(bytes(self._outbound_l16_buf[:640]))
                    del self._outbound_l16_buf[:640]
        elif source_codec == target_codec:
            chunks = source_chunks
        else:
            raise ValueError(f"unsupported outbound conversion {source_codec}->{target_codec}")
        outbound_codec = target_codec
        if outbound_codec != self._negotiated_media.codec:
            log_pstn(
                "outbound.convert.drop",
                control=self.call_control_id,
                reason="codec_mismatch",
                got=outbound_codec,
                expected=self._negotiated_media.codec,
            )
            return
        if self._negotiated_media.sample_rate not in {8000, 16000} or self._negotiated_media.channels != 1:
            log_pstn(
                "outbound.convert.drop",
                control=self.call_control_id,
                reason="media_shape",
                sample_rate=self._negotiated_media.sample_rate,
                channels=self._negotiated_media.channels,
            )
            return
        if self._media_frames_out == 0 and self._out_queue.empty():
            log_pstn(
                "media.out.queued",
                timer_key=self.call_control_id,
                call_id=self.call_id,
                wire_bytes=len(wire),
                rtp_frames=len(chunks),
                wire_mulaw=source_codec == "PCMU",
                source_codec=source_codec,
                outbound_codec=outbound_codec,
            )
        for chunk in chunks:
            playback = getattr(self, "_playback", None)
            if playback is not None and not playback.is_generation_valid(generation_id):
                pstn_media_flow.increment(self.call_control_id or self.ws_id, "dropped_frames", 1)
                return
            if generation_id and generation_id in self._invalid_generations:
                pstn_media_flow.increment(self.call_control_id or self.ws_id, "dropped_frames", 1)
                return
            frame = OutboundFrame(
                payload=chunk,
                codec=outbound_codec,
                turn_id=turn_id,
                generation_id=generation_id,
            )
            try:
                deadline = time.monotonic() + 2.0
                while True:
                    if self._closed or generation_id in self._invalid_generations or (
                        playback is not None and not playback.is_generation_valid(generation_id)
                    ):
                        return
                    try:
                        # Validation + enqueue are synchronous: no blocked put can
                        # wake after a drain and resurrect invalidated audio.
                        self._out_queue.put_nowait(frame)
                        break
                    except asyncio.QueueFull:
                        if time.monotonic() >= deadline:
                            raise asyncio.TimeoutError()
                        await asyncio.sleep(0.005)
            except asyncio.TimeoutError:
                pstn_media_flow.increment(self.call_control_id or self.ws_id, "dropped_frames", 1)
                log_pstn("outbound.queue.timeout", control=self.call_control_id, call_id=self.call_id)
                return
            if playback is not None and not playback.is_generation_valid(generation_id):
                pstn_media_flow.increment(self.call_control_id or self.ws_id, "dropped_frames", 1)
                return
            if generation_id and generation_id in self._invalid_generations:
                pstn_media_flow.increment(self.call_control_id or self.ws_id, "dropped_frames", 1)
                return
            queue_size = self._out_queue.qsize()
            queue_status = "delayed" if queue_size >= 10 else "healthy"
            pstn_media_flow.emit(
                self.call_control_id or self.ws_id,
                "converter",
                "outbound",
                turn_id=frame.turn_id,
                generation_id=frame.generation_id,
                codec=outbound_codec,
                sample_rate=self._negotiated_media.sample_rate,
                channels=1,
                bytes=len(chunk),
                frames=1,
                duration_ms=self._negotiated_media.duration_ms(len(chunk)),
                queue_size=queue_size,
                detail=f"{source_codec}->{outbound_codec}",
                status=queue_status,
            )
            pstn_media_flow.emit(
                self.call_control_id or self.ws_id,
                "outbound_queued",
                "outbound",
                turn_id=frame.turn_id,
                generation_id=frame.generation_id,
                codec=outbound_codec,
                sample_rate=self._negotiated_media.sample_rate,
                channels=1,
                bytes=len(chunk),
                frames=1,
                duration_ms=self._negotiated_media.duration_ms(len(chunk)),
                queue_size=queue_size,
                status=queue_status,
            )

    async def drain_outbound(self, *, timeout_s: float = 2.5) -> bool:
        """Wait until the outbound RTP queue drains so farewell audio can play."""
        deadline = time.monotonic() + max(0.2, float(timeout_s))
        while time.monotonic() < deadline:
            if self._out_queue.empty() and not self._mp3_sending and not self._out_sending:
                # One extra frame period so the last queued frame can leave the worker.
                await asyncio.sleep(0.04)
                if self._out_queue.empty() and not self._out_sending:
                    return True
            await asyncio.sleep(0.02)
        log_pstn(
            "hangup.drain.timeout",
            control=self.call_control_id,
            call_id=self.call_id,
            queue=self._out_queue.qsize(),
        )
        return False

    async def _provider_hangup(self) -> None:
        if not self.call_control_id:
            return
        from server.services.telnyx_client import TelnyxClient

        await self.drain_outbound(timeout_s=2.5)
        try:
            await TelnyxClient().hangup(self.call_control_id)
            log_pstn("hangup.provider", control=self.call_control_id, call_id=self.call_id)
        except Exception as exc:
            log_pstn("hangup.provider.failed", control=self.call_control_id, error=str(exc)[:200])

    async def _barge_in(self) -> None:
        generation_id = (getattr(self._voice, "_barge_generation", None)
                         or self._voice.current_generation_id) if self._voice else None
        playback = getattr(self, "_playback", None)
        generation_id = generation_id or (playback.current_generation() if playback else None)
        self._source_audio_buf.clear()
        self._outbound_pcm8k_buf.clear()
        self._outbound_l16_buf.clear()
        self._outbound_l16_to_8k = None
        self._outbound_8k_to_l16 = None
        if playback is not None:
            playback.invalidate_generation(generation_id)
            interrupted = playback.clear()
        else:
            if generation_id:
                self._invalid_generations.add(generation_id)
                self._invalid_generation_order.append(generation_id)
            interrupted = 0
            while True:
                try:
                    self._out_queue.get_nowait()
                    interrupted += 1
                except asyncio.QueueEmpty:
                    break
        if generation_id:
            self._invalid_generations.add(generation_id)
            if not self._invalid_generation_order or self._invalid_generation_order[-1] != generation_id:
                self._invalid_generation_order.append(generation_id)
            # Prune stale gens (FIFO — sets alone are unordered).
            while len(self._invalid_generation_order) > 12:
                old = self._invalid_generation_order.pop(0)
                self._invalid_generations.discard(old)
        if interrupted:
            pstn_media_flow.increment(
                self.call_control_id or self.ws_id, "interrupted_frames", interrupted
            )
        pstn_media_flow.emit(
            self.call_control_id or self.ws_id,
            "queue_cleared",
            "outbound",
            turn_id=self._voice.current_turn_id if self._voice else None,
            generation_id=generation_id,
            frames=interrupted,
            queue_size=0,
            status="processing",
            detail="caller barge-in",
        )
        log_pstn(
            "PROVIDER_CLEAR",
            control=self.call_control_id,
            call_id=self.call_id,
            frames=interrupted,
            generation_id=generation_id,
            queue_ms=playback.queued_ms() if playback else 0,
        )
        async with self._ws_send_lock:
            await self.ws.send_text(json.dumps({"event": "clear"}))
        pstn_media_flow.emit(self.call_control_id or self.ws_id, "remote_cleared", "outbound", generation_id=generation_id)

    async def _run_cartesia_bilingual_test(self) -> None:
        """Cartesia L16 @ 16 kHz — Telugu (Indian voice) then English (US accent)."""
        if not self._voice:
            return
        from server.services.cartesia_voices import fetch_cartesia_voices

        voices = await fetch_cartesia_voices()
        indian = next((v for v in voices if v.get("region") == "indian_english"), None)
        telugu = next((v for v in voices if v.get("region") == "telugu"), indian)
        english = next((v for v in voices if v.get("region") == "english"), None)
        indian_id = str((telugu or indian or {}).get("id") or "79a125e8-cd45-4c13-8a67-0491c5ad1b8a")
        english_id = str((english or {}).get("id") or "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4")
        telugu_msg = (
            "Namaste! Nenu Priya, SKM Plants nundi matladutunnanu. "
            "Meeku ela help cheyagalanu?"
        )
        english_msg = (
            "Hello! This is Priya from SKM Plants. "
            "How can I help you today?"
        )
        log_pstn(
            "cartesia_bilingual.start",
            call_id=self.call_id,
            telugu_voice=indian_id[:8],
            english_voice=english_id[:8],
        )
        await self._voice.speak(telugu_msg, speaker=indian_id, language_code="te-IN")
        await asyncio.sleep(0.8)
        await self._voice.speak(english_msg, speaker=english_id, language_code="en-IN")
        log_pstn("cartesia_bilingual.done", call_id=self.call_id)

    async def test_agent_audio(self) -> None:
        for _ in range(50):
            if self._voice:
                break
            await asyncio.sleep(0.1)
        if not self._voice:
            raise RuntimeError("voice loop is not ready")
        await self._voice.speak(
            "Signal test one. Signal test two. Signal test three. "
            "నమస్కారం, ఇది ఏజెంట్ ఆడియో పరీక్ష."
        )

    async def _cleanup(self, reason: str) -> None:
        """Idempotent staged cleanup — safe to call twice after a mid-await cancel (12.3)."""
        if self._cleanup_done:
            return
        self._closed = True
        if not self._cleaned_voice_loop:
            if (self._voice_loop_task and not self._voice_loop_task.done()
                    and self._voice_loop_task is not asyncio.current_task()):
                self._voice_loop_task.cancel()
                try:
                    await self._voice_loop_task
                except (asyncio.CancelledError, Exception):
                    pass
            self._cleaned_voice_loop = True
        if not self._cleaned_out_task:
            if self._out_task and not self._out_task.done():
                self._out_task.cancel()
                try:
                    await self._out_task
                except (asyncio.CancelledError, Exception):
                    pass
            self._cleaned_out_task = True
        if not self._cleaned_voice:
            if self._voice:
                try:
                    await self._voice.close()
                except Exception:
                    pass
                self._voice = None
            self._cleaned_voice = True
        if not self._cleaned_lifecycle and self.call_id:
            from server.call.call_lifecycle_service import call_lifecycle_service

            try:
                await asyncio.wait_for(
                    call_lifecycle_service.end(self.call_id, reason="pstn_hangup"),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                log_pstn("lifecycle.end.timeout", call_id=self.call_id, timeout_s=5.0)
            except Exception:
                pass
            self._cleaned_lifecycle = True
        elif not self._cleaned_lifecycle:
            self._cleaned_lifecycle = True
        if not self._cleaned_registry:
            if active_telnyx_bridges.get(self.call_control_id) is self:
                active_telnyx_bridges.pop(self.call_control_id, None)
            if active_telnyx_bridges.get(self.ws_id) is self:
                active_telnyx_bridges.pop(self.ws_id, None)
            if self.call_control_id and self._owns_call:
                bidirectional_ok = self._media_frames_in > 0 and self._media_frames_out > 0
                from server.services.telnyx_client import telnyx_call_registry

                health_score: int | None = None
                failures: list[str] = []
                flow_snap = pstn_media_flow.snapshot(self.call_control_id or self.ws_id)
                if flow_snap:
                    health = flow_snap.get("health") or {}
                    health_score = int(health.get("score") or 0) or None
                    failures = list(health.get("failures") or flow_snap.get("failures") or [])

                telnyx_call_registry.upsert(
                    self.call_control_id,
                    {
                        "status": "completed",
                        "stream_connected": False,
                        "stream_state": "ended",
                        "ended": True,
                        "last_event": reason,
                        "media_frames_in": self._media_frames_in,
                        "media_frames_out": self._media_frames_out,
                        "bidirectional_ok": bidirectional_ok,
                        "health_score": health_score,
                    },
                )
                if self.call_id:
                    from server.call.call_context import get as get_ctx
                    from server.services.production_canary import record_canary_call

                    ctx = get_ctx(self.call_id)
                    record_canary_call(
                        call_id=self.call_id,
                        external_id=self.call_control_id,
                        bidirectional_ok=bidirectional_ok,
                        media_in=self._media_frames_in,
                        media_out=self._media_frames_out,
                        health_score=health_score,
                        failures=failures,
                        compiled_brain_version=ctx.compiled_brain_version if ctx else None,
                        combination_id=ctx.resolved_stack.combination_id if ctx and ctx.resolved_stack else None,
                    )
                log_pstn_summary(
                    provider="telnyx",
                    external_id=self.call_control_id,
                    call_id=self.call_id,
                    media_in=self._media_frames_in,
                    media_out=self._media_frames_out,
                    reason=reason,
                )
                pstn_media_flow.finish(self.call_control_id)
            self._cleaned_registry = True
        self._cleanup_done = True


def _chunk_l16_rtp(pcm16: bytes, sample_rate: int = 16000) -> list[bytes]:
    frame_bytes = int(sample_rate * 20 / 1000) * 2
    chunks: list[bytes] = []
    for i in range(0, len(pcm16), frame_bytes):
        chunk = pcm16[i : i + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk = chunk + b"\x00" * (frame_bytes - len(chunk))
        chunks.append(chunk)
    return chunks
