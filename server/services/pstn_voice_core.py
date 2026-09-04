"""Shared PSTN voice loop — STT → brain → TTS (used by Exotel/Telnyx/Plivo bridges)."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from server.services.audio_transcode import chunk_mulaw_frames, chunk_pcm16_frames
from server.services.pstn_debug import log_pstn
from server.services.pstn_media_flow import pstn_media_flow
from server.services.pstn_text_chunker import (
    drain_complete_sentences,
    extract_opening_greeting,
    resolve_stream_tts_tail,
)
from server.utils.logger import log_error, log_stt, log_tts

logger = logging.getLogger(__name__)

OnAgentWire = Callable[[bytes], Awaitable[None]]

# Enabled after TEST 5–6 passed (Telnyx clear + local TTS stop on caller interrupt).
ENABLE_PSTN_BARGE_IN = True

# PSTN telephony: 8 kHz (Exotel/Plivo μ-law) or 16 kHz (Telnyx L16).
PSTN_SAMPLE_RATE = 8000
TELNYX_PCM_SAMPLE_RATE = 16000
_MULAW_FRAME_BYTES = 160  # 20 ms μ-law @ 8 kHz


def pstn_wire_mode(tts_output_codec: str, sample_rate: int) -> str:
    if tts_output_codec == "mp3":
        return "mp3"
    if tts_output_codec == "linear16" and sample_rate >= TELNYX_PCM_SAMPLE_RATE:
        return "rtp_l16"
    return "rtp_mulaw"


def pstn_frame_bytes(wire_mode: str, sample_rate: int) -> int:
    if wire_mode == "rtp_mulaw":
        return _MULAW_FRAME_BYTES
    return int(sample_rate * 20 / 1000) * 2


def pstn_call_options(local: dict[str, Any]) -> dict[str, Any]:
    """Extract PSTN lifecycle + TTS options saved at outbound dial time."""
    source = str(local.get("source_session_id") or "").strip()
    # Browser Test Studio session is not used for PSTN TTS/runtime lookup.
    tts_session_id = source if source and source != "test-studio" else None
    return {
        "stack_override": local.get("stack_override"),
        "language": local.get("language"),
        "tts_session_id": tts_session_id,
    }


class PstnVoiceLoop:
    def __init__(
        self,
        *,
        session_id: str,
        call_id: str | None,
        on_agent_wire: OnAgentWire,
        sample_rate: int = PSTN_SAMPLE_RATE,
        tts_session_id: str | None = None,
        tts_output_codec: str = "mulaw",
        is_agent_audio_active: Callable[[], bool] | None = None,
    ) -> None:
        self.session_id = session_id
        self.call_id = call_id
        self.tts_session_id = tts_session_id or session_id
        self.on_agent_wire = on_agent_wire
        self.sample_rate = sample_rate
        self.tts_output_codec = tts_output_codec
        self.is_agent_audio_active = is_agent_audio_active
        self._stt_cm = None
        self._stt = None
        self._stt_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._stt_frames_in = 0
        self._agent_speaking = False
        self._turn_busy = False
        self._closed = False
        self._on_barge: Callable[[], Awaitable[None]] | None = None
        self._speak_lock = asyncio.Lock()
        self._wire_frames_out = 0
        self._wire_bytes_out = 0
        self.current_turn_id: str | None = None
        self.current_generation_id: str | None = None
        self._active_speak_task: asyncio.Task | None = None
        self.current_output_codec = "L16" if sample_rate >= TELNYX_PCM_SAMPLE_RATE else "PCMU"
        self._last_barge_at = 0.0

    def set_barge_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_barge = fn

    def _resolve_language(self) -> str:
        if not self.call_id:
            return "te-IN"
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id)
        if ctx and ctx.resolved_stack:
            return ctx.resolved_stack.language or "te-IN"
        return "te-IN"

    async def start_call(self, *, play_greeting: bool = True) -> None:
        """Open STT, set archive sample rate, optional agent opening line."""
        log_pstn(
            "lifecycle.started",
            call_id=self.call_id,
            session_id=self.session_id,
            sample_rate=self.sample_rate,
            tts_codec=self.tts_output_codec,
            play_greeting=play_greeting,
        )
        if self.call_id:
            from server.call.audio_archive import audio_archive

            audio_archive.set_agent_sample_rate(self.call_id, self.sample_rate)
        try:
            await self.open_stt()
        except Exception as exc:
            log_pstn("stt.open.failed", call_id=self.call_id, error=str(exc)[:200])
            log_error("PSTN STT open failed", call_id=self.call_id, detail=str(exc)[:300])
            raise
        if not play_greeting or not self.call_id:
            return
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id)
        greeting = extract_opening_greeting(
            ctx.compiled_brain_text if ctx else None,
            self._resolve_language(),
        )
        if greeting:
            log_pstn("greeting.start", call_id=self.call_id, chars=len(greeting))
            log_tts("PSTN greeting", call_id=self.call_id, chars=len(greeting))
            await self.speak(greeting)
            log_pstn("greeting.done", timer_key=self.call_id, call_id=self.call_id)
        else:
            log_pstn("greeting.skip", call_id=self.call_id, reason="no_opening_line")

    async def open_stt(self) -> None:
        from server.routes.ws import _connect_stt_upstream

        lang = self._resolve_language()
        self._stt_cm = _connect_stt_upstream(
            session_id=self.session_id,
            call_id=self.call_id,
            language_code=lang,
            sample_rate=self.sample_rate,
        )
        self._stt = await self._stt_cm.__aenter__()
        self._stt_task = asyncio.create_task(self._stt_reader())
        self._ping_task = asyncio.create_task(self._stt_ping())
        log_pstn("stt.open", call_id=self.call_id, language=lang, sample_rate=self.sample_rate)

    async def _stt_ping(self) -> None:
        while not self._closed and self._stt:
            await asyncio.sleep(20)
            try:
                await self._stt.send(json.dumps({"event": "ping"}))
            except Exception:
                return

    async def _stt_reader(self) -> None:
        assert self._stt is not None
        try:
            async for raw in self._stt:
                if isinstance(raw, bytes):
                    raw = raw.decode(errors="ignore")
                msg = json.loads(raw)
                ev = msg.get("event") or msg.get("type") or ""
                if ev == "error":
                    log_pstn("stt.error", call_id=self.call_id, detail=str(msg)[:200])
                    log_error("PSTN STT error", call_id=self.call_id, detail=str(msg)[:300])
                elif ev == "transcript.partial":
                    text = (msg.get("text") or (msg.get("data") or {}).get("text") or "").strip()
                    if ENABLE_PSTN_BARGE_IN:
                        now = time.monotonic()
                        if (
                            text
                            and (
                                self._agent_speaking
                                or (self.is_agent_audio_active and self.is_agent_audio_active())
                            )
                            and len(text.split()) >= 2
                            and self._on_barge
                            and now - self._last_barge_at >= 0.75
                        ):
                            self._last_barge_at = now
                            log_pstn("barge_in", call_id=self.call_id)
                            await self._on_barge()
                            await self.interrupt_tts()
                elif ev == "transcript.final":
                    text = (msg.get("text") or (msg.get("data") or {}).get("text") or "").strip()
                    if text:
                        safe = text[:120].encode("ascii", "replace").decode("ascii")
                        log_pstn("stt.transcript", call_id=self.call_id, text=safe)
                        log_stt("PSTN transcript final", call_id=self.call_id, text=safe)
                        if self.call_id:
                            pstn_media_flow.emit(
                                self.call_id,
                                "stt_final",
                                "inbound",
                                turn_id=self.current_turn_id,
                                status="healthy",
                                detail=text[:120],
                            )
                    if text and not self._turn_busy:
                        asyncio.create_task(self._run_turn(text))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log_pstn("stt.reader.failed", call_id=self.call_id, error=str(e)[:200])
            logger.warning("[PSTN] stt reader: %s", str(e)[:200])

    async def feed_user_pcm16(self, pcm16: bytes) -> None:
        if not self._stt or not pcm16:
            return
        if self.call_id:
            from server.call.audio_archive import audio_archive

            asyncio.create_task(audio_archive.append_user_pcm(self.call_id, pcm16))
        b64 = base64.b64encode(pcm16).decode()
        try:
            await self._stt.send(json.dumps({"event": "audio_input", "audio": b64}))
        except Exception as exc:
            log_pstn("stt.send.failed", call_id=self.call_id, error=str(exc)[:200])
            return
        self._stt_frames_in += 1
        if self._stt_frames_in == 1:
            log_pstn("stt.first_audio", timer_key=self.call_id, call_id=self.call_id, bytes=len(pcm16))
            log_stt("PSTN first audio to STT", call_id=self.call_id, bytes=len(pcm16))
        elif self._stt_frames_in in (50, 200, 500):
            log_pstn("stt.audio.progress", call_id=self.call_id, frames_in=self._stt_frames_in)

    async def _run_turn(self, text: str) -> None:
        if self._turn_busy:
            return
        if not self.call_id:
            logger.warning("[PSTN] transcript ignored — no call_id (agent not linked)")
            return
        self._turn_busy = True
        self.current_turn_id = uuid.uuid4().hex[:12]
        safe = text[:120].encode("ascii", "replace").decode("ascii")
        log_pstn("turn.start", call_id=self.call_id, turn_id=self.current_turn_id, text=safe)
        pstn_media_flow.emit(
            self.call_id,
            "llm_started",
            "outbound",
            turn_id=self.current_turn_id,
            status="processing",
            detail=text[:200],
        )
        try:
            from server.call.live_turn_orchestrator import live_turn_orchestrator

            pending = ""
            spoke_from_stream = False
            async for chunk in live_turn_orchestrator.handle_user_turn_stream(
                transcript=text,
                session_id=self.session_id,
                call_id=self.call_id,
            ):
                if chunk.get("delta"):
                    if not pending:
                        pstn_media_flow.emit(
                            self.call_id,
                            "llm_first_token",
                            "outbound",
                            turn_id=self.current_turn_id,
                            status="healthy",
                        )
                    pending += chunk.get("delta") or ""
                    sentences, pending = drain_complete_sentences(pending)
                    for sent in sentences:
                        await self.speak(sent)
                        spoke_from_stream = True
                elif chunk.get("done"):
                    tail = resolve_stream_tts_tail(
                        pending,
                        chunk.get("text") or "",
                        spoke_from_stream=spoke_from_stream,
                    )
                    if tail:
                        await self.speak(tail)
                    pending = ""
        except Exception as e:
            logger.warning("[PSTN] turn error: %s", str(e)[:300])
            log_pstn("turn.error", call_id=self.call_id, error=str(e)[:200])
        finally:
            self._turn_busy = False
            log_pstn("turn.done", timer_key=self.call_id, call_id=self.call_id, turn_id=self.current_turn_id)
            self.current_turn_id = None

    async def _emit_agent_wire(self, wire: bytes) -> None:
        if not wire:
            return
        self._agent_speaking = True
        self._wire_frames_out += 1
        self._wire_bytes_out += len(wire)
        if self.call_id:
            from server.call.audio_archive import audio_archive

            asyncio.create_task(audio_archive.append_agent_audio(self.call_id, wire))
        await self.on_agent_wire(wire)
        self._agent_speaking = False

    async def _tts_ping(self, tts) -> None:
        while not self._closed:
            await asyncio.sleep(20)
            try:
                await tts.send(json.dumps({"type": "ping"}))
            except Exception:
                return

    def _tts_is_completion(self, msg_type: str, data: Any) -> bool:
        if msg_type in ("end_of_stream", "done", "complete", "completion"):
            return True
        if msg_type != "event":
            return False
        if not isinstance(data, dict):
            return False
        event_type = str(data.get("event_type") or data.get("type") or "")
        return event_type in ("final", "completion", "end", "done")

    async def speak(
        self,
        text: str,
        *,
        speaker: str | None = None,
        language_code: str | None = None,
    ) -> None:
        if not text or self._closed:
            return
        async with self._speak_lock:
            self._active_speak_task = asyncio.current_task()
            self.current_generation_id = uuid.uuid4().hex[:12]
            from server.routes.ws import _connect_tts_upstream
            from server.services.tts_config import merge_pstn_tts_config

            use_mp3 = self.tts_output_codec == "mp3"
            wire_mode = pstn_wire_mode(self.tts_output_codec, self.sample_rate)
            use_mulaw_wire = wire_mode == "rtp_mulaw"
            use_l16_wire = wire_mode == "rtp_l16"
            frame_bytes = pstn_frame_bytes(wire_mode, self.sample_rate)
            tts_audio_bytes = 0
            tts_ws_msgs = 0
            try:
                lang = language_code or self._resolve_language()
                client_data: dict[str, Any] = {"language_code": lang}
                if speaker:
                    client_data["speaker"] = speaker
                merged = merge_pstn_tts_config(
                    self.tts_session_id,
                    client_data,
                    call_id=self.call_id,
                    ws_model=None,
                    wire_mode=wire_mode,
                )
                model = str(merged.get("model") or "bulbul:v3")
                tts_cm = _connect_tts_upstream(model, session_id=self.tts_session_id, call_id=self.call_id)
                tts = await tts_cm.__aenter__()
                ping_task = asyncio.create_task(self._tts_ping(tts))
                if merged.get("provider") == "cartesia":
                    use_mulaw_wire = False
                    use_l16_wire = True
                    use_mp3 = False
                    frame_bytes = pstn_frame_bytes("rtp_l16", self.sample_rate)
                if use_mp3:
                    self.current_output_codec = "MP3"
                elif use_l16_wire:
                    self.current_output_codec = "L16"
                elif use_mulaw_wire:
                    self.current_output_codec = "PCMU"
                else:
                    self.current_output_codec = "L16"
                log_tts(
                    "PSTN speak config",
                    call_id=self.call_id,
                    speaker=merged.get("speaker"),
                    pace=merged.get("pace"),
                    model=model,
                    codec=merged.get("output_audio_codec"),
                    speech_sample_rate=merged.get("speech_sample_rate"),
                )
                log_pstn(
                    "tts.speak.start",
                    call_id=self.call_id,
                    turn_id=self.current_turn_id,
                    generation_id=self.current_generation_id,
                    chars=len(text),
                    speaker=merged.get("speaker"),
                    pace=merged.get("pace"),
                    codec=merged.get("output_audio_codec"),
                    speech_sample_rate=merged.get("speech_sample_rate"),
                    provider=merged.get("provider"),
                    text=text[:120].encode("ascii", "replace").decode("ascii"),
                )
                if self.call_id:
                    pstn_media_flow.emit(
                        self.call_id,
                        "tts_started",
                        "outbound",
                        turn_id=self.current_turn_id,
                        generation_id=self.current_generation_id,
                        codec=self.current_output_codec,
                        sample_rate=self.sample_rate,
                        channels=1,
                        status="processing",
                        detail=text[:200],
                    )
                await tts.send(
                    json.dumps(
                        {
                            "type": "config",
                            "data": {
                                k: v
                                for k, v in merged.items()
                                if k
                                not in {
                                    "provider",
                                    "model",
                                }
                            },
                        }
                    )
                )
                await tts.send(json.dumps({"type": "text", "data": {"text": text}}))
                await tts.send(json.dumps({"type": "flush"}))

                audio_buf = bytearray()
                first_chunk = True
                tts_rate = self.sample_rate
                async for raw in tts:
                    if self._closed:
                        break
                    if isinstance(raw, bytes):
                        raw = raw.decode(errors="ignore")
                    obj = json.loads(raw)
                    msg_type = obj.get("type") or obj.get("event") or ""
                    tts_ws_msgs += 1
                    if msg_type == "error":
                        log_error("PSTN TTS error", call_id=self.call_id, detail=str(obj)[:300])
                        log_pstn("tts.error", call_id=self.call_id, detail=str(obj)[:200])
                        break
                    data = obj.get("data")
                    if self._tts_is_completion(msg_type, data):
                        log_pstn("tts.complete", call_id=self.call_id, msg_type=msg_type)
                        break
                    audio_b64 = None
                    if isinstance(data, dict):
                        audio_b64 = data.get("audio")
                        rate_val = data.get("speech_sample_rate") or data.get("sample_rate")
                        if rate_val:
                            try:
                                tts_rate = int(rate_val)
                            except (TypeError, ValueError):
                                pass
                    audio_b64 = audio_b64 or obj.get("audio")
                    if msg_type == "chunk" and isinstance(data, str):
                        audio_b64 = data
                    if not audio_b64:
                        if tts_ws_msgs <= 3:
                            log_pstn(
                                "tts.ws.msg",
                                call_id=self.call_id,
                                msg_type=msg_type,
                                keys=list(obj.keys())[:8],
                            )
                        continue
                    audio = base64.b64decode(audio_b64)
                    tts_audio_bytes += len(audio)
                    if use_mulaw_wire:
                        from server.services.audio_transcode import pcm16_to_mulaw_8k

                        audio = pcm16_to_mulaw_8k(audio, source_rate=tts_rate)
                        tts_rate = 8000
                    if use_mp3:
                        if first_chunk and self.call_id:
                            pstn_media_flow.emit(
                                self.call_id,
                                "tts_audio",
                                "outbound",
                                turn_id=self.current_turn_id,
                                generation_id=self.current_generation_id,
                                codec="MP3",
                                sample_rate=tts_rate,
                                channels=1,
                                bytes=len(audio),
                                status="healthy",
                            )
                            log_pstn(
                                "tts.first_audio",
                                timer_key=self.call_id,
                                call_id=self.call_id,
                                bytes=len(audio),
                                codec="mp3",
                                tts_rate=tts_rate,
                            )
                            first_chunk = False
                        await self._emit_agent_wire(audio)
                        continue
                    if not use_mulaw_wire and not use_mp3 and tts_rate != self.sample_rate:
                        from server.services.audio_transcode import pcm_resample

                        audio = pcm_resample(audio, tts_rate, self.sample_rate)
                    audio_buf.extend(audio)
                    if first_chunk and self.call_id:
                        pstn_media_flow.emit(
                            self.call_id,
                            "tts_audio",
                            "outbound",
                            turn_id=self.current_turn_id,
                            generation_id=self.current_generation_id,
                            codec=self.current_output_codec,
                            sample_rate=self.sample_rate,
                            channels=1,
                            bytes=len(audio),
                            duration_ms=(
                                len(audio) * 1000 / self.sample_rate
                                if use_mulaw_wire
                                else len(audio) * 1000 / (self.sample_rate * 2)
                            ),
                            status="healthy",
                        )
                        first_chunk = False
                    while len(audio_buf) >= frame_bytes:
                        chunk = bytes(audio_buf[:frame_bytes])
                        del audio_buf[:frame_bytes]
                        if first_chunk:
                            log_pstn(
                                "tts.first_audio",
                                timer_key=self.call_id,
                                call_id=self.call_id,
                                bytes=len(chunk),
                                codec="mulaw" if use_mulaw_wire else "pcm16",
                                tts_rate=tts_rate,
                            )
                            log_tts("PSTN first audio", call_id=self.call_id, bytes=len(chunk))
                            first_chunk = False
                        await self._emit_agent_wire(chunk)
                if audio_buf:
                    tail = bytes(audio_buf)
                    if use_mulaw_wire:
                        for frame in chunk_mulaw_frames(tail, sample_rate=8000):
                            await self._emit_agent_wire(frame)
                    else:
                        for frame in chunk_pcm16_frames(tail, sample_rate=self.sample_rate):
                            await self._emit_agent_wire(frame)
            finally:
                ping_task.cancel()
                try:
                    await tts.close()
                except Exception:
                    pass
                try:
                    await tts_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                log_pstn(
                    "tts.speak.done",
                    call_id=self.call_id,
                    turn_id=self.current_turn_id,
                    generation_id=self.current_generation_id,
                    chars=len(text),
                    tts_audio_bytes=tts_audio_bytes,
                    wire_frames=self._wire_frames_out,
                    tts_ws_msgs=tts_ws_msgs,
                )
                self._active_speak_task = None
                self.current_generation_id = None
                self.current_output_codec = "L16" if self.sample_rate >= TELNYX_PCM_SAMPLE_RATE else "PCMU"

    async def interrupt_tts(self) -> None:
        task = self._active_speak_task
        if task and task is not asyncio.current_task() and not task.done():
            log_pstn(
                "tts.interrupt",
                call_id=self.call_id,
                turn_id=self.current_turn_id,
                generation_id=self.current_generation_id,
            )
            task.cancel()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        log_pstn(
            "lifecycle.closed",
            call_id=self.call_id,
            stt_frames_in=self._stt_frames_in,
            wire_frames_out=self._wire_frames_out,
        )
        for task in (self._stt_task, self._ping_task):
            if task:
                task.cancel()
        if self._stt:
            try:
                await self._stt.close()
            except Exception:
                pass
        if self._stt_cm:
            try:
                await self._stt_cm.__aexit__(None, None, None)
            except Exception:
                pass
