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
    alaw_to_pcm16,
    chunk_mulaw_frames,
    convert_g711,
    g711_dbfs,
    mulaw_to_pcm16,
    pcm16_chunk_to_mulaw_frames,
)
from server.services.pstn_debug import log_pstn, log_pstn_summary, mark
from server.services.pstn_media_flow import CallMediaConfig, new_ws_id, pstn_media_flow
from server.services.pstn_voice_core import (
    ENABLE_PSTN_BARGE_IN,
    PstnVoiceLoop,
    pstn_call_options,
)
from server.services.telnyx_client import TELNYX_RTP_CODEC, TELNYX_RTP_SAMPLE_RATE
from server.utils.logger import log_tts, log_ws

logger = logging.getLogger(__name__)

# Telnyx L16 wire @ 16 kHz — matches Sarvam linear16 and avoids G.711 transcoding.
_WIRE_SAMPLE_RATE = TELNYX_RTP_SAMPLE_RATE
MAX_AUDIO_QUEUE_FRAMES = 15  # 300 ms at 20 ms/frame; producer backpressures here.
active_telnyx_bridges: dict[str, "TelnyxPstnBridge"] = {}


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
        self._invalid_generations: set[str] = set()
        self._bidirectional_mode = "rtp"
        self._mp3_sending = False
        self._last_mp3_sent_at = 0.0

    async def run(self, *, agent_id: str | None, tier: str | None, token_meta: dict[str, Any] | None) -> None:
        self.agent_id = agent_id or (token_meta or {}).get("agent_id")
        self.tier = tier or (token_meta or {}).get("tier")
        try:
            while not self._closed:
                try:
                    message = await self.ws.receive()
                except WebSocketDisconnect as exc:
                    logger.info("[TELNYX] websocket closed code=%s", exc.code)
                    break
                if message.get("type") == "websocket.disconnect":
                    break
                raw = message.get("text")
                if not raw:
                    continue
                ev = json.loads(raw)
                event = ev.get("event") or ""
                if event == "connected":
                    log_pstn("stream.connected", control=self.call_control_id)
                    log_ws("Telnyx stream connected", control=self.call_control_id)
                    continue
                if event == "start":
                    await self._on_start(ev)
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
                elif event == "stop":
                    log_pstn("stream.stop", timer_key=self.call_control_id, control=self.call_control_id)
                    logger.info("[TELNYX] stream stop")
                    break
        finally:
            await self._cleanup("stop")

    async def _decode_client_state(self, start: dict[str, Any]) -> None:
        raw = start.get("client_state")
        if not raw or self.agent_id:
            return
        try:
            meta = json.loads(base64.b64decode(str(raw)).decode())
            self.agent_id = meta.get("agent_id") or self.agent_id
            self.tier = meta.get("tier") or self.tier
            self._client_meta = meta
        except Exception:
            pass

    async def _on_start(self, ev: dict[str, Any]) -> None:
        start = ev.get("start") or ev
        self.call_control_id = start.get("call_control_id") or ev.get("call_control_id")
        self.caller_id = start.get("from") or start.get("caller")
        media = start.get("media_format") or {}
        self._wire_sample_rate = int(media.get("sample_rate") or _WIRE_SAMPLE_RATE)
        self._wire_codec = str(media.get("encoding") or media.get("codec") or "PCMU").upper()
        channels = int(media.get("channels") or 1)
        await self._decode_client_state(start)
        self._negotiated_media = CallMediaConfig(
            codec=self._wire_codec,
            sample_rate=self._wire_sample_rate,
            channels=channels,
        )
        active_telnyx_bridges[self.call_control_id or self.ws_id] = self
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
        merged_local = {**local, **self._client_meta}
        self.agent_id = self.agent_id or merged_local.get("agent_id")
        self.tier = self.tier or merged_local.get("tier")
        pstn_opts = pstn_call_options(merged_local)
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
        )

        try:
            if self.agent_id:
                from server.call.call_lifecycle_service import call_lifecycle_service

                started = await call_lifecycle_service.start(
                    agent_id=self.agent_id,
                    session_id=f"pstn-telnyx-{self.call_control_id}",
                    channel="pstn",
                    direction=str(merged_local.get("direction") or "outbound"),
                    tier=self.tier,
                    caller_id=self.caller_id,
                    stack_override=pstn_opts.get("stack_override"),
                    language=str(pstn_opts.get("language") or "te-IN"),
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
            self._voice = PstnVoiceLoop(
                session_id=self.session_id,
                call_id=self.call_id,
                on_agent_wire=self._send_agent_wire,
                sample_rate=_WIRE_SAMPLE_RATE,
                tts_session_id=pstn_opts.get("tts_session_id"),
                tts_output_codec="mp3" if self._bidirectional_mode == "mp3" else "linear16",
                is_agent_audio_active=lambda: not self._out_queue.empty(),
            )
            if ENABLE_PSTN_BARGE_IN:
                self._voice.set_barge_handler(self._barge_in)
            asyncio.create_task(self._start_voice_loop())
        except Exception as exc:
            logger.exception("[TELNYX] stream start failed control=%s: %s", self.call_control_id, exc)
            if self.call_control_id:
                telnyx_call_registry.upsert(
                    self.call_control_id,
                    {"status": "stream-error", "last_event": "stream-error", "error": str(exc)[:200]},
                )
            raise

    async def _start_voice_loop(self) -> None:
        if not self._voice:
            return
        try:
            skip_greeting = bool(
                self._client_meta.get("skip_greeting")
                or self._client_meta.get("test_mode") == "cartesia_bilingual"
            )
            await self._voice.start_call(play_greeting=bool(self.call_id) and not skip_greeting)
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
            from server.services.audio_transcode import pcm_resample

            pcm = wire
            if self._wire_sample_rate != _WIRE_SAMPLE_RATE:
                pcm = pcm_resample(pcm, self._wire_sample_rate, _WIRE_SAMPLE_RATE)
        elif self._wire_codec == "PCMU":
            pcm = mulaw_to_pcm16(wire, target_rate=_WIRE_SAMPLE_RATE)
        elif self._wire_codec == "PCMA":
            pcm = alaw_to_pcm16(wire, target_rate=_WIRE_SAMPLE_RATE)
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
        """Send one RTP frame every 20ms — Telnyx drops/bursts mis-timed audio."""
        try:
            while not self._closed:
                try:
                    frame = await asyncio.wait_for(self._out_queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    continue
                chunk = frame.payload
                if frame.generation_id and frame.generation_id in self._invalid_generations:
                    pstn_media_flow.increment(
                        self.call_control_id or self.ws_id, "dropped_frames", 1
                    )
                    continue
                if frame.codec != self._negotiated_media.codec:
                    raise AssertionError(
                        f"outbound codec {frame.codec} != negotiated {self._negotiated_media.codec}"
                    )
                if len(chunk) != self._negotiated_media.frame_bytes:
                    raise AssertionError(
                        f"outbound frame {len(chunk)}B != expected {self._negotiated_media.frame_bytes}B"
                    )
                encoded = base64.b64encode(chunk).decode("ascii")
                message = json.dumps({"event": "media", "media": {"payload": encoded}})
                async with self._ws_send_lock:
                    await self.ws.send_text(message)
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
                await asyncio.sleep(0.02)
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
            raise

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

    async def _send_agent_wire(self, wire: bytes) -> None:
        """Enqueue Telnyx RTP payloads — or send MP3 blobs in mp3 bidirectional mode."""
        if self._bidirectional_mode == "mp3":
            await self._send_agent_mp3(wire)
            return
        source_codec = self._voice.current_output_codec if self._voice else "PCMU"
        target_codec = self._negotiated_media.codec
        if source_codec == "PCMU":
            source_chunks = chunk_mulaw_frames(wire, sample_rate=8000)
        elif source_codec == "L16":
            source_chunks = _chunk_l16_rtp(wire, self._negotiated_media.sample_rate)
        else:
            raise ValueError(f"unsupported TTS output codec {source_codec}")

        if source_codec in {"PCMU", "PCMA"} and target_codec in {"PCMU", "PCMA"}:
            chunks = [convert_g711(chunk, source_codec, target_codec) for chunk in source_chunks]
        elif source_codec == "L16" and target_codec in {"PCMU", "PCMA"}:
            pcmu_chunks = [
                pcm16_chunk_to_mulaw_frames(chunk, sample_rate=8000, frame_ms=20)[0]
                for chunk in source_chunks
            ]
            chunks = [convert_g711(chunk, "PCMU", target_codec) for chunk in pcmu_chunks]
        elif source_codec == "PCMU" and target_codec == "L16":
            from server.services.audio_transcode import pcm_resample

            chunks = [
                _chunk_l16_rtp(
                    pcm_resample(mulaw_to_pcm16(chunk, 8000), 8000, 16000),
                    16000,
                )[0]
                for chunk in source_chunks
            ]
        elif source_codec == target_codec:
            chunks = source_chunks
        else:
            raise ValueError(f"unsupported outbound conversion {source_codec}->{target_codec}")
        outbound_codec = target_codec
        assert outbound_codec == self._negotiated_media.codec
        assert self._negotiated_media.sample_rate in {8000, 16000}
        assert self._negotiated_media.channels == 1
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
            generation_id = self._voice.current_generation_id if self._voice else None
            frame = OutboundFrame(
                payload=chunk,
                codec=outbound_codec,
                turn_id=self._voice.current_turn_id if self._voice else None,
                generation_id=generation_id,
            )
            while self._out_queue.full():
                await asyncio.sleep(0.005)
                if generation_id and generation_id in self._invalid_generations:
                    pstn_media_flow.increment(
                        self.call_control_id or self.ws_id, "dropped_frames", 1
                    )
                    return
            if generation_id and generation_id in self._invalid_generations:
                pstn_media_flow.increment(self.call_control_id or self.ws_id, "dropped_frames", 1)
                return
            self._out_queue.put_nowait(frame)
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

    async def _barge_in(self) -> None:
        generation_id = self._voice.current_generation_id if self._voice else None
        if generation_id:
            self._invalid_generations.add(generation_id)
        interrupted = 0
        while True:
            try:
                self._out_queue.get_nowait()
                interrupted += 1
            except asyncio.QueueEmpty:
                break
        if interrupted:
            pstn_media_flow.increment(
                self.call_control_id or self.ws_id, "interrupted_frames", interrupted
            )
        pstn_media_flow.emit(
            self.call_control_id or self.ws_id,
            "queue_cleared",
            "outbound",
            turn_id=self._voice.current_turn_id if self._voice else None,
            generation_id=self._voice.current_generation_id if self._voice else None,
            frames=interrupted,
            queue_size=0,
            status="processing",
            detail="caller barge-in",
        )
        async with self._ws_send_lock:
            await self.ws.send_text(json.dumps({"event": "clear"}))

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
        if self._closed:
            return
        self._closed = True
        if self._out_task:
            self._out_task.cancel()
            try:
                await self._out_task
            except asyncio.CancelledError:
                pass
        if self._voice:
            await self._voice.close()
        if self.call_id:
            from server.call.call_lifecycle_service import call_lifecycle_service

            try:
                await call_lifecycle_service.end(self.call_id, reason="pstn_hangup")
            except Exception:
                pass
        if self.call_control_id:
            bidirectional_ok = self._media_frames_in > 0 and self._media_frames_out > 0
            active_telnyx_bridges.pop(self.call_control_id, None)
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


def _chunk_l16_rtp(pcm16: bytes, sample_rate: int = 16000) -> list[bytes]:
    frame_bytes = int(sample_rate * 20 / 1000) * 2
    chunks: list[bytes] = []
    for i in range(0, len(pcm16), frame_bytes):
        chunk = pcm16[i : i + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk = chunk + b"\x00" * (frame_bytes - len(chunk))
        chunks.append(chunk)
    return chunks
