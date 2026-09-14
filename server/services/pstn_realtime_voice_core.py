"""PSTN Realtime audio E2E loop — Telnyx PCM ↔ OpenAI Realtime mini speech-to-speech."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from server.call.end_call_validate import (
    caller_asked_to_record_details,
    caller_firm_refusal,
    caller_requested_callback,
    caller_requested_hangup,
    looks_like_bare_name,
    validate_end_call,
)
from server.realtime.end_call_tool import parse_end_call_tool
from server.realtime.models import (
    REALTIME_PCM_RATE,
    realtime_voice_config,
    resolve_realtime_voice_max_output_tokens,
    resolve_realtime_voice_model,
)
from server.realtime.text_session import build_audio_session_instructions
from server.services.audio_transcode import StreamingPcmResampler, pcm16_to_mulaw
from server.services.echo_guard import is_likely_echo
from server.services.pstn_debug import log_pstn
from server.services.pstn_media_flow import pstn_media_flow
from server.services.pstn_text_chunker import extract_opening_greeting
from server.services.pstn_voice_core import (
    PHASE_CLOSING,
    PHASE_ENDED,
    PHASE_INTRO,
    PHASE_LISTENING,
    PHASE_SPEAKING,
    PSTN_AEC_QUIET_CLOSE_FRAMES,
    TELNYX_PCM_SAMPLE_RATE,
)

# Telnyx already separates inbound/outbound tracks; this gate only filters
# residual handset acoustic echo. Echo of our own greeting sits ~500–1400 RMS
# on some handsets — that must not PROVIDER_CLEAR live audio.
REALTIME_AEC_ENERGY_MIN = 1600
REALTIME_AEC_LOUD_OPEN_FRAMES = 4
_BARGE_HOLD_SEC = 2.5
_PICKUP_SUPPRESS_SEC = 1.8

# Later hello / are-you-there after the intro is an availability check, not a new opening.
_SIMPLE_HELLO_RE = re.compile(
    r"^(?:hello|hallo|hi+|hey|ഹലോ|హలో|हेलो|हैलो|नमस्ते)[.!?]*\s*$",
    re.I | re.UNICODE,
)
_AVAILABILITY_RE = re.compile(
    r"^(?:"
    r"(?:hello|hallo|hi+|hey)(?:\s+\w+){0,3}[.!?]*|"
    r"are you (?:still\s+)?(?:there|here)\??|"
    r"(?:you|u) (?:there|here)\??|"
    r"can you hear me\??|"
    r"(?:hello[,.\s]+)?(?:who(?:'s| is) this)\??|"
    r"ഹലോ[.!?]*|హలో[.!?]*|हेलो[.!?]*|हैलो[.!?]*|नमस्ते[.!?]*"
    r")\s*$",
    re.I | re.UNICODE,
)
_PICKUP_RE = re.compile(
    r"^(?:(?:yes|yeah|ya|ok|okay|hai)[,.\s]+)?"
    r"(?:hello|hallo|hi+|hey|ഹലോ|హలో)(?:[,.\s]+(?:who(?:'s| is) this))?[.!?]*$",
    re.I | re.UNICODE,
)
# Arabic / Persian / Urdu / Thai / Hangul / CJK with no Latin or Indic — overlap STT junk.
_FOREIGN_SCRIPT_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
    r"\u0E00-\u0E7F\uAC00-\uD7AF\u3040-\u30FF\u4E00-\u9FFF]"
)
_LATIN_OR_INDIC_RE = re.compile(
    r"[A-Za-z\u0900-\u097F\u0A80-\u0D7F]"
)
_REJECTED_END_CALL_FOLLOWUP = (
    "Stay on the line. Confirm or answer what they just said in one short sentence. "
    "Do not re-introduce yourself. Do not call end_call this turn."
)
_AVAILABILITY_FOLLOWUP = (
    "The caller is checking you are still on the line. "
    "Say only that you are here, then continue the current topic. "
    "Do not re-introduce yourself or restart the opening."
)
_UNCLEAR_NAME_FOLLOWUP = (
    "The last thing they said was their name, but it was unclear. "
    "Ask them to repeat their name only. Do not invent a name or a messaging app. "
    "Do not re-introduce yourself."
)


def _is_simple_hello(text: str) -> bool:
    return bool(_SIMPLE_HELLO_RE.fullmatch((text or "").strip()))


def _is_availability_check(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    return _is_simple_hello(t) or bool(_AVAILABILITY_RE.fullmatch(t))


def _is_pickup_phrase(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return _is_simple_hello(t) or bool(_PICKUP_RE.fullmatch(t)) or _is_availability_check(t)


def _is_line_check(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(
        re.fullmatch(
            r"(?:are you (?:still\s+)?(?:there|here)|(?:you|u) (?:there|here)|can you hear me)\??",
            t,
            flags=re.I,
        )
    )


def _is_foreign_script_junk(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_FOREIGN_SCRIPT_RE.search(t) and not _LATIN_OR_INDIC_RE.search(t))

logger = logging.getLogger(__name__)

OnAgentWire = Callable[[bytes], Awaitable[None]]


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def record_realtime_voice_usage(
    *,
    call_id: str | None,
    usage: dict[str, Any],
    llm_model: str,
    user_text: str = "",
    assistant_text: str = "",
    started_at: float | None = None,
) -> dict[str, Any] | None:
    """Persist OpenAI audio-token usage + USD/INR cost onto the call ledger."""
    if not call_id:
        return None
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.services.usage_pricing import estimate_turn_cost

    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cached_tokens = int(usage.get("cached_tokens") or 0)
    cache_write = int(usage.get("cache_write_tokens") or 0)
    input_audio = int(usage.get("input_audio_tokens") or 0)
    output_audio = int(usage.get("output_audio_tokens") or 0)
    if not any((input_tokens, output_tokens, input_audio, output_audio)):
        return None
    fx = float(get_settings().fx_rate_inr or 95.64)
    cost = estimate_turn_cost(
        stt_audio_sec=0,
        tts_chars=0,
        tts_provider="openai",
        llm_model=llm_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write,
        fx_rate_inr=fx,
        input_audio_tokens=input_audio,
        output_audio_tokens=output_audio,
    )
    meta = call_ledger.read_meta(call_id)
    prev = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    seq = int(prev.get("turns") or 0) + 1
    duration_sec = max(0.0, time.monotonic() - started_at) if started_at else 0.0
    minutes = duration_sec / 60.0 if duration_sec > 0 else 0.0
    total_usd = float(prev.get("cost_usd") or 0) + float(cost["total_usd"])
    total_inr = float(prev.get("cost_inr") or 0) + float(cost["total_inr"])
    turn = {
        "turn": seq,
        "user_text": user_text,
        "assistant_text": assistant_text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "cache_write_tokens": cache_write,
        "input_audio_tokens": input_audio,
        "output_audio_tokens": output_audio,
        "stt_final_ms": None,
        "llm_ttft_ms": None,
        "tts_first_audio_ms": None,
        "e2e_ms": None,
        "cost_usd": cost["total_usd"],
        "cost_inr": cost["total_inr"],
        "llm_usd": cost["llm_usd"],
        "pipeline": "realtime_voice",
        "llm_model": llm_model,
        "errors": [],
    }
    await call_ledger.append_trace_turn(call_id, turn)
    meta["usage"] = {
        "pipeline": "realtime_voice",
        "llm_model": llm_model,
        "input_tokens": int(prev.get("input_tokens") or 0) + input_tokens,
        "output_tokens": int(prev.get("output_tokens") or 0) + output_tokens,
        "input_audio_tokens": int(prev.get("input_audio_tokens") or 0) + input_audio,
        "output_audio_tokens": int(prev.get("output_audio_tokens") or 0) + output_audio,
        "cached_tokens": int(prev.get("cached_tokens") or 0) + cached_tokens,
        "turns": seq,
        "cost_usd": total_usd,
        "cost_inr": total_inr,
        "model_cost_usd": total_usd,
        "model_cost_inr": total_inr,
        "duration_sec": round(duration_sec, 3),
        "cost_usd_per_min": (total_usd / minutes) if minutes > 0 else 0.0,
        "cost_inr_per_min": (total_inr / minutes) if minutes > 0 else 0.0,
        "fx_rate_inr": fx,
    }
    call_ledger.write_meta(call_id, meta)
    return turn


class PstnRealtimeVoiceLoop:
    """Drop-in voice-loop surface for Telnyx/Exotel/Plivo without Sarvam STT/TTS."""

    def __init__(
        self,
        *,
        session_id: str,
        call_id: str | None,
        on_agent_wire: OnAgentWire,
        sample_rate: int = 8000,
        tts_session_id: str | None = None,
        config_session_id: str | None = None,
        tts_output_codec: str = "mulaw",
        is_agent_audio_active: Callable[[], bool] | None = None,
        playback: Any | None = None,
        stack_override: dict[str, Any] | None = None,
        adapter: Any | None = None,
    ) -> None:
        self.session_id = session_id
        self.call_id = call_id
        self.config_session_id = config_session_id
        self.tts_session_id = tts_session_id or session_id
        self.on_agent_wire = on_agent_wire
        self.sample_rate = int(sample_rate)
        self.tts_output_codec = tts_output_codec
        self.is_agent_audio_active = is_agent_audio_active
        self.playback = playback
        self.stack_override = stack_override or {}
        self._injected_adapter = adapter
        self._adapter: Any | None = None
        self._pump_task: asyncio.Task | None = None
        self._closed = False
        self._call_started = False
        self._phase = PHASE_LISTENING
        self._tts_active = False
        self._active_tts_session = None
        self._on_barge: Callable[[], Awaitable[None]] | None = None
        self._on_remote_hangup: Callable[[], Awaitable[None]] | None = None
        self._on_turn_audio_done: Callable[[], Awaitable[None]] | None = None
        self.current_turn_id: str | None = None
        self.current_generation_id: str | None = None
        self._barge_generation: str | None = None
        self.current_output_codec = "L16" if self.sample_rate >= TELNYX_PCM_SAMPLE_RATE else "PCMU"
        self._in_resampler = StreamingPcmResampler(self.sample_rate, REALTIME_PCM_RATE)
        self._out_resampler = StreamingPcmResampler(REALTIME_PCM_RATE, self.sample_rate)
        self._out_pcm = bytearray()
        self._wire_frames_out = 0
        self._user_partial = ""
        self._assistant_text = ""
        self._response_had_audio = False
        self._pending_end_call: dict[str, Any] | None = None
        self._pending_followup_instruction: str | None = None
        self._pending_farewell_text: str | None = None
        self._farewell_response_active = False
        self._callback_request_text = ""
        self._callback_collecting_field: str | None = None
        self._callback_details: dict[str, str] = {}
        self._callback_close_phase = "idle"
        self._hangup_started = False
        self._stt = None
        self._live_model = ""
        self._voice_name = ""
        self._started_at: float | None = None
        self._intro_noted = False
        self._deferred_greeting_frames: list[bytes] | None = None
        self._deferred_greeting_text: str | None = None
        self._deferred_greeting_armed = False
        self._deferred_greeting_playing = False
        self._deferred_greeting_task: asyncio.Task | None = None
        self._tts_started_emitted = False
        self._aec_loud_streak = 0
        self._aec_quiet_streak = 0
        self._aec_barge_open = False
        self._cleared_input_for_turn = False
        self._response_open = False
        self._suppress_until_user = False
        self._openai_response_id = ""
        self._followup_inflight = False
        self._heard_user_turn = False
        self._heard_content_turn = False
        self._barge_hold_until = 0.0
        self._pickup_suppress_until = 0.0
        from server.services.pstn_archive_writer import PstnArchiveWriter

        self._archive = PstnArchiveWriter()

    def emission_blocked(self) -> bool:
        if self._closed or self._phase == PHASE_ENDED:
            return True
        gen = self.current_generation_id
        if self._barge_generation and gen and gen == self._barge_generation:
            return True
        if self.playback is not None and hasattr(self.playback, "is_generation_valid"):
            if gen and not self.playback.is_generation_valid(gen):
                return True
        return False

    def _promote_queued_tts_to_heard(self) -> None:
        return None

    def set_barge_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_barge = fn

    def set_hangup_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_remote_hangup = fn

    def set_turn_audio_done_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_turn_audio_done = fn

    def _set_phase(self, phase: str) -> None:
        if self._phase == PHASE_ENDED:
            return
        if self._phase == PHASE_CLOSING and phase not in (PHASE_CLOSING, PHASE_ENDED):
            if not (phase == PHASE_LISTENING and not self._hangup_started):
                return
        self._phase = phase

    def _set_tts_active(self, active: bool) -> None:
        self._tts_active = bool(active)

    def _agent_audio_playing(self) -> bool:
        if self._tts_active:
            return True
        if self.playback is not None and hasattr(self.playback, "is_active"):
            try:
                if self.playback.is_active():
                    return True
            except Exception:
                pass
        if self.is_agent_audio_active:
            try:
                return bool(self.is_agent_audio_active())
            except Exception:
                return False
        return False

    def _farewell_still_on_the_line(self) -> bool:
        """Playback still leaving the phone — same drain check as the classic PSTN hangup."""
        return self._agent_audio_playing()

    def _abort_in_progress_hangup(self) -> None:
        self._hangup_started = False
        self._pending_end_call = None
        self._pending_farewell_text = None
        self._farewell_response_active = False
        self._clear_hangup_arm()
        log_pstn("hangup.aborted_barge", call_id=self.call_id)
        self._set_phase(PHASE_LISTENING)

    def _clear_hangup_arm(self) -> None:
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id) if self.call_id else None
        if ctx:
            ctx.agent_hangup_armed = False
            ctx.barge_in_flight = False

    def _greeting_protected(self) -> bool:
        return bool(self._deferred_greeting_armed or self._deferred_greeting_playing)

    def _barge_hold_active(self) -> bool:
        return bool(self._barge_hold_until and time.monotonic() < self._barge_hold_until)

    def _pickup_suppressed(self) -> bool:
        return bool(self._pickup_suppress_until and time.monotonic() < self._pickup_suppress_until)

    def _event_response_id(self, event: dict[str, Any]) -> str:
        return str(event.get("response_id") or "").strip()

    def _is_stale_openai_event(self, event: dict[str, Any]) -> bool:
        rid = self._event_response_id(event)
        current = self._openai_response_id
        return bool(rid and current and rid != current)

    def _should_drop_user_final(self, text: str) -> bool:
        if not (text or "").strip():
            return True
        if _is_foreign_script_junk(text):
            return True
        if self._greeting_protected():
            return True
        if _is_pickup_phrase(text) or _is_availability_check(text):
            return False
        if self._aec_barge_open or self._barge_hold_active():
            return False
        if self._tts_active or self._agent_audio_playing():
            spoken = (self._assistant_text or self._deferred_greeting_text or "").strip()
            if spoken and is_likely_echo(text, spoken):
                return True
            words = [w for w in (text or "").split() if w]
            if len(words) <= 2 and not text.rstrip().endswith("?"):
                return True
            return False
        return False

    async def _commit_local_barge(self) -> None:
        """Cut agent audio as soon as local AEC commits a barge — do not wait for VAD."""
        if self._closed:
            return
        if self._greeting_protected():
            log_pstn("realtime_voice.barge_ignored_greeting", call_id=self.call_id)
            return
        self._barge_generation = self.current_generation_id
        self._suppress_until_user = False
        self._response_open = False
        self._followup_inflight = False
        self._barge_hold_until = time.monotonic() + _BARGE_HOLD_SEC
        if self._on_barge:
            try:
                await asyncio.wait_for(self._on_barge(), timeout=1.0)
            except Exception as exc:
                log_pstn("playback.remote_clear.failed", call_id=self.call_id, error=str(exc)[:160])
        await self.interrupt_tts()
        self._clear_hangup_arm()
        if self._hangup_started or self._phase == PHASE_CLOSING or self._farewell_response_active:
            self._abort_in_progress_hangup()
        else:
            self._set_phase(PHASE_LISTENING)

    async def _start_injected_response(self, instruction: str) -> None:
        if self._adapter is None or not (instruction or "").strip():
            return
        self._pending_followup_instruction = None
        self._suppress_until_user = False
        self._response_open = False
        self._followup_inflight = True
        self._assistant_text = ""
        await self._adapter.start_response(instructions=instruction)
        self._set_phase(PHASE_SPEAKING)

    async def _handle_pickup_or_availability(self, text: str, *, first_user: bool) -> None:
        """First hello is pickup (greeting already covers it). Later hello is availability."""
        if self._adapter is None:
            return
        try:
            await self._adapter.cancel_response()
        except Exception:
            pass
        who = bool(re.search(r"who(?:'s| is) this", text or "", flags=re.I))
        pickup = (first_user or (who and not self._heard_content_turn)) and not _is_line_check(text)
        if pickup:
            self._pickup_suppress_until = time.monotonic() + _PICKUP_SUPPRESS_SEC
            log_pstn("realtime_voice.pickup_consumed", call_id=self.call_id, text=(text or "")[:80])
            return
        if not self._intro_noted:
            return
        log_pstn("realtime_voice.availability_check", call_id=self.call_id, text=(text or "")[:80])
        try:
            await self._start_injected_response(_AVAILABILITY_FOLLOWUP)
        except Exception as exc:
            log_pstn(
                "realtime_voice.availability_followup.failed",
                call_id=self.call_id,
                error=str(exc)[:160],
            )
            self._pending_followup_instruction = _AVAILABILITY_FOLLOWUP

    def _resolve_language(self) -> str:
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id) if self.call_id else None
        if ctx and getattr(ctx, "resolved_stack", None):
            lang = getattr(ctx.resolved_stack, "language", None)
            if lang:
                return str(lang)
        return str(self.stack_override.get("language") or "te-IN")

    def _resolve_direction(self) -> str:
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id) if self.call_id else None
        raw = str(getattr(ctx, "direction", "") or self.stack_override.get("direction") or "")
        return "outbound" if raw.strip().lower() in ("outbound", "outgoing", "outbound-api") else "inbound"

    def _compiled_brain(self) -> str | None:
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id) if self.call_id else None
        return ctx.compiled_brain_text if ctx else None

    def _frame_bytes(self) -> int:
        if self.current_output_codec == "L16":
            return int(self.sample_rate * 0.02) * 2
        return 160

    async def start_call(
        self,
        *,
        play_greeting: bool = True,
        greeting_wire_frames: list[bytes] | None = None,
        greeting_text: str | None = None,
    ) -> None:
        if self._call_started:
            return
        self._call_started = True
        if self.call_id:
            from server.call.audio_archive import audio_archive

            audio_archive.set_agent_sample_rate(self.call_id, self.sample_rate)
        language = self._resolve_language()
        direction = self._resolve_direction()
        brain = self._compiled_brain()
        cfg = realtime_voice_config(self.stack_override)
        from server.call.call_context import get as get_ctx
        from server.realtime.voice_manager import realtime_voice_manager
        from server.services.runtime_settings import runtime_settings

        ctx = get_ctx(self.call_id) if self.call_id else None
        caller_id = getattr(ctx, "session_id", None)
        rt = runtime_settings.get(self.config_session_id or self.session_id)
        model = resolve_realtime_voice_model(self.stack_override, rt.get("openaiModel"))
        max_output_tokens = resolve_realtime_voice_max_output_tokens(rt.get("openaiMaxTokens"))
        self._live_model = model
        self._voice_name = str(cfg.get("voice") or "")
        self._started_at = time.monotonic()
        opening = greeting_text
        if opening is None and play_greeting:
            opening = extract_opening_greeting(brain, language, direction=direction)
        instructions = build_audio_session_instructions(
            brain,
            caller_id=str(caller_id or "") if direction == "inbound" else None,
            language=language,
            direction=direction,
            opening_greeting=opening,
        )
        adapter = self._injected_adapter
        if adapter is None and self.call_id:
            adapter = realtime_voice_manager.get(self.call_id)
        if adapter is None:
            adapter = await realtime_voice_manager.create(
                self.call_id or f"voice-{uuid.uuid4().hex[:10]}",
                instructions=instructions,
                compiled_brain=brain,
                model=model,
                language=language,
                voice=cfg["voice"],
                turn_detection=cfg["turn_detection"],
                stack_override=self.stack_override,
                max_output_tokens=max_output_tokens,
                wait_ready=True,
            )
        else:
            if not adapter.is_open():
                await adapter.connect(
                    model=model,
                    instructions=instructions,
                    voice=cfg["voice"],
                    turn_detection=cfg["turn_detection"],
                    vad_eagerness=cfg.get("vad_eagerness"),
                    noise_reduction=cfg.get("noise_reduction"),
                    speed=cfg.get("speed"),
                    silence_ms=cfg.get("silence_ms"),
                    max_output_tokens=max_output_tokens,
                )
                await adapter.wait_ready()
            else:
                updater = getattr(adapter, "update_instructions", None)
                if callable(updater):
                    await updater(instructions)
                elif hasattr(adapter, "instructions"):
                    adapter.instructions = instructions
        self._adapter = adapter
        if (
            play_greeting
            and direction == "outbound"
            and greeting_wire_frames
            and greeting_text
        ):
            self._deferred_greeting_frames = list(greeting_wire_frames)
            self._deferred_greeting_text = greeting_text.strip()
            self._deferred_greeting_armed = True
        elif play_greeting and direction == "outbound" and greeting_text and not greeting_wire_frames:
            log_pstn("greeting.deferred.miss", call_id=self.call_id, reason="no_prewarm_frames")
        if self._deferred_greeting_armed:
            auto_response = getattr(adapter, "set_auto_response", None)
            if callable(auto_response):
                await auto_response(False)
            else:
                # Without this control VAD can create a competing live reply.
                log_pstn(
                    "greeting.deferred.miss",
                    call_id=self.call_id,
                    reason="adapter_missing_auto_response_control",
                )
                self._deferred_greeting_frames = None
                self._deferred_greeting_text = None
                self._deferred_greeting_armed = False
        self._pump_task = asyncio.create_task(self._event_pump(), name=f"rt-voice-pump-{self.call_id}")
        log_pstn(
            "lifecycle.started",
            call_id=self.call_id,
            session_id=self.session_id,
            sample_rate=self.sample_rate,
            pipeline="realtime_voice",
            vad_mode="natural_vad",
            direction=direction,
            play_greeting=play_greeting,
            deferred_greeting=self._deferred_greeting_armed,
            deferred_frames=len(self._deferred_greeting_frames or []),
        )
        self._set_phase(PHASE_LISTENING)

    async def feed_user_pcm16(self, pcm16: bytes) -> None:
        if not pcm16 or self._closed or self._adapter is None:
            return
        raw = pcm16
        if self.call_id:
            self._archive.enqueue(self.call_id, "user", raw)
        # Handset echo of agent audio looks like the caller to OpenAI VAD and
        # cuts the reply. Hold inbound (do not append zeros — that can look like
        # speech_stopped and spawn an overlapping response) until the level is a barge.
        if self._agent_audio_playing():
            if self._greeting_protected():
                return
            try:
                from server.services.audio_transcode import pcm16_rms

                rms = pcm16_rms(raw)
                if rms >= REALTIME_AEC_ENERGY_MIN:
                    self._aec_loud_streak += 1
                    self._aec_quiet_streak = 0
                    if self._aec_loud_streak >= REALTIME_AEC_LOUD_OPEN_FRAMES:
                        if not self._aec_barge_open:
                            log_pstn(
                                "realtime_voice.barge_open",
                                call_id=self.call_id,
                                rms=round(rms, 1),
                            )
                            self._aec_barge_open = True
                            await self._commit_local_barge()
                        else:
                            self._aec_barge_open = True
                else:
                    self._aec_quiet_streak += 1
                    self._aec_loud_streak = 0
                    if self._aec_quiet_streak >= PSTN_AEC_QUIET_CLOSE_FRAMES:
                        self._aec_barge_open = False
                if not self._aec_barge_open:
                    return
            except Exception:
                return
        else:
            self._aec_loud_streak = 0
            self._aec_quiet_streak = 0
            self._aec_barge_open = False
        pcm24 = self._in_resampler.feed(pcm16)
        if not pcm24:
            return
        try:
            await self._adapter.append_pcm16(pcm24)
        except Exception as exc:
            log_pstn("realtime_voice.append.failed", call_id=self.call_id, error=str(exc)[:160])

    async def _event_pump(self) -> None:
        adapter = self._adapter
        if adapter is None:
            return
        try:
            async for event in adapter.events():
                if self._closed:
                    break
                await self._handle_event(event)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("[REALTIME_VOICE] pump failed: %s", str(exc)[:200])

    def _capture_callback_detail(self, text: str) -> None:
        value = (text or "").strip()
        if not value:
            return
        field = self._callback_collecting_field
        if field == "name":
            cleaned = re.sub(
                r"^(?:my name is|this is|i am|i'm|name is)\s+",
                "",
                value,
                flags=re.IGNORECASE,
            ).strip(" .,!?:;")
            if cleaned and not re.search(r"\d", cleaned) and len(cleaned.split()) <= 8:
                self._callback_details["name"] = cleaned
                self._callback_collecting_field = None
        elif field == "phone":
            digits = re.sub(r"\D", "", value)
            if 7 <= len(digits) <= 15:
                self._callback_details["phone"] = digits
                self._callback_collecting_field = None
            elif looks_like_bare_name(value):
                self._callback_details["name"] = value.strip(" .,!?:;")
        elif field == "timing":
            self._callback_details["timing"] = value[:120]
            self._callback_collecting_field = None

        explicit_name = re.search(
            r"\b(?:my name is|name is|this is)\s+([A-Za-z][A-Za-z .'-]{0,60})",
            value,
            re.IGNORECASE,
        )
        if explicit_name:
            self._callback_details["name"] = explicit_name.group(1).strip(" .,!?:;")
        digits = re.sub(r"\D", "", value)
        if 7 <= len(digits) <= 15:
            self._callback_details["phone"] = digits

    def _sync_callback_close_state(self):
        from server.call.callback_close import advance_callback_close
        from server.call.call_context import get as get_ctx
        from server.call.memory_manager import memory_manager

        ctx = get_ctx(self.call_id) if self.call_id else None
        snapshot = None
        if self.call_id:
            try:
                snapshot = memory_manager.get_snapshot(self.call_id)
            except Exception:
                snapshot = None
        state = advance_callback_close(
            ctx,
            self._user_partial,
            snapshot,
            extra_slots=self._callback_details,
            request_text=self._callback_request_text,
        )
        if caller_requested_callback(self._user_partial):
            self._callback_request_text = self._user_partial
        elif ctx and ctx.callback_request_text:
            self._callback_request_text = ctx.callback_request_text
        self._callback_close_phase = state.phase
        self._callback_collecting_field = state.missing
        if state.name:
            self._callback_details["name"] = state.name
        if state.phone:
            self._callback_details["phone"] = state.phone
        if state.when:
            self._callback_details["timing"] = state.when
        return state

    def _callback_missing_detail(self) -> str | None:
        return self._sync_callback_close_state().missing

    def _callback_followup_instruction(self, field: str) -> str:
        from server.call.callback_close import spoken_collect_instruction

        return spoken_collect_instruction(field, self._resolve_language())

    def _persist_callback_details(self) -> None:
        if not self.call_id or not self._callback_request_text:
            return
        try:
            from server.call.call_ledger import call_ledger
            from server.call.memory_manager import memory_manager

            meta = call_ledger.read_meta(self.call_id)
            snapshot = memory_manager.get_snapshot(self.call_id)
            facts = snapshot.get("facts") if isinstance(snapshot.get("facts"), dict) else {}
            from server.call.caller_detail_capture import is_usable_lead_name, is_usable_lead_phone

            name = (
                self._callback_details.get("name", "")
                or facts.get("name", "")
                or facts.get("caller_name", "")
            )
            if not is_usable_lead_name(str(name or "")):
                name = ""
            phone = (
                self._callback_details.get("phone", "")
                or facts.get("callback_phone", "")
                or facts.get("phone", "")
            )
            if not is_usable_lead_phone(str(phone or "")):
                phone = ""
            direction = str(meta.get("direction") or self._resolve_direction() or "")
            if (
                not phone
                and direction.strip().lower() not in ("outbound", "outgoing", "outbound-api")
                and not caller_asked_to_record_details(self._callback_request_text)
            ):
                ani = str(meta.get("caller_id") or "")
                phone = ani if is_usable_lead_phone(ani) else ""
            values = {
                "callback_requested": "true",
                "callback_time": self._callback_details.get("timing", ""),
                "name": name,
                "phone": phone,
            }
            operations = [
                {"op": "set_fact", "key": key, "value": str(value)}
                for key, value in values.items()
                if str(value).strip()
            ]
            turn_seq = 1 + sum(
                1 for row in call_ledger.read_lines(self.call_id) if row.get("role") == "user"
            )
            memory_manager.apply_proposals(
                self.call_id,
                operations,
                turn_seq=turn_seq,
                source="realtime_callback_gate",
            )
        except Exception as exc:
            log_pstn(
                "end_call.callback_memory_failed",
                call_id=self.call_id,
                error=str(exc)[:160],
            )

    async def _maybe_resume_callback_close(self) -> None:
        """If the caller asked to leave details / be contacted, keep collecting then hang up.

        The model often keeps pitching instead of calling end_call. Drive the close here.
        """
        if not self._callback_request_text:
            return
        if self._pending_end_call or self._pending_followup_instruction:
            return
        if self._farewell_response_active or self._hangup_started:
            return
        if caller_requested_hangup(self._user_partial) or caller_firm_refusal(self._user_partial):
            return
        state = self._sync_callback_close_state()
        spoken = self._assistant_text or ""
        asked = {
            "name": re.compile(
                r"\b(your name|may i have your name|name please|మీ పేరు|aapka naam)\b",
                re.I,
            ),
            "phone": re.compile(
                r"\b(phone(?: number)?|mobile number|best number|నంబర్|नंबर)\b",
                re.I,
            ),
        }
        if state.missing:
            self._callback_collecting_field = state.missing
            if asked.get(state.missing) and asked[state.missing].search(spoken):
                return
            self._pending_followup_instruction = self._callback_followup_instruction(state.missing)
            log_pstn("end_call.callback_prompted", call_id=self.call_id, missing=state.missing)
            return
        from server.call.end_call_validate import looks_like_question
        from server.call.hangup_judge import agent_spoke_closing

        if looks_like_question(spoken) or asked["phone"].search(spoken) or asked["name"].search(spoken):
            return
        if agent_spoke_closing(spoken):
            accepted = await self._gate_end_call_payload(
                {
                    "should_end": True,
                    "reason": "goal_complete",
                    "farewell": spoken,
                }
            )
            if accepted:
                self._pending_end_call = accepted
                self._pending_farewell_text = str(accepted.get("farewell") or "").strip()
            return
        self._pending_followup_instruction = (
            "The caller already asked to record their details and be contacted later. "
            "Confirm the callback in one short sentence, thank them, say goodbye, "
            "and call end_call with should_end true and reason goal_complete. Do not pitch."
        )

    async def _gate_end_call_payload(self, parsed: dict[str, Any]) -> dict[str, Any] | None:
        if not parsed.get("should_end"):
            return None
        if caller_requested_callback(self._user_partial):
            self._callback_request_text = self._user_partial
        state = self._sync_callback_close_state()
        callback_close = bool(
            self._callback_request_text
            and not caller_requested_hangup(self._user_partial)
            and not caller_firm_refusal(self._user_partial)
        )
        if callback_close:
            parsed = dict(parsed)
            parsed["reason"] = "goal_complete"
            if state.missing:
                self._callback_collecting_field = state.missing
                self._pending_followup_instruction = self._callback_followup_instruction(state.missing)
                log_pstn(
                    "end_call.callback_deferred",
                    call_id=self.call_id,
                    missing=state.missing,
                )
                return None
            self._persist_callback_details()

        from server.call.call_context import get as get_ctx
        from server.call.call_ledger import call_ledger
        from server.call.memory_manager import memory_manager

        ctx = get_ctx(self.call_id) if self.call_id else None
        snapshot = memory_manager.get_snapshot(self.call_id) if self.call_id else None
        completed = 0
        if self.call_id:
            completed = sum(
                1 for row in call_ledger.read_lines(self.call_id) if row.get("role") == "assistant"
            )
        evidence_user = self._callback_request_text if callback_close else self._user_partial
        decision = validate_end_call(
            parsed,
            user_text=evidence_user,
            language=self._resolve_language(),
            call_status=ctx.status if ctx else "active",
            already_armed=bool(ctx and ctx.agent_hangup_armed),
            barge_in_flight=bool(ctx and ctx.barge_in_flight),
            last_stt_partial_at=ctx.last_stt_partial_at if ctx else None,
            completed_turns=completed,
            memory_snapshot=snapshot,
            call_end_policy=ctx.call_end_policy if ctx else None,
            spoken_text=self._assistant_text,
            callback_close_phase=state.phase,
        )
        if not decision.accepted:
            log_pstn(
                "end_call.rejected",
                call_id=self.call_id,
                reason=decision.reason,
                code=decision.reject_code,
            )
            if (
                not self._pending_followup_instruction
                and not self._response_had_audio
                and not (self._assistant_text or "").strip()
            ):
                self._pending_followup_instruction = _REJECTED_END_CALL_FOLLOWUP
            return None
        if ctx:
            ctx.agent_hangup_armed = True
        farewell = decision.farewell
        if callback_close:
            name = self._callback_details.get("name", "").strip()
            timing = self._callback_details.get("timing", "").strip()
            if self._resolve_language().lower().startswith("en"):
                from server.call.caller_detail_capture import is_usable_lead_name

                if name and not is_usable_lead_name(name):
                    name = ""
                greeting = f"Thank you, {name}. " if name else "Thank you. "
                when = f" {timing}" if timing else ""
                farewell = (
                    f"{greeting}Your callback is confirmed. Our team will call you{when}. "
                    "Have a good day. Goodbye."
                )
        return {
            "should_end": True,
            "reason": decision.reason,
            "farewell": farewell,
        }

    async def _handle_event(self, event: dict[str, Any]) -> None:
        kind = str(event.get("type") or "")
        if kind == "speech_started":
            agent_out = self._tts_active or self._agent_audio_playing()
            if self._greeting_protected():
                log_pstn("realtime_voice.echo_ignore", call_id=self.call_id, reason="deferred_greeting")
                return
            if agent_out and not self._aec_barge_open:
                log_pstn("realtime_voice.echo_ignore", call_id=self.call_id)
                return
            self._suppress_until_user = False
            if agent_out:
                await self._commit_local_barge()
            else:
                self._set_phase(PHASE_LISTENING)
            return
        if kind == "speech_stopped":
            agent_out = self._tts_active or self._agent_audio_playing()
            if not (agent_out and not self._aec_barge_open):
                self._suppress_until_user = False
            if self._deferred_greeting_armed:
                self._schedule_deferred_greeting()
            return
        if kind == "user_transcript":
            text = str(event.get("text") or "").strip()
            if not text:
                return
            if event.get("final"):
                if self._should_drop_user_final(text):
                    log_pstn(
                        "realtime_voice.transcript_drop",
                        call_id=self.call_id,
                        text=text[:80],
                    )
                    return
                self._user_partial = text
                self._suppress_until_user = False
                first_user = not self._heard_user_turn
                self._heard_user_turn = True
                if not (_is_pickup_phrase(text) or _is_availability_check(text)):
                    self._heard_content_turn = True
                if caller_requested_callback(text):
                    self._callback_request_text = text
                self._capture_callback_detail(text)
                self._sync_callback_close_state()
                if self.call_id:
                    from server.call.caller_detail_capture import caller_detail_memory_operations
                    from server.call.call_ledger import call_ledger
                    from server.call.memory_manager import memory_manager

                    line = await call_ledger.append_user_turn(self.call_id, text)
                    detail_ops = caller_detail_memory_operations(text)
                    if detail_ops:
                        try:
                            memory_manager.apply_proposals(
                                self.call_id,
                                detail_ops,
                                turn_seq=int(line.get("seq") or 0),
                                source="realtime_caller_detail",
                            )
                        except Exception as exc:
                            log_pstn(
                                "realtime_voice.caller_detail_memory_failed",
                                call_id=self.call_id,
                                error=str(exc)[:160],
                            )
                pstn_media_flow.emit(
                    self.call_id or "",
                    "stt_final",
                    "inbound",
                    detail=text[:200],
                    turn_id=self.current_turn_id,
                )
                if self._adapter is not None:
                    from server.call.caller_detail_capture import unclear_name_phrase

                    if unclear_name_phrase(text):
                        log_pstn("realtime_voice.unclear_name", call_id=self.call_id)
                        try:
                            await self._adapter.cancel_response()
                        except Exception:
                            pass
                        try:
                            await self._start_injected_response(_UNCLEAR_NAME_FOLLOWUP)
                        except Exception as exc:
                            log_pstn(
                                "realtime_voice.unclear_name.failed",
                                call_id=self.call_id,
                                error=str(exc)[:160],
                            )
                            self._pending_followup_instruction = _UNCLEAR_NAME_FOLLOWUP
                    elif _is_pickup_phrase(text) or _is_availability_check(text):
                        await self._handle_pickup_or_availability(text, first_user=first_user)
            else:
                self._user_partial = text
            return
        if kind == "response_created":
            if (
                self._greeting_protected()
                or (self._pickup_suppressed() and not self._heard_content_turn)
            ) and self._adapter is not None:
                try:
                    await self._adapter.cancel_response()
                except Exception as exc:
                    log_pstn("greeting.deferred.cancel.failed", call_id=self.call_id, error=str(exc)[:160])
                if self._deferred_greeting_armed:
                    self._schedule_deferred_greeting()
                return
            if not self._intro_noted and self._deferred_greeting_frames and self._adapter is not None:
                try:
                    await self._adapter.cancel_response()
                except Exception as exc:
                    log_pstn("greeting.deferred.cancel.failed", call_id=self.call_id, error=str(exc)[:160])
                if self._deferred_greeting_armed:
                    self._schedule_deferred_greeting()
                return
            extra = (
                not self._followup_inflight
                and not self._aec_barge_open
                and not self._farewell_response_active
                and not self._pending_followup_instruction
                and (
                    self._suppress_until_user
                    or (self._response_open and self._response_had_audio)
                )
            )
            if extra and self._adapter is not None:
                log_pstn("realtime_voice.overlap_response_ignore", call_id=self.call_id)
                try:
                    await self._adapter.cancel_response()
                except Exception:
                    pass
                return
            self._followup_inflight = False
            self._suppress_until_user = False
            self._response_open = True
            self._barge_generation = None
            rid = self._event_response_id(event)
            if rid:
                self._openai_response_id = rid
            self.current_turn_id = self.current_turn_id or uuid.uuid4().hex[:12]
            self.current_generation_id = uuid.uuid4().hex[:12]
            self._assistant_text = ""
            self._response_had_audio = False
            self._out_pcm.clear()
            self._out_resampler.reset()
            self._tts_started_emitted = False
            self._cleared_input_for_turn = False
            if self.playback is not None and hasattr(self.playback, "set_current_generation"):
                self.playback.set_current_generation(self.current_generation_id)
            self._set_phase(PHASE_SPEAKING)
            pstn_media_flow.emit(self.call_id or "", "llm_started", "outbound", turn_id=self.current_turn_id)
            return
        if kind == "audio_delta":
            if self._is_stale_openai_event(event):
                return
            if self._deferred_greeting_playing:
                return
            if not self._intro_noted and self._deferred_greeting_frames:
                return
            pcm = event.get("pcm") or b""
            if pcm:
                self._response_had_audio = True
                if not self._cleared_input_for_turn and self._adapter is not None:
                    self._cleared_input_for_turn = True
                    clearer = getattr(self._adapter, "clear_input_audio", None)
                    if callable(clearer):
                        try:
                            await clearer()
                        except Exception:
                            pass
                self._set_tts_active(True)
                if not self._tts_started_emitted:
                    self._tts_started_emitted = True
                    pstn_media_flow.emit(
                        self.call_id or "",
                        "tts_started",
                        "outbound",
                        detail="openai-realtime",
                        turn_id=self.current_turn_id,
                    )
                pstn_media_flow.emit(
                    self.call_id or "",
                    "tts_audio",
                    "outbound",
                    bytes=len(pcm),
                    codec="pcm16",
                    sample_rate=REALTIME_PCM_RATE,
                    turn_id=self.current_turn_id,
                )
                await self._emit_realtime_pcm(pcm)
            return
        if kind == "assistant_transcript_delta":
            self._assistant_text += str(event.get("delta") or "")
            return
        if kind == "assistant_transcript":
            text = str(event.get("text") or "").strip()
            if text:
                self._assistant_text = text
            return
        if kind == "function_call":
            if str(event.get("name") or "") != "end_call":
                return
            parsed = parse_end_call_tool(event.get("arguments"))
            accepted: dict[str, Any] | None = None
            if parsed and parsed.get("should_end") and not self._farewell_response_active:
                accepted = await self._gate_end_call_payload(parsed)
                if accepted:
                    self._pending_end_call = accepted
                    self._pending_farewell_text = str(accepted.get("farewell") or "").strip()
            call_id = str(event.get("call_id") or "")
            if call_id and self._adapter is not None:
                try:
                    await self._adapter.submit_function_output(
                        call_id=call_id,
                        output=json.dumps(
                            {
                                "ok": bool(accepted or self._farewell_response_active),
                                "deferred": bool(self._pending_followup_instruction),
                                "missing": self._callback_collecting_field,
                            }
                        ),
                    )
                except Exception:
                    pass
            return
        if kind in ("response_done", "cancelled"):
            if self._is_stale_openai_event(event):
                return
            self._set_tts_active(False)
            if kind == "cancelled":
                self._response_open = False
                self._suppress_until_user = False
            if (
                kind == "response_done"
                and self._assistant_text.strip()
                and not self._intro_noted
                and not self._deferred_greeting_frames
            ):
                noter = getattr(self._adapter, "note_assistant_text", None) if self._adapter else None
                if callable(noter):
                    try:
                        await noter(self._assistant_text.strip())
                        self._intro_noted = True
                    except Exception as exc:
                        log_pstn(
                            "realtime_voice.note_assistant.failed",
                            call_id=self.call_id,
                            error=str(exc)[:160],
                        )
            if kind == "response_done" and self._assistant_text and self.call_id:
                from server.call.call_ledger import call_ledger

                await call_ledger.append_assistant_turn(self.call_id, self._assistant_text)
            if kind == "response_done":
                await self._maybe_resume_callback_close()
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            if usage and self.call_id:
                pstn_media_flow.emit(
                    self.call_id,
                    "llm_usage",
                    "outbound",
                    detail=str(usage.get("input_audio_tokens") or 0),
                    turn_id=self.current_turn_id,
                )
                if kind == "response_done":
                    try:
                        await record_realtime_voice_usage(
                            call_id=self.call_id,
                            usage=usage,
                            llm_model=self._live_model or "gpt-realtime-2.1-mini",
                            user_text=self._user_partial,
                            assistant_text=self._assistant_text,
                            started_at=self._started_at,
                        )
                    except Exception as exc:
                        log_pstn(
                            "realtime_voice.usage.failed",
                            call_id=self.call_id,
                            error=str(exc)[:160],
                        )
            if kind == "response_done" and self._pending_followup_instruction and self._adapter is not None:
                instruction = self._pending_followup_instruction
                await self._start_injected_response(instruction)
                return
            if kind == "response_done" and self._pending_end_call and not self._hangup_started:
                if self._farewell_response_active:
                    self._farewell_response_active = False
                    await self._finish_hangup()
                    return
                if (
                    not self._assistant_text.strip()
                    and not self._response_had_audio
                    and self._pending_farewell_text
                    and self._adapter is not None
                ):
                    farewell = self._pending_farewell_text
                    self._farewell_response_active = True
                    await self._start_injected_response(
                        f"Speak this farewell exactly, then stop: {farewell}"
                    )
                    return
                await self._finish_hangup()
                return
            if kind == "response_done":
                self._response_open = False
                if self._assistant_text.strip() or self._response_had_audio:
                    self._suppress_until_user = True
            if self._on_turn_audio_done:
                try:
                    await self._on_turn_audio_done()
                except Exception:
                    pass
            if self._phase != PHASE_ENDED:
                self._set_phase(PHASE_LISTENING)
            return
        if kind == "error":
            log_pstn("realtime_voice.error", call_id=self.call_id, error=str(event.get("message") or "")[:200])

    def _schedule_deferred_greeting(self) -> None:
        if not self._deferred_greeting_armed or self._closed:
            return
        task = self._deferred_greeting_task
        if task is not None and not task.done():
            return
        self._deferred_greeting_task = asyncio.create_task(
            self._on_first_user_speech_deferred_greeting(),
            name=f"rt-deferred-greeting-{self.call_id}",
        )

    async def _on_first_user_speech_deferred_greeting(self) -> None:
        if not self._deferred_greeting_armed or self._closed:
            return
        self._deferred_greeting_armed = False
        if self._adapter is not None:
            try:
                await self._adapter.cancel_response()
            except Exception as exc:
                log_pstn("greeting.deferred.cancel.failed", call_id=self.call_id, error=str(exc)[:160])
        await self._play_deferred_greeting()

    async def _play_deferred_greeting(self) -> None:
        frames = self._deferred_greeting_frames or []
        text = (self._deferred_greeting_text or "").strip()
        if not frames or not text or self._closed:
            return

        self._deferred_greeting_playing = True
        self._set_phase(PHASE_INTRO)
        self._set_tts_active(True)
        self.current_turn_id = self.current_turn_id or uuid.uuid4().hex[:12]
        self.current_generation_id = uuid.uuid4().hex[:12]
        if self.playback is not None and hasattr(self.playback, "set_current_generation"):
            self.playback.set_current_generation(self.current_generation_id)
        log_pstn(
            "greeting.deferred.play",
            call_id=self.call_id,
            frames=len(frames),
            chars=len(text),
        )
        try:
            for wire in frames:
                if self._closed:
                    break
                if self.call_id:
                    self._archive.enqueue(self.call_id, "agent", wire)
                self._wire_frames_out += 1
                await self.on_agent_wire(wire)
        finally:
            self._set_tts_active(False)
            self._deferred_greeting_playing = False

        if self._closed:
            return

        noter = getattr(self._adapter, "note_assistant_text", None) if self._adapter else None
        if callable(noter):
            try:
                await noter(text)
            except Exception as exc:
                log_pstn(
                    "realtime_voice.note_assistant.failed",
                    call_id=self.call_id,
                    error=str(exc)[:160],
                )
        self._intro_noted = True
        self._pickup_suppress_until = time.monotonic() + _PICKUP_SUPPRESS_SEC
        if self._adapter is not None:
            try:
                await self._adapter.cancel_response()
            except Exception as exc:
                log_pstn("greeting.deferred.cancel.failed", call_id=self.call_id, error=str(exc)[:160])
            clearer = getattr(self._adapter, "clear_input_audio", None)
            if callable(clearer):
                try:
                    await clearer()
                except Exception:
                    pass
        auto_response = getattr(self._adapter, "set_auto_response", None) if self._adapter else None
        if callable(auto_response):
            try:
                await auto_response(True)
            except Exception as exc:
                log_pstn(
                    "greeting.deferred.vad_restore.failed",
                    call_id=self.call_id,
                    error=str(exc)[:160],
                )
        if self.call_id:
            from server.call.call_ledger import call_ledger

            await call_ledger.append_assistant_turn(self.call_id, text)
        log_pstn("greeting.deferred.done", call_id=self.call_id)
        self._set_phase(PHASE_LISTENING)

    async def _emit_realtime_pcm(self, pcm24: bytes) -> None:
        if self.emission_blocked() or not pcm24:
            return
        pcm_out = self._out_resampler.feed(pcm24)
        if not pcm_out:
            return
        if self.current_output_codec == "PCMU":
            wire = pcm16_to_mulaw(pcm_out, sample_rate=self.sample_rate)
            self._out_pcm.extend(wire)
        else:
            self._out_pcm.extend(pcm_out)
        frame = self._frame_bytes()
        while len(self._out_pcm) >= frame:
            chunk = bytes(self._out_pcm[:frame])
            del self._out_pcm[:frame]
            if self.call_id:
                self._archive.enqueue(self.call_id, "agent", chunk)
            self._wire_frames_out += 1
            await self.on_agent_wire(chunk)

    async def _flush_agent_pcm_to_wire(self) -> None:
        """Send leftover farewell samples so hangup does not drop the last syllable."""
        leftover = b""
        try:
            leftover = self._out_resampler.flush()
        except Exception:
            leftover = b""
        if leftover:
            if self.current_output_codec == "PCMU":
                try:
                    leftover = pcm16_to_mulaw(leftover, sample_rate=self.sample_rate)
                except Exception:
                    leftover = b""
            if leftover:
                self._out_pcm.extend(leftover)
        frame = self._frame_bytes()
        if self._out_pcm and len(self._out_pcm) < frame:
            self._out_pcm.extend(b"\x00" * (frame - len(self._out_pcm)))
        while len(self._out_pcm) >= frame:
            chunk = bytes(self._out_pcm[:frame])
            del self._out_pcm[:frame]
            if self.call_id:
                self._archive.enqueue(self.call_id, "agent", chunk)
            self._wire_frames_out += 1
            try:
                await self.on_agent_wire(chunk)
            except Exception:
                break

    async def _drain_agent_archive(self) -> None:
        leftover = b""
        try:
            leftover = self._out_resampler.flush()
        except Exception:
            leftover = b""
        if leftover:
            if self.current_output_codec == "PCMU":
                try:
                    leftover = pcm16_to_mulaw(leftover, sample_rate=self.sample_rate)
                except Exception:
                    leftover = b""
            if leftover:
                self._out_pcm.extend(leftover)
        if self._out_pcm and self.call_id:
            self._archive.enqueue(self.call_id, "agent", bytes(self._out_pcm))
            self._out_pcm.clear()
        try:
            await self._archive.close()
        except Exception:
            pass

    async def _finish_hangup(self) -> None:
        if self._hangup_started or self._phase == PHASE_ENDED:
            return
        if self._aec_barge_open:
            log_pstn("hangup.skip_caller_talking", call_id=self.call_id)
            return
        self._hangup_started = True
        from server.call.close_call_executor import execute_agent_close
        from server.call.natural_hangup import HANGUP_PLAYBACK_TIMEOUT_SEC, wait_for_farewell_playback

        reason = str((self._pending_end_call or {}).get("reason") or "agent_hangup")
        spoke = bool(self._response_had_audio or self._pending_farewell_text)
        has_line = self.playback is not None or self.is_agent_audio_active is not None
        heard = await wait_for_farewell_playback(
            self._farewell_still_on_the_line,
            timeout_sec=HANGUP_PLAYBACK_TIMEOUT_SEC,
            wait_for_start_sec=0.5 if has_line and spoke else 0.0,
        )
        if self._closed or self._aec_barge_open or not self._hangup_started:
            if self._hangup_started:
                self._abort_in_progress_hangup()
            return
        await execute_agent_close(
            call_id=self.call_id,
            reason=reason,
            spoke_farewell=spoke or heard,
            flush_audio=self._flush_agent_pcm_to_wire,
            is_playing=lambda: False,
            on_closing=lambda: self._set_phase(PHASE_CLOSING),
            drain_archive=self._drain_agent_archive,
            on_provider_hangup=self._on_remote_hangup,
            on_ended=lambda: self._set_phase(PHASE_ENDED),
        )

    async def speak(
        self,
        text: str,
        *,
        speaker: str | None = None,
        language_code: str | None = None,
    ) -> None:
        _ = speaker
        _ = language_code
        if self._adapter is None or self.emission_blocked() or not (text or "").strip():
            return
        self.current_turn_id = uuid.uuid4().hex[:12]
        self.current_generation_id = uuid.uuid4().hex[:12]
        if self.playback is not None and hasattr(self.playback, "set_current_generation"):
            self.playback.set_current_generation(self.current_generation_id)
        await self._adapter.start_response(
            instructions=f"Speak this exactly, then wait: {text.strip()}"
        )

    async def interrupt_tts(
        self,
        *,
        skip_playback_clear: bool = False,
        already_invalidated: bool = False,
    ) -> None:
        old_gen = self.current_generation_id
        if not already_invalidated and self.playback is not None and hasattr(self.playback, "invalidate_generation"):
            try:
                self.playback.invalidate_generation(old_gen)
            except Exception:
                pass
        if not skip_playback_clear and self.playback is not None and hasattr(self.playback, "clear"):
            try:
                self.playback.clear()
            except Exception:
                pass
        self._set_tts_active(False)
        self._out_pcm.clear()
        self._out_resampler.reset()
        if self._adapter is not None:
            try:
                clearer = getattr(self._adapter, "clear_output_audio", None)
                if callable(clearer):
                    await clearer()
            except Exception:
                pass
            try:
                await self._adapter.cancel_response()
            except Exception as exc:
                log_pstn("LLM_CANCEL.failed", call_id=self.call_id, error=str(exc)[:120])
        log_pstn("QUEUE_DRAIN", call_id=self.call_id, generation_id=old_gen)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._set_phase(PHASE_ENDED)
        self._set_tts_active(False)
        await self._drain_agent_archive()
        try:
            await self.interrupt_tts()
        except Exception:
            pass
        try:
            await self._archive.close()
        except Exception:
            pass
        if self._pump_task and self._pump_task is not asyncio.current_task() and not self._pump_task.done():
            self._pump_task.cancel()
            try:
                await self._pump_task
            except (asyncio.CancelledError, Exception):
                pass
        from server.realtime.voice_manager import realtime_voice_manager

        await realtime_voice_manager.destroy(self.call_id)
        self._adapter = None
        log_pstn("CLEANUP", call_id=self.call_id, wire_frames_out=self._wire_frames_out, pipeline="realtime_voice")
