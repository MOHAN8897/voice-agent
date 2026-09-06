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

# Disabled until live PSTN echo+hold is proven. The commit path below already
# matches browser rules (3 words, echo, 700 ms, 200 ms hold) so flipping this
# later does not re-introduce the 2-word energy barge.
ENABLE_PSTN_BARGE_IN = False
PSTN_BARGE_MIN_WORDS = 3
PSTN_BARGE_HOLD_S = 0.2
PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.7
PSTN_BARGE_DEBOUNCE_S = 0.8

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
    """Extract PSTN lifecycle + TTS options saved at outbound dial time.

    Any explicit source_session_id (including test-studio) is used for brain/stack/TTS.
    Validation scripts omit source_session_id and stay tier-only.
    """
    source = str(local.get("source_session_id") or "").strip()
    inherit = bool(local.get("inherit_test_studio_config"))
    config_session_id: str | None = None
    if inherit:
        config_session_id = source or "test-studio"
    elif source:
        config_session_id = source
    return {
        "stack_override": local.get("stack_override"),
        "language": local.get("language"),
        "tts_session_id": config_session_id,
        "config_session_id": config_session_id,
    }


def pstn_turn_runtime(config_session_id: str | None, session_id: str) -> dict[str, Any]:
    """LLM fine-tune from Test Studio / source session — same keys the browser /api/brain path uses."""
    from server.services.runtime_settings import runtime_settings

    rt = runtime_settings.get(config_session_id or session_id)
    return {
        "openai_model": rt.get("openaiModel"),
        "temperature": rt.get("openaiTemperature"),
        "reasoning_effort": rt.get("openaiReasoningEffort"),
        "max_output_tokens": rt.get("openaiMaxTokens"),
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
        config_session_id: str | None = None,
        tts_output_codec: str = "mulaw",
        is_agent_audio_active: Callable[[], bool] | None = None,
    ) -> None:
        self.session_id = session_id
        self.call_id = call_id
        self.config_session_id = config_session_id
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
        self._active_tts_session = None
        self._pending_transcript: str | None = None
        self.current_output_codec = "L16" if sample_rate >= TELNYX_PCM_SAMPLE_RATE else "PCMU"
        self._last_barge_at = 0.0
        self._on_remote_hangup: Callable[[], Awaitable[None]] | None = None
        self._last_tts_text = ""
        self._tts_started_at = 0.0
        self._partial_started_at = 0.0

    def set_barge_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_barge = fn

    def set_hangup_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_remote_hangup = fn

    def _should_commit_barge(self, text: str) -> bool:
        if not ENABLE_PSTN_BARGE_IN:
            return False
        now = time.monotonic()
        speaking = self._agent_speaking or (
            self.is_agent_audio_active is not None and self.is_agent_audio_active()
        )
        if not speaking:
            self._partial_started_at = 0.0
            return False
        if now - self._last_barge_at < PSTN_BARGE_DEBOUNCE_S:
            return False
        if self._tts_started_at and now - self._tts_started_at < PSTN_BARGE_MIN_AFTER_SPEAK_S:
            return False
        words = len((text or "").split())
        if words < PSTN_BARGE_MIN_WORDS:
            self._partial_started_at = 0.0
            return False
        if self._partial_started_at <= 0:
            self._partial_started_at = now
            return False
        if now - self._partial_started_at < PSTN_BARGE_HOLD_S:
            return False
        from server.services.echo_guard import is_likely_echo

        if is_likely_echo(text, self._last_tts_text):
            return False
        return True

    async def _send_tts_text(self, session: Any, text: str) -> None:
        from server.services.spoken_numbers import expand_spoken_numbers

        expanded = expand_spoken_numbers(text or "")
        if not expanded.strip():
            return
        if self._tts_started_at <= 0:
            self._tts_started_at = time.monotonic()
        self._last_tts_text = (self._last_tts_text + " " + expanded).strip()[-800:]
        await session.send_text(expanded)

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
        from server.services.runtime_settings import runtime_settings
        from server.services.voice_stt_runtime import (
            effective_stt_mode,
            effective_stt_silence_ms,
            effective_stt_stream_type,
        )

        lang = self._resolve_language()
        rt = runtime_settings.get(self.config_session_id or self.session_id)
        stream_type = effective_stt_stream_type(str(rt.get("sttStreamType") or "fast"))
        mode = effective_stt_mode(str(rt.get("sttMode") or "transcribe"))
        silence_ms = effective_stt_silence_ms(rt)
        threshold_val = rt.get("sttThreshold")
        self._stt_cm = _connect_stt_upstream(
            session_id=self.config_session_id or self.session_id,
            call_id=self.call_id,
            language_code=lang,
            sample_rate=self.sample_rate,
            stream_type=stream_type,
            mode=mode,
            silence_duration_ms=silence_ms,
            threshold=float(threshold_val) if threshold_val is not None else None,
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
                    if text and self.call_id:
                        from server.call.call_context import get as get_ctx

                        ctx = get_ctx(self.call_id)
                        if ctx:
                            ctx.last_stt_partial_at = time.monotonic()
                    if self._should_commit_barge(text):
                        now = time.monotonic()
                        self._last_barge_at = now
                        self._partial_started_at = 0.0
                        log_pstn("barge_in", call_id=self.call_id)
                        from server.agent.conversation_manager import conversation_manager

                        conversation_manager.note_barge(self.session_id, self._last_tts_text)
                        if self.call_id:
                            from server.call.call_context import get as get_ctx

                            ctx = get_ctx(self.call_id)
                            if ctx:
                                ctx.barge_in_flight = True
                                ctx.agent_hangup_armed = False
                        if self._on_barge:
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
                    if text and self._turn_busy:
                        self._pending_transcript = text
                    elif text and not self._turn_busy:
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
            from server.services.pstn_turn_tts import PstnTurnTtsSession

            pending = ""
            spoke_from_stream = False
            accepted_end_call = False
            llm_rt = pstn_turn_runtime(self.config_session_id, self.session_id)
            self.current_generation_id = uuid.uuid4().hex[:12]
            self._last_tts_text = ""
            self._tts_started_at = 0.0
            tts_session = PstnTurnTtsSession(self)
            self._active_tts_session = tts_session
            async with self._speak_lock:
                self._active_speak_task = asyncio.current_task()
                await tts_session.open()
            try:
                async for chunk in live_turn_orchestrator.handle_user_turn_stream(
                    transcript=text,
                    language_code=self._resolve_language(),
                    session_id=self.session_id,
                    call_id=self.call_id,
                    openai_model=llm_rt.get("openai_model"),
                    temperature=llm_rt.get("temperature"),
                    reasoning_effort=llm_rt.get("reasoning_effort"),
                    max_output_tokens=llm_rt.get("max_output_tokens"),
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
                        sentences, pending = drain_complete_sentences(
                            pending,
                            allow_first_fast=not spoke_from_stream,
                        )
                        for sent in sentences:
                            await self._send_tts_text(tts_session, sent)
                            spoke_from_stream = True
                    elif chunk.get("done"):
                        tail = resolve_stream_tts_tail(
                            pending,
                            chunk.get("text") or "",
                            spoke_from_stream=spoke_from_stream,
                        )
                        if tail:
                            await self._send_tts_text(tts_session, tail)
                        pending = ""
                        end_call = chunk.get("end_call") or {}
                        accepted_end_call = bool(
                            isinstance(end_call, dict) and end_call.get("should_end")
                        )
                if spoke_from_stream or tts_session.has_sent_text:
                    await tts_session.finish()
                if accepted_end_call and self.call_id:
                    from server.call.call_lifecycle_service import call_lifecycle_service

                    await call_lifecycle_service.end(self.call_id, reason="agent_hangup")
                    self._pending_transcript = None
                    if self._on_remote_hangup:
                        try:
                            await self._on_remote_hangup()
                        except Exception as exc:
                            log_pstn("hangup.provider.failed", call_id=self.call_id, error=str(exc)[:200])
                    return
            finally:
                await tts_session.close()
                self._active_tts_session = None
                self._active_speak_task = None
                self.current_generation_id = None
        except Exception as e:
            logger.warning("[PSTN] turn error: %s", str(e)[:300])
            log_pstn("turn.error", call_id=self.call_id, error=str(e)[:200])
        finally:
            self._turn_busy = False
            log_pstn("turn.done", timer_key=self.call_id, call_id=self.call_id, turn_id=self.current_turn_id)
            self.current_turn_id = None
            pending = self._pending_transcript
            self._pending_transcript = None
            if pending:
                asyncio.create_task(self._run_turn(pending))

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

    async def speak(
        self,
        text: str,
        *,
        speaker: str | None = None,
        language_code: str | None = None,
    ) -> None:
        if not text or self._closed:
            return
        from server.services.pstn_turn_tts import PstnTurnTtsSession

        async with self._speak_lock:
            self._active_speak_task = asyncio.current_task()
            self.current_generation_id = uuid.uuid4().hex[:12]
            session = PstnTurnTtsSession(self)
            self._active_tts_session = session
            try:
                await session.open(speaker=speaker, language_code=language_code)
                self._last_tts_text = ""
                self._tts_started_at = 0.0
                await self._send_tts_text(session, text)
                await session.finish()
            finally:
                await session.close()
                self._active_tts_session = None
                self._active_speak_task = None
                self.current_generation_id = None

    async def interrupt_tts(self) -> None:
        session = self._active_tts_session
        if session is not None:
            log_pstn(
                "tts.interrupt",
                call_id=self.call_id,
                turn_id=self.current_turn_id,
                generation_id=self.current_generation_id,
            )
            await session.interrupt()
            self._active_tts_session = None
        task = self._active_speak_task
        if task and task is not asyncio.current_task() and not task.done():
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
