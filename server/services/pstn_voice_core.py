"""Shared PSTN voice loop — STT → brain → TTS (used by Exotel/Telnyx/Plivo bridges)."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
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

# Barge is ON. Comment kept historically — do not flip without measuring.
ENABLE_PSTN_BARGE_IN = True
# Prefer substantive/short natural interruptions over a rigid 3-word rule.
PSTN_BARGE_MIN_WORDS = 1
PSTN_BARGE_HOLD_S = 0.12
# Soft AEC energy is a barge confidence signal only — never a hard STT drop gate.
PSTN_TTS_STT_ENERGY_MIN = 320
# Soft AEC barge hysteresis: open after 2 loud frames; close after 8 quiet frames.
PSTN_AEC_LOUD_OPEN_FRAMES = 2
PSTN_AEC_QUIET_CLOSE_FRAMES = 8
PSTN_BARGE_FINAL_TIMEOUT_S = 0.8
# Two 20ms frames protect the onset; transcript confirmation still holds 120ms.
PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.04
# Conversational corrections often land <800ms apart; 450ms still blocks echo double-fires.
PSTN_BARGE_DEBOUNCE_S = 0.45
PSTN_BARGE_FINAL_WINDOW_S = 1.5
PSTN_BARGE_FINAL_DEBOUNCE_S = 0.3
PSTN_ECHO_TAIL_S = 0.35
PSTN_THINK_CANCEL_MIN_WORDS = 1
PSTN_THINK_CANCEL_HOLD_S = 0.25
# Pure backchannels must never kill an in-flight LLM turn.
_THINK_CANCEL_ACK_ONLY = re.compile(
    r"^(?:yeah|yes|yep|yup|ok|okay|sure|hmm|mm|mhm|uh huh|haan|ha|han|sare|"
    r"right|correct|got it|i see|alright|all right)"
    r"(?:\s+(?:yeah|yes|yep|yup|ok|okay|sure|hmm|haan|ha))*[.!,]*$",
    re.I,
)
# Short natural barge / think-cancel phrases (EN + common TE/HI).
_SHORT_INTERRUPT = re.compile(
    r"^(?:yes|no|yeah|yep|nope|wait|stop|actually|hold on|one second|sorry|"
    r"కాదు|లేదు|లేదండి|అవును|వద్దు|అది కాదు|"
    r"नहीं|हाँ|रुको|ठीक)"
    r"(?:\s+\w+){0,3}[.!,]*$",
    re.I,
)
# After idle STT final: allow slower PSTN / Telugu pauses without feeling dead.
PSTN_LISTEN_COALESCE_S = 0.15
# If user still producing partials near fire time, extend once more.
PSTN_LISTEN_COALESCE_PARTIAL_GRACE_S = 0.2
# Keep enough of a long utterance for the LLM (was 500 — truncated mid-thought).
PSTN_PENDING_TRANSCRIPT_MAX = 1500

# Call FSM (mutually exclusive phases).
PHASE_INTRO = "intro"
PHASE_LISTENING = "listening"
PHASE_THINKING = "thinking"
PHASE_SPEAKING = "speaking"
PHASE_INTERRUPTING = "interrupting"
PHASE_ENDED = "ended"

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
        config_session_id = source or (
            f"test-studio:{local['agent_id']}" if local.get("agent_id") else "test-studio"
        )
    elif source:
        config_session_id = source
    from server.services.test_studio_config import merge_stack, saved_call_config

    saved = saved_call_config(config_session_id)
    return {
        "tier": local.get("tier") or saved.get("tier"),
        "stack_override": merge_stack(saved.get("stack_override"), local.get("stack_override")),
        "language": local.get("language") or saved.get("language"),
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
        playback: Any | None = None,
    ) -> None:
        self.session_id = session_id
        self.call_id = call_id
        self.config_session_id = config_session_id
        self.tts_session_id = tts_session_id or session_id
        self.on_agent_wire = on_agent_wire
        self.sample_rate = sample_rate
        self.tts_output_codec = tts_output_codec
        self.is_agent_audio_active = is_agent_audio_active
        self.playback = playback
        self._stt_cm = None
        self._stt = None
        self._stt_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._barge_confirm_task: asyncio.Task | None = None
        self._barge_timeout_task: asyncio.Task | None = None
        self._remote_clear_task: asyncio.Task | None = None
        self._llm_cancel_task: asyncio.Task | None = None
        self._latest_interrupt_text = ""
        self._call_started = False
        self._orphan_turn_task: asyncio.Task | None = None
        self._stt_frames_in = 0
        self._agent_speaking = False
        self._tts_active = False
        self._intro_phase = False
        self._phase = PHASE_LISTENING
        self._phase_lock = asyncio.Lock()
        self._intro_queue: list[str] = []
        self._awaiting_barge_final_at = 0.0
        self._turn_busy = False
        self._closed = False
        self._on_barge: Callable[[], Awaitable[None]] | None = None
        self._speak_lock = asyncio.Lock()
        self._wire_frames_out = 0
        self._wire_bytes_out = 0
        self.current_turn_id: str | None = None
        self.current_generation_id: str | None = None
        self._interrupted_generation: str | None = None
        self._barge_generation: str | None = None
        self._active_speak_task: asyncio.Task | None = None
        self._active_tts_session = None
        self._pending_transcript: str | None = None
        self.current_output_codec = "L16" if sample_rate >= TELNYX_PCM_SAMPLE_RATE else "PCMU"
        self._last_barge_at = 0.0
        self._barge_epoch = 0.0
        self._awaiting_barge_final = False
        self._last_barge_partial: str | None = None
        self._on_remote_hangup: Callable[[], Awaitable[None]] | None = None
        self._on_turn_audio_done: Callable[[], Awaitable[None]] | None = None
        # TTS text layers: generated/queued ≠ heard (echo must use heard only).
        self._tts_generated_text = ""
        self._tts_queued_text = ""
        self._tts_heard_text = ""
        self._last_tts_text = ""  # alias of heard — kept for existing callers
        self._heard_sentences: list[str] = []
        self._tts_started_at = 0.0
        self._partial_started_at = 0.0
        self._think_partial_started_at = 0.0
        self._tts_tail_until = 0.0
        self._coalesce_task: asyncio.Task | None = None
        self._coalesce_epoch = 0
        self._coalesce_transcript: str | None = None
        self._last_user_partial_at = 0.0
        self._current_turn_transcript: str = ""
        self._voice_turn_generation: str | None = None
        from server.services.pstn_archive_writer import PstnArchiveWriter

        self._archive = PstnArchiveWriter()
        self._aec_loud_streak = 0
        self._aec_quiet_streak = 0
        self._aec_barge_open = False
        from server.services.runtime_settings import runtime_settings

        self._barge_runtime = runtime_settings.get(config_session_id or session_id)
        self._last_vad_voice_at = 0.0

    def emission_blocked(self) -> bool:
        """Strict invariant: no valid generation ⇒ no outbound agent audio."""
        gen = self.current_generation_id
        allowed = True
        drop_reason = ""
        if not gen:
            allowed = False
            drop_reason = "no_generation"
        elif self._interrupted_generation and gen == self._interrupted_generation:
            allowed = False
            drop_reason = "interrupted_generation"
        elif self.playback is not None and hasattr(self.playback, "is_generation_valid"):
            if not self.playback.is_generation_valid(gen):
                allowed = False
                drop_reason = "playback_invalid"
        if not allowed:
            log_pstn(
                "PSTN_GEN_GUARD",
                call_id=self.call_id,
                generation=gen,
                current_generation=self.current_generation_id,
                interrupted_generation=self._interrupted_generation,
                allowed=False,
                drop_reason=drop_reason,
            )
        return not allowed

    def _promote_queued_tts_to_heard(self) -> None:
        """Move queued TTS text into heard state only after audio is emitted."""
        queued = (self._tts_queued_text or "").strip()
        if not queued:
            return
        self._tts_queued_text = ""
        self._tts_heard_text = (self._tts_heard_text + " " + queued).strip()[-800:]
        self._last_tts_text = self._tts_heard_text
        self._heard_sentences.append(queued)
        self._heard_sentences = self._heard_sentences[-12:]
        log_pstn(
            "PSTN_PLAYBACK",
            call_id=self.call_id,
            event="tts_heard_promoted",
            generation_id=self.current_generation_id,
            chars=len(queued),
        )

    def _clear_tts_text_layers(self) -> None:
        self._tts_generated_text = ""
        self._tts_queued_text = ""
        self._tts_heard_text = ""
        self._last_tts_text = ""
        self._heard_sentences = []

    def _set_phase(self, phase: str) -> None:
        # ENDED is terminal — never reopen the FSM after hangup (8.3).
        if self._phase == PHASE_ENDED and phase != PHASE_ENDED:
            return
        self._phase = phase
        self._intro_phase = phase == PHASE_INTRO
        if self.call_id:
            pstn_media_flow.emit(self.call_id, "fsm_phase", "internal", detail=phase,
                                 turn_id=self.current_turn_id, generation_id=self.current_generation_id)

    async def _set_phase_async(self, phase: str) -> None:
        async with self._phase_lock:
            self._set_phase(phase)

    def _provider_queued_ms(self) -> float:
        if self.playback is not None and hasattr(self.playback, "queued_ms"):
            try:
                return float(self.playback.queued_ms())
            except Exception:
                return 0.0
        return 0.0

    def _agent_audio_playing(self) -> bool:
        if self._tts_active:
            return True
        if self.playback is not None and hasattr(self.playback, "is_active"):
            try:
                if self.playback.is_active():
                    return True
            except Exception:
                pass
        if self.is_agent_audio_active is not None and self.is_agent_audio_active():
            return True
        if self._tts_tail_until and time.monotonic() < self._tts_tail_until:
            return True
        return False

    def _in_echo_tail_only(self) -> bool:
        if self._tts_active:
            return False
        if self.playback is not None and hasattr(self.playback, "is_active"):
            try:
                if self.playback.is_active():
                    return False
            except Exception:
                pass
        if self.is_agent_audio_active is not None and self.is_agent_audio_active():
            return False
        return bool(self._tts_tail_until and time.monotonic() < self._tts_tail_until)

    def _set_tts_active(self, active: bool) -> None:
        was_active = self._tts_active
        self._tts_active = active
        self._agent_speaking = active
        if active:
            if self._tts_started_at <= 0:
                self._tts_started_at = time.monotonic()
            self._tts_tail_until = 0.0
            if self._phase not in (PHASE_INTRO, PHASE_INTERRUPTING, PHASE_ENDED):
                self._set_phase(PHASE_SPEAKING)
        else:
            self._tts_tail_until = time.monotonic() + PSTN_ECHO_TAIL_S
            if self._phase == PHASE_SPEAKING and not self._turn_busy:
                self._set_phase(PHASE_LISTENING)
            if was_active and self._on_turn_audio_done is not None:
                try:
                    asyncio.get_running_loop().create_task(self._on_turn_audio_done())
                except RuntimeError:
                    pass

    def set_barge_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_barge = fn

    def set_hangup_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_remote_hangup = fn

    def set_turn_audio_done_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_turn_audio_done = fn

    def on_playback_drained(self) -> None:
        """Release speech received after generation finished but before RTP drained."""
        if (self._closed or self._turn_busy or self._intro_phase or self._awaiting_barge_final
                or self._phase in (PHASE_ENDED, PHASE_INTERRUPTING) or self._agent_audio_playing()):
            return
        pending = self._pending_transcript
        self._pending_transcript = None
        if pending:
            self._arm_listen_coalesce(pending)

    def _cancel_listen_coalesce(self, *, clear_text: bool = True) -> None:
        task = self._coalesce_task
        self._coalesce_task = None
        if clear_text:
            self._coalesce_transcript = None
        if task and not task.done():
            task.cancel()

    def _arm_listen_coalesce(self, text: str, *, after_barge: bool = False) -> None:
        """Delay idle turn start so mid-utterance pauses can continue speaking."""
        from server.services.transcript_gate import is_substantive_transcript

        cleaned = (text or "").strip()
        if not cleaned:
            return
        if not is_substantive_transcript(cleaned, after_barge=after_barge):
            log_pstn(
                "stt.thin_drop",
                call_id=self.call_id,
                text=cleaned[:80],
                after_barge=after_barge,
            )
            return
        self._coalesce_transcript = cleaned[-PSTN_PENDING_TRANSCRIPT_MAX:]
        self._coalesce_epoch = getattr(self, "_coalesce_epoch", 0) + 1
        epoch = self._coalesce_epoch
        prev = self._coalesce_task
        self._coalesce_task = None
        if prev and not prev.done():
            prev.cancel()
        self._coalesce_task = asyncio.create_task(self._listen_coalesce_fire(epoch))
        log_pstn(
            "LISTEN_COALESCE_ARM",
            call_id=self.call_id,
            ms=int(PSTN_LISTEN_COALESCE_S * 1000),
            text=cleaned[:80],
        )

    async def _listen_coalesce_fire(self, epoch: int) -> None:
        try:
            await asyncio.sleep(PSTN_LISTEN_COALESCE_S)
            # User still mid-utterance (fresh partials) — wait a short grace once.
            for _ in range(3):
                if self._closed or epoch != self._coalesce_epoch:
                    return
                now = time.monotonic()
                if (
                    self._last_user_partial_at
                    and (now - self._last_user_partial_at) < PSTN_LISTEN_COALESCE_PARTIAL_GRACE_S
                ):
                    await asyncio.sleep(PSTN_LISTEN_COALESCE_PARTIAL_GRACE_S)
                    continue
                break
            if epoch != self._coalesce_epoch:
                return
            text = (self._coalesce_transcript or "").strip()
            self._coalesce_transcript = None
            if self._coalesce_task is asyncio.current_task():
                self._coalesce_task = None
            if not text or self._closed or self._phase == PHASE_ENDED:
                return
            if self._turn_busy or self._phase in (
                PHASE_THINKING,
                PHASE_SPEAKING,
                PHASE_INTERRUPTING,
                PHASE_INTRO,
            ):
                self._queue_user_transcript(text)
                return
            if self._agent_audio_playing():
                self._queue_user_transcript(text)
                return
            log_pstn("LISTEN_COALESCE_FIRE", call_id=self.call_id, text=text[:80])
            self._launch_turn(text)
        except asyncio.CancelledError:
            return

    def _should_commit_barge(self, text: str) -> bool:
        from server.services.echo_guard import echo_overlap_ratio, is_barge_echo, window_assistant_text
        from server.services.transcript_gate import effective_word_count, is_substantive_transcript

        now = time.monotonic()
        speaking = self._agent_audio_playing()
        tts_age_ms = int((now - self._tts_started_at) * 1000) if self._tts_started_at else 0
        echo_tail_ms = max(0, int((self._tts_tail_until - now) * 1000)) if self._tts_tail_until else 0
        last_barge_age_ms = int((now - self._last_barge_at) * 1000) if self._last_barge_at else -1
        words = effective_word_count(text)
        hold_ms = int((now - self._partial_started_at) * 1000) if self._partial_started_at > 0 else 0
        # Echo against HEARD audio only — never against unplayed generated text.
        heard_ref = self._tts_heard_text or self._last_tts_text
        ref = window_assistant_text(heard_ref)
        overlap = echo_overlap_ratio(text, ref)
        provider_queued_ms = self._provider_queued_ms()
        intro = self._phase == PHASE_INTRO or self._intro_phase
        short_ok = bool(_SHORT_INTERRUPT.match((text or "").strip()))
        substantive = is_substantive_transcript(text or "", after_barge=True) or short_ok

        result = True
        reason = "ok"
        if not ENABLE_PSTN_BARGE_IN:
            result, reason = False, "disabled"
        elif not speaking:
            # Do not reset the hold timer on brief not-speaking gaps (chunk boundaries /
            # end-of-TTS edge). Resetting here caused barge attempts to never commit (4.3).
            result, reason = False, "not_speaking"
        elif now - self._last_barge_at < PSTN_BARGE_DEBOUNCE_S:
            result, reason = False, "debounce"
        elif words < int(self._barge_runtime.get("bargeMinWords") or PSTN_BARGE_MIN_WORDS) and not short_ok:
            self._partial_started_at = 0.0
            result, reason = False, "min_words"
        elif not substantive:
            self._partial_started_at = 0.0
            result, reason = False, "not_substantive"
        elif self._barge_runtime.get("bargeRequireVad") and now - self._last_vad_voice_at > 0.8:
            result, reason = False, "vad_required"
        elif self._partial_started_at <= 0:
            self._partial_started_at = now
            result, reason = False, "hold_start"
        elif now - self._partial_started_at < PSTN_BARGE_HOLD_S:
            result, reason = False, "hold"
        elif self._tts_started_at and now - self._tts_started_at < PSTN_BARGE_MIN_AFTER_SPEAK_S:
            result, reason = False, "min_after_speak"
        elif is_barge_echo(text, heard_ref):
            result, reason = False, "echo"

        log_pstn(
            "BARGE_CHECK",
            call_id=self.call_id,
            turn_id=self.current_turn_id,
            tts_active=self._tts_active,
            tts_age_ms=tts_age_ms,
            echo_tail_ms=echo_tail_ms,
            partial_words=words,
            partial_hold_ms=hold_ms,
            echo_overlap=round(overlap, 3),
            intro=intro,
            last_barge_age_ms=last_barge_age_ms,
            provider_queued_ms=round(provider_queued_ms, 1),
            fsm=self._phase,
            reason=reason,
            result=result,
        )
        return result

    def _should_think_cancel(self, text: str) -> bool:
        """Cancel LLM while THINKING (no audio yet) when caller keeps talking."""
        from server.services.transcript_gate import effective_word_count, is_substantive_transcript

        if self._phase != PHASE_THINKING or self._agent_audio_playing():
            self._think_partial_started_at = 0.0
            return False
        cleaned = (text or "").strip()
        if not cleaned:
            self._think_partial_started_at = 0.0
            return False
        # "yeah yeah" / "ok ok" backchannels must not abort the reply.
        if _THINK_CANCEL_ACK_ONLY.match(cleaned):
            self._think_partial_started_at = 0.0
            return False
        short_ok = bool(_SHORT_INTERRUPT.match(cleaned))
        words = effective_word_count(cleaned)
        if words < PSTN_THINK_CANCEL_MIN_WORDS and not short_ok:
            self._think_partial_started_at = 0.0
            return False
        if not short_ok and not is_substantive_transcript(cleaned, after_barge=True):
            self._think_partial_started_at = 0.0
            return False
        now = time.monotonic()
        if self._think_partial_started_at <= 0:
            self._think_partial_started_at = now
            return False
        return (now - self._think_partial_started_at) >= PSTN_THINK_CANCEL_HOLD_S

    def _merge_pending_transcript(self, *parts: str) -> str:
        """Merge STT fragments without dropping corrections (5.4).

        STT refinements (shorter ⊂ longer) replace. Distinct / correction phrases append.
        """
        correction = ("no ", "not ", "wait", "actually", "i meant", "sorry", "కాదు", "వద్దు", "नहीं")
        merged = ""
        for part in parts:
            cleaned = (part or "").strip()
            if not cleaned:
                continue
            if not merged:
                merged = cleaned
                continue
            a = merged.lower()
            b = cleaned.lower()
            if b == a or b in a:
                continue
            if a in b:
                # Refinement vs correction: keep both when the short phrase looks like a fix.
                looks_fix = any(a.startswith(p) or f" {p}" in f" {a}" for p in correction)
                if looks_fix or (len(b) - len(a) > 48):
                    merged = f"{merged} {cleaned}".strip()
                else:
                    merged = cleaned
                continue
            merged = f"{merged} {cleaned}".strip()
        return merged[-PSTN_PENDING_TRANSCRIPT_MAX:]

    async def _think_cancel(self, heard: str | None = None) -> None:
        self._think_partial_started_at = 0.0
        cleaned = (heard or "").strip()
        # Keep the in-flight user utterance + continuation so recovery is not "Yeah yeah" alone.
        merged = self._merge_pending_transcript(
            self._current_turn_transcript,
            self._pending_transcript or "",
            cleaned,
        )
        if merged:
            self._pending_transcript = merged
            log_pstn(
                "THINK_CANCEL.pending",
                call_id=self.call_id,
                chars=len(merged),
                text=merged[:80],
            )
        log_pstn(
            "THINK_CANCEL",
            call_id=self.call_id,
            turn_id=self.current_turn_id,
            generation_id=self.current_generation_id,
            fsm=self._phase,
        )
        if self.call_id:
            async def _bg_cancel(cid: str) -> None:
                try:
                    from server.realtime.manager import realtime_text_manager

                    await realtime_text_manager.cancel(cid)
                except Exception as exc:
                    log_pstn("THINK_CANCEL.llm_failed", call_id=cid, error=str(exc)[:120])

            asyncio.create_task(_bg_cancel(self.call_id))
        task = self._active_speak_task
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _queue_user_transcript(self, text: str, *, intro: bool = False, barge_final: bool = False) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        from server.services.echo_guard import is_barge_final_echo, is_final_echo

        if barge_final:
            if is_barge_final_echo(cleaned, self._tts_heard_text or self._last_tts_text):
                log_pstn("stt.echo_drop", call_id=self.call_id, text=cleaned[:80], rail="barge_final")
                return
        elif intro or self._intro_phase:
            if is_final_echo(cleaned, self._tts_heard_text or self._last_tts_text, in_echo_tail=True):
                log_pstn("stt.echo_drop", call_id=self.call_id, text=cleaned[:80], rail="intro")
                return
        elif is_final_echo(
            cleaned, self._tts_heard_text or self._last_tts_text, in_echo_tail=self._in_echo_tail_only()
        ):
            log_pstn("stt.echo_drop", call_id=self.call_id, text=cleaned[:80], rail="final")
            return

        if intro or self._intro_phase:
            self._intro_queue.append(cleaned)
            self._intro_queue = self._intro_queue[-8:]
            log_pstn("intro.queue", call_id=self.call_id, queued=len(self._intro_queue), text=cleaned[:80])
            return

        # Prefer latest substantive utterance after barge / overlapping finals.
        words = len(cleaned.split())
        if barge_final or self._awaiting_barge_final:
            if words >= 2:
                self._pending_transcript = cleaned[-PSTN_PENDING_TRANSCRIPT_MAX:]
            elif self._pending_transcript:
                if cleaned.lower() not in self._pending_transcript.lower():
                    self._pending_transcript = (self._pending_transcript + " " + cleaned).strip()[
                        -PSTN_PENDING_TRANSCRIPT_MAX:
                    ]
            else:
                self._pending_transcript = cleaned
            log_pstn("PENDING_TRANSCRIPT", call_id=self.call_id, mode="replace" if words >= 2 else "merge", text=cleaned[:80])
            return

        if self._pending_transcript:
            if cleaned.lower() not in self._pending_transcript.lower():
                # Replace if new final is longer/more complete; else merge.
                if words >= 3 and words >= len(self._pending_transcript.split()):
                    self._pending_transcript = cleaned[-PSTN_PENDING_TRANSCRIPT_MAX:]
                else:
                    self._pending_transcript = (self._pending_transcript + " " + cleaned).strip()[
                        -PSTN_PENDING_TRANSCRIPT_MAX:
                    ]
        else:
            self._pending_transcript = cleaned

    def _end_intro_phase(self) -> None:
        if not self._intro_phase and self._phase != PHASE_INTRO:
            return
        self._set_phase(PHASE_LISTENING)
        queued = " ".join(self._intro_queue).strip()
        self._intro_queue.clear()
        log_pstn("intro.done", call_id=self.call_id, queued_chars=len(queued))
        if not queued:
            return
        if self._turn_busy:
            self._queue_user_transcript(queued)
        else:
            self._launch_turn(queued)

    async def _wait_for_intro_playback(self, frames: int) -> None:
        """Keep startup speech queued until the greeting leaves the playback path.

        TTS completion only means synthesis/enqueue finished. In particular, the
        final RTP frame can be in flight even when the local queue is empty.
        A deliberate barge-in changes phase and retains its own handoff logic.
        """
        deadline = time.monotonic() + max(10.0, frames * 0.02 + 5.0)
        while not self._closed and self._intro_phase and self._agent_audio_playing():
            if time.monotonic() >= deadline:
                raise TimeoutError("PSTN greeting playback did not drain")
            await asyncio.sleep(0.02)

    async def _send_tts_text(self, session: Any, text: str) -> None:
        from server.services.spoken_numbers import prepare_spoken_reply

        if self.emission_blocked():
            return
        provider = None
        try:
            from server.call.call_context import get as get_ctx

            ctx = get_ctx(self.call_id) if self.call_id else None
            if ctx and ctx.resolved_stack and getattr(ctx.resolved_stack, "tts", None):
                provider = str(getattr(ctx.resolved_stack.tts, "provider", "") or "") or None
        except Exception:
            provider = None
        # Intermediate streaming chunks share one upstream TTS context. Preserve
        # their original punctuation so the provider does not reset prosody at an
        # artificial full stop between token batches.
        expanded = prepare_spoken_reply(
            text or "",
            provider=provider,
            ensure_terminal=False,
        )
        if not expanded.strip():
            return
        self._set_tts_active(True)
        # Generated/queued only — heard state updates when audio actually emits.
        self._tts_generated_text = (self._tts_generated_text + " " + expanded).strip()[-800:]
        self._tts_queued_text = (self._tts_queued_text + " " + expanded).strip()[-800:]
        log_pstn(
            "PSTN_TTS",
            call_id=self.call_id,
            event="text_queued",
            generation_id=self.current_generation_id,
            chars=len(expanded),
            heard_chars=len(self._tts_heard_text),
        )
        await session.send_text(expanded)

    def _resolve_language(self) -> str:
        if not self.call_id:
            return "te-IN"
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id)
        if ctx and ctx.resolved_stack:
            return ctx.resolved_stack.language or "te-IN"
        return "te-IN"

    async def start_call(
        self,
        *,
        play_greeting: bool = True,
        greeting_wire_frames: list[bytes] | None = None,
        greeting_text: str | None = None,
    ) -> None:
        """Open STT and play the opening line in parallel so greeting is not blocked on STT."""
        if self._call_started or self._closed:
            return
        self._call_started = True
        log_pstn(
            "lifecycle.started",
            call_id=self.call_id,
            session_id=self.session_id,
            sample_rate=self.sample_rate,
            tts_codec=self.tts_output_codec,
            play_greeting=play_greeting,
            prewarm_frames=len(greeting_wire_frames or []),
        )
        if self.call_id:
            from server.call.audio_archive import audio_archive

            audio_archive.set_agent_sample_rate(self.call_id, self.sample_rate)

        greeting = greeting_text if play_greeting else None
        if greeting is None and play_greeting and self.call_id:
            from server.call.call_context import get as get_ctx

            ctx = get_ctx(self.call_id)
            greeting = extract_opening_greeting(
                ctx.compiled_brain_text if ctx else None,
                self._resolve_language(),
            )

        jobs: list[asyncio.Task] = [asyncio.create_task(self.open_stt())]
        if greeting:
            self._set_phase(PHASE_INTRO)
            self._intro_queue.clear()
            self._tts_generated_text = greeting
            log_pstn("INTRO_START", call_id=self.call_id, chars=len(greeting))
        if greeting_wire_frames and greeting:
            log_pstn(
                "greeting.prewarm.play",
                call_id=self.call_id,
                chars=len(greeting),
                frames=len(greeting_wire_frames),
            )
            jobs.append(asyncio.create_task(self._play_buffered_greeting(greeting_wire_frames, greeting)))
        elif greeting:
            log_pstn("greeting.start", call_id=self.call_id, chars=len(greeting))
            log_tts("PSTN greeting", call_id=self.call_id, chars=len(greeting))
            # Speak first; note_spoken after so Realtime history matches what the caller heard.
            jobs.append(asyncio.create_task(self.speak(greeting)))

        before_frames = self._wire_frames_out
        results = await asyncio.gather(*jobs, return_exceptions=True)
        stt_err = results[0] if isinstance(results[0], BaseException) else None
        if greeting:
            greet_err = results[1] if len(results) > 1 and isinstance(results[1], BaseException) else None
            if greet_err and not isinstance(greet_err, asyncio.CancelledError):
                log_pstn("greeting.failed", call_id=self.call_id, error=str(greet_err)[:200])
                if self._wire_frames_out == before_frames and not self._closed:
                    # Retry a cold greeting once; another failure reaches bridge cleanup.
                    await self.speak(greeting)
            await self._wait_for_intro_playback(self._wire_frames_out - before_frames)
            if not self._closed and self._intro_phase and self._wire_frames_out > before_frames:
                await self._note_opening_spoken(self._tts_heard_text or greeting)
                log_pstn("greeting.done", timer_key=self.call_id, call_id=self.call_id)
            # Release queued startup speech only after playback, not after synthesis.
            self._end_intro_phase()
        elif not play_greeting or not self.call_id:
            log_pstn("greeting.skip", call_id=self.call_id, reason="disabled" if not play_greeting else "no_call")
            self._set_phase(PHASE_LISTENING)
        if stt_err:
            log_pstn("stt.open.failed", call_id=self.call_id, error=str(stt_err)[:200])
            log_error("PSTN STT open failed", call_id=self.call_id, detail=str(stt_err)[:300])
            raise stt_err

    async def _play_buffered_greeting(self, frames: list[bytes], greeting: str) -> None:
        self._set_tts_active(True)
        if not self.current_generation_id:
            self.current_generation_id = uuid.uuid4().hex[:12]
            self._interrupted_generation = None
            if self.playback is not None and hasattr(self.playback, "set_current_generation"):
                self.playback.set_current_generation(self.current_generation_id)
        self._tts_queued_text = greeting
        self._tts_generated_text = greeting or self._tts_generated_text
        try:
            for wire in frames:
                if self._closed or self.emission_blocked():
                    break
                await self._emit_agent_wire(wire)
        finally:
            self._set_tts_active(False)

    async def _note_opening_spoken(self, greeting: str) -> None:
        if not self.call_id or not greeting:
            return
        from server.realtime.manager import realtime_text_manager

        # Assistant history = what was spoken; plus a clear do-not-repeat marker for the model.
        spoken_note = (
            f"{greeting.strip()}\n"
            "[Opening already spoken aloud — do not greet or introduce yourself again.]"
        )
        last_err = ""
        for attempt in range(5):
            try:
                await realtime_text_manager.note_spoken(self.call_id, spoken_note)
                return
            except Exception as exc:
                last_err = str(exc)[:160]
                log_pstn("greeting.note_failed", call_id=self.call_id, attempt=attempt + 1, error=last_err)
                await asyncio.sleep(min(0.15 * (2**attempt), 1.2))
        # Deterministic priming fallback so Realtime does not re-greet.
        try:
            session = realtime_text_manager.get(self.call_id)
            if session is not None and hasattr(session, "note_spoken"):
                await session.note_spoken(spoken_note)
                log_pstn("greeting.note_primed", call_id=self.call_id)
                return
        except Exception as exc:
            last_err = str(exc)[:160]
        log_pstn("greeting.note_exhausted", call_id=self.call_id, error=last_err)

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
        self._stt_task = asyncio.create_task(self._stt_supervisor())
        self._ping_task = asyncio.create_task(self._stt_ping())
        log_pstn("stt.open", call_id=self.call_id, language=lang, sample_rate=self.sample_rate)
        if self.call_id:
            pstn_media_flow.emit(self.call_id, "stt_stream", "inbound", detail="streaming")

    async def _reopen_stt_socket(self) -> bool:
        """Close and reopen the STT upstream without spawning a nested supervisor."""
        try:
            if self._ping_task and not self._ping_task.done():
                self._ping_task.cancel()
            if self._stt_cm is not None:
                try:
                    await self._stt_cm.__aexit__(None, None, None)
                except Exception:
                    pass
            self._stt = None
            self._stt_cm = None
            # Reuse open_stt connection setup without replacing the supervisor task.
            from server.routes.ws import _connect_stt_upstream
            from server.services.runtime_settings import runtime_settings
            from server.services.voice_stt_runtime import (
                effective_stt_mode,
                effective_stt_silence_ms,
                effective_stt_stream_type,
            )

            lang = self._resolve_language()
            rt = runtime_settings.get(self.config_session_id or self.session_id)
            self._stt_cm = _connect_stt_upstream(
                session_id=self.config_session_id or self.session_id,
                call_id=self.call_id,
                language_code=lang,
                sample_rate=self.sample_rate,
                stream_type=effective_stt_stream_type(str(rt.get("sttStreamType") or "fast")),
                mode=effective_stt_mode(str(rt.get("sttMode") or "transcribe")),
                silence_duration_ms=effective_stt_silence_ms(rt),
                threshold=float(rt["sttThreshold"]) if rt.get("sttThreshold") is not None else None,
            )
            self._stt = await self._stt_cm.__aenter__()
            self._ping_task = asyncio.create_task(self._stt_ping())
            log_pstn("stt.reopen", call_id=self.call_id)
            return True
        except Exception as exc:
            log_pstn("stt.reopen.failed", call_id=self.call_id, error=str(exc)[:200])
            return False

    async def _stt_supervisor(self) -> None:
        """Restart STT reader on crash so the call does not go permanently deaf (3.2)."""
        retries = 0
        while not self._closed and self._phase != PHASE_ENDED:
            try:
                await self._stt_reader()
                # Clean iterator end — try one reconnect if call still live.
                if self._closed or self._phase == PHASE_ENDED:
                    return
                retries += 1
                if retries > 3:
                    self._stt_failed("STT reconnect budget exhausted")
                    return
                await asyncio.sleep(min(2**retries, 8))
                if not await self._reopen_stt_socket():
                    self._stt_failed("STT reconnect failed")
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                retries += 1
                log_pstn(
                    "stt.reader.crash",
                    call_id=self.call_id,
                    error=str(exc)[:200],
                    retry=retries,
                )
                if retries > 3 or self._closed or self._phase == PHASE_ENDED:
                    logger.warning("[PSTN] stt supervisor giving up: %s", str(exc)[:200])
                    self._stt_failed(str(exc))
                    return
                await asyncio.sleep(min(2**retries, 8))
                if not await self._reopen_stt_socket():
                    self._stt_failed("STT reconnect failed")
                    return

    def _stt_failed(self, detail: str) -> None:
        self._stt = None
        self._set_phase(PHASE_ENDED)
        log_pstn("stt.terminal_failed", call_id=self.call_id, error=detail[:200])
        if self.call_id:
            pstn_media_flow.emit(self.call_id, "stt_stream", "inbound", status="failed", detail=detail[:200])
        if self._on_remote_hangup and not self._closed:
            asyncio.create_task(self._on_remote_hangup())

    async def _stt_ping(self) -> None:
        while not self._closed and self._stt:
            await asyncio.sleep(12)
            try:
                await self._stt.send(json.dumps({"event": "ping"}))
            except Exception:
                return

    async def _stt_reader(self) -> None:
        assert self._stt is not None
        try:
            async for raw in self._stt:
                if self._closed or self._phase == PHASE_ENDED:
                    break
                if (
                    self._awaiting_barge_final
                    and self._awaiting_barge_final_at
                    and (time.monotonic() - self._awaiting_barge_final_at) > PSTN_BARGE_FINAL_TIMEOUT_S
                    and (time.monotonic() - self._last_user_partial_at) > PSTN_BARGE_FINAL_TIMEOUT_S
                ):
                    fallback = (self._last_barge_partial or "").strip()
                    from server.services.transcript_gate import is_substantive_transcript

                    used = False
                    if fallback and is_substantive_transcript(fallback, after_barge=True):
                        used = True
                        self._cancel_listen_coalesce()
                        self._queue_user_transcript(fallback, barge_final=True)
                        if not self._turn_busy:
                            pending = self._pending_transcript
                            self._pending_transcript = None
                            if pending:
                                self._launch_turn(pending)
                    log_pstn(
                        "PSTN_BARGE_FINAL",
                        call_id=self.call_id,
                        event="timeout",
                        timeout=True,
                        fallback_used=used,
                        fallback_text=(fallback[:80] if used else ""),
                        generation_id=self._interrupted_generation or self.current_generation_id,
                        partial_received=bool(fallback),
                        final_received=False,
                    )
                    self._awaiting_barge_final = False
                    self._awaiting_barge_final_at = 0.0
                    self._last_barge_partial = None
                    if self._phase == PHASE_INTERRUPTING:
                        self._set_phase(PHASE_LISTENING)
                if isinstance(raw, bytes):
                    raw = raw.decode(errors="ignore")
                msg = json.loads(raw)
                ev = msg.get("event") or msg.get("type") or ""
                if ev == "error":
                    log_pstn("stt.error", call_id=self.call_id, detail=str(msg)[:200])
                    log_error("PSTN STT error", call_id=self.call_id, detail=str(msg)[:300])
                elif ev == "transcript.partial":
                    text = (msg.get("text") or (msg.get("data") or {}).get("text") or "").strip()
                    if text:
                        self._last_user_partial_at = time.monotonic()
                        if self._awaiting_barge_final:
                            self._last_barge_partial = text
                    if text and self.call_id:
                        from server.call.call_context import get as get_ctx

                        ctx = get_ctx(self.call_id)
                        if ctx:
                            ctx.last_stt_partial_at = time.monotonic()
                    # Mid-utterance continuation while waiting to launch after a pause.
                    if (
                        text
                        and self._coalesce_task is not None
                        and not self._coalesce_task.done()
                        and self._phase == PHASE_LISTENING
                        and not self._turn_busy
                        and not self._agent_audio_playing()
                    ):
                        from server.services.transcript_gate import (
                            effective_word_count,
                            is_substantive_transcript,
                        )

                        if effective_word_count(text) >= 2 or is_substantive_transcript(text):
                            self._arm_listen_coalesce(text)
                    self._schedule_interrupt_confirmation(text)
                    if self._should_commit_barge(text):
                        await self._commit_barge(text)
                    elif self._should_think_cancel(text):
                        await self._think_cancel(text)
                elif ev == "transcript.final":
                    text = (msg.get("text") or (msg.get("data") or {}).get("text") or "").strip()
                    if text:
                        self._last_user_partial_at = 0.0
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
                    if not text:
                        continue
                    # Some providers emit a short final without any repeated partial.
                    self._schedule_interrupt_confirmation(text)
                    now = time.monotonic()
                    barge_final = bool(
                        self._awaiting_barge_final
                        and self._barge_epoch
                    )
                    if self._intro_phase or self._phase == PHASE_INTRO:
                        self._queue_user_transcript(text, intro=True)
                    elif barge_final:
                        from server.services.transcript_gate import is_substantive_transcript

                        if not is_substantive_transcript(text, after_barge=True):
                            log_pstn("stt.thin_drop", call_id=self.call_id, text=text[:80], after_barge=True)
                            continue
                        self._cancel_listen_coalesce()
                        self._queue_user_transcript(text, barge_final=True)
                        log_pstn(
                            "PSTN_BARGE_FINAL",
                            call_id=self.call_id,
                            event="final",
                            timeout=False,
                            fallback_used=False,
                            final_received=True,
                            partial_received=bool(self._last_barge_partial),
                            generation_id=self._interrupted_generation or self.current_generation_id,
                        )
                        self._awaiting_barge_final = False
                        self._last_barge_partial = None
                        if not self._turn_busy:
                            pending = self._pending_transcript
                            self._pending_transcript = None
                            if pending:
                                self._launch_turn(pending)
                    elif self._turn_busy or self._phase in (PHASE_THINKING, PHASE_SPEAKING, PHASE_INTERRUPTING):
                        self._queue_user_transcript(text)
                    elif self._agent_audio_playing():
                        # Provider still playing but turn not busy — hold as pending.
                        self._queue_user_transcript(text)
                    else:
                        if (
                            self._barge_epoch
                            and (now - self._barge_epoch) < PSTN_BARGE_FINAL_DEBOUNCE_S
                        ):
                            continue
                        # Listening: substantive + coalesce — do not launch on first pause final.
                        self._arm_listen_coalesce(text)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log_pstn("stt.reader.failed", call_id=self.call_id, error=str(e)[:200])
            logger.warning("[PSTN] stt reader: %s", str(e)[:200])
            raise

    def _schedule_interrupt_confirmation(self, text: str) -> None:
        """Confirm once after the hold, even if STT emits only one short result."""
        if not text or self._closed or self._awaiting_barge_final:
            return
        if self._phase not in (PHASE_INTRO, PHASE_SPEAKING, PHASE_THINKING) and not self._agent_audio_playing():
            return
        self._latest_interrupt_text = text
        if self._barge_confirm_task and not self._barge_confirm_task.done():
            return
        generation = self.current_generation_id or (self.playback.current_generation() if self.playback else None)
        thinking = self._phase == PHASE_THINKING
        if thinking:
            self._should_think_cancel(text)
        else:
            self._should_commit_barge(text)

        async def confirm() -> None:
            hold = PSTN_THINK_CANCEL_HOLD_S if thinking else PSTN_BARGE_HOLD_S
            deadline = time.monotonic() + hold
            # Windows event-loop timers may wake before monotonic hold expires.
            while time.monotonic() < deadline:
                await asyncio.sleep(max(0.01, deadline - time.monotonic()))
            active_generation = self.current_generation_id or (self.playback.current_generation() if self.playback else None)
            if self._closed or generation != active_generation or self._awaiting_barge_final:
                return
            latest = self._latest_interrupt_text
            if thinking and self._should_think_cancel(latest):
                await self._think_cancel(latest)
            elif self._should_commit_barge(latest):
                await self._commit_barge(latest)

        self._barge_confirm_task = asyncio.create_task(confirm())

    async def _barge_final_timeout(self, epoch: float) -> None:
        await asyncio.sleep(PSTN_BARGE_FINAL_TIMEOUT_S)
        # Keep collecting an interruption while fresh partials are still arriving.
        while (not self._closed and self._awaiting_barge_final and epoch == self._barge_epoch
               and self._last_user_partial_at
               and time.monotonic() - self._last_user_partial_at < PSTN_BARGE_FINAL_TIMEOUT_S):
            await asyncio.sleep(PSTN_BARGE_FINAL_TIMEOUT_S)
        if self._closed or not self._awaiting_barge_final or epoch != self._barge_epoch:
            return
        text = self._last_barge_partial or ""
        self._awaiting_barge_final = False
        self._awaiting_barge_final_at = 0.0
        self._last_barge_partial = None
        self._set_phase(PHASE_LISTENING)
        if text:
            self._arm_listen_coalesce(text, after_barge=True)

    async def _commit_barge(self, partial_text: str) -> None:
        """Canonical barge sequence — single ordered path.

        1 mark interrupted / invalidate generation
        2 clear local playback queue
        3 Telnyx clear (via _on_barge)
        4 stop TTS (no stale flush)
        5 cancel LLM
        6 preserve caller partial for final timeout fallback
        """
        now = time.monotonic()
        self._last_barge_at = now
        self._barge_epoch = now
        self._awaiting_barge_final = True
        self._awaiting_barge_final_at = now
        if self._barge_timeout_task and not self._barge_timeout_task.done():
            self._barge_timeout_task.cancel()
        self._barge_timeout_task = asyncio.create_task(self._barge_final_timeout(now))
        cleaned = (partial_text or "").strip()
        if self._intro_queue:
            self._pending_transcript = self._merge_pending_transcript(*self._intro_queue, cleaned)
            self._intro_queue.clear()
        if cleaned:
            self._last_barge_partial = cleaned
        self._partial_started_at = 0.0
        self._think_partial_started_at = 0.0
        self._cancel_listen_coalesce()
        self._set_phase(PHASE_INTERRUPTING)
        barge_t0 = time.monotonic()
        old_gen = self.current_generation_id
        old_gen = old_gen or (self.playback.current_generation() if self.playback else None)
        self._barge_generation = old_gen
        # 1) interrupt + invalidate generation before any clear/cancel
        self._interrupted_generation = old_gen
        if self.playback is not None and hasattr(self.playback, "invalidate_generation"):
            self.playback.invalidate_generation(old_gen)
        heard = " ".join(self._heard_sentences).strip() or self._tts_heard_text or self._last_tts_text
        log_pstn(
            "BARGE_TRIGGER",
            call_id=self.call_id,
            turn_id=self.current_turn_id,
            generation_id=old_gen,
            provider_queued_ms=round(self._provider_queued_ms(), 1),
            heard_chars=len(heard),
            partial=cleaned[:80],
        )
        log_pstn(
            "PSTN_BARGE",
            call_id=self.call_id,
            event="commit",
            generation_id=old_gen,
            partial_received=bool(cleaned),
        )
        from server.agent.conversation_manager import conversation_manager

        conversation_manager.note_barge(self.session_id, heard)
        if self.call_id:
            from server.realtime.manager import realtime_text_manager

            realtime_session = realtime_text_manager.get(self.call_id)
            if realtime_session is not None:
                realtime_session.reconcile_spoken(heard)
            pstn_media_flow.emit(self.call_id, "barge_confirmed", "inbound", generation_id=old_gen, detail=cleaned)
        if self.call_id:
            from server.call.call_context import get as get_ctx

            ctx = get_ctx(self.call_id)
            if ctx:
                ctx.barge_in_flight = True
                ctx.agent_hangup_armed = False
        # 2–5) interrupt_tts clears playback, stops TTS, cancels LLM.
        # Provider clear runs once via _on_barge before interrupt to match Telnyx order:
        # clear remote queue then stop local generation.
        async def clear_carrier() -> None:
            if self._on_barge:
                try:
                    await asyncio.wait_for(self._on_barge(), timeout=1.0)
                except Exception as exc:
                    log_pstn("playback.remote_clear.failed", call_id=self.call_id, error=str(exc)[:160])

        # Local invalidation/drain and LLM cancellation cannot wait on the carrier.
        self._remote_clear_task = asyncio.create_task(clear_carrier())
        await self.interrupt_tts(already_invalidated=True)
        # Drop unplayed generated text so echo guard cannot use it.
        self._tts_queued_text = ""
        log_pstn(
            "BARGE_AUDIO_STOP_MS",
            call_id=self.call_id,
            ms=int((time.monotonic() - barge_t0) * 1000),
            queue_ms=round(self._provider_queued_ms(), 1),
        )

    async def feed_user_pcm16(self, pcm16: bytes) -> None:
        if not self._stt or not pcm16:
            return
        # Soft AEC hysteresis is barge confidence only — always forward audio to STT
        # so quiet barge syllables are not lost (transcript-level echo guards remain).
        agent_playing = self._agent_audio_playing()
        rms = 0
        dropped = False
        drop_reason = ""
        if agent_playing:
            try:
                from server.services.audio_transcode import pcm16_rms

                rms = pcm16_rms(pcm16)
                if rms >= PSTN_TTS_STT_ENERGY_MIN:
                    self._last_vad_voice_at = time.monotonic()
                    self._aec_loud_streak += 1
                    self._aec_quiet_streak = 0
                    if self._aec_loud_streak >= PSTN_AEC_LOUD_OPEN_FRAMES:
                        self._aec_barge_open = True
                else:
                    self._aec_quiet_streak += 1
                    self._aec_loud_streak = 0
                    if self._aec_quiet_streak >= PSTN_AEC_QUIET_CLOSE_FRAMES:
                        self._aec_barge_open = False
                # Intentionally do NOT return early — quiet speech still reaches STT.
            except Exception:
                pass
        else:
            self._aec_loud_streak = 0
            self._aec_quiet_streak = 0
            self._aec_barge_open = False
        if self.call_id:
            self._archive.enqueue(self.call_id, "user", pcm16)
        b64 = base64.b64encode(pcm16).decode()
        try:
            await self._stt.send(json.dumps({"event": "audio_input", "audio": b64}))
        except Exception as exc:
            log_pstn("stt.send.failed", call_id=self.call_id, error=str(exc)[:200])
            dropped = True
            drop_reason = "stt_send_failed"
            log_pstn(
                "PSTN_STT_GATE",
                call_id=self.call_id,
                agent_audio_playing=agent_playing,
                rms=rms,
                threshold=PSTN_TTS_STT_ENERGY_MIN,
                audio_forwarded_to_stt=False,
                audio_dropped=True,
                drop_reason=drop_reason,
                aec_open=self._aec_barge_open,
            )
            return
        if self._stt_frames_in % 25 == 0:
            log_pstn(
                "PSTN_STT_GATE",
                call_id=self.call_id,
                agent_audio_playing=agent_playing,
                rms=rms,
                threshold=PSTN_TTS_STT_ENERGY_MIN,
                audio_forwarded_to_stt=True,
                audio_dropped=False,
                drop_reason="",
                aec_open=self._aec_barge_open,
            )
        self._stt_frames_in += 1
        if self._stt_frames_in == 1:
            log_pstn("stt.first_audio", timer_key=self.call_id, call_id=self.call_id, bytes=len(pcm16))
            log_stt("PSTN first audio to STT", call_id=self.call_id, bytes=len(pcm16))
        elif self._stt_frames_in in (50, 200, 500):
            log_pstn("stt.audio.progress", call_id=self.call_id, frames_in=self._stt_frames_in)

    def _launch_turn(self, text: str) -> None:
        self._cancel_listen_coalesce()
        if self._turn_busy or self._phase == PHASE_ENDED:
            if text:
                self._queue_user_transcript(text)
            return
        if self.call_id:
            from server.call.turn_coordinator import track

            track(self.call_id, self._run_turn(text))
            return
        task = asyncio.create_task(self._run_turn(text))
        self._orphan_turn_task = task

        def _log_orphan(t: asyncio.Task) -> None:
            try:
                exc = t.exception()
            except asyncio.CancelledError:
                return
            except Exception:
                return
            if exc:
                logger.warning("[PSTN] orphan turn failed: %s", str(exc)[:200])

        task.add_done_callback(_log_orphan)

    async def _run_turn(self, text: str) -> None:
        if self._turn_busy:
            self._queue_user_transcript(text)
            return
        if not self.call_id:
            logger.warning("[PSTN] transcript ignored — no call_id (agent not linked)")
            return
        self._turn_busy = True
        self._set_phase(PHASE_THINKING)
        self._awaiting_barge_final = False
        # Prefer full user intent: trigger text + any pending barge/correction fragments (11.2).
        self._current_turn_transcript = self._merge_pending_transcript(
            text,
            self._pending_transcript or "",
        ) or (text or "").strip()
        text = self._current_turn_transcript
        self._pending_transcript = None
        self.current_turn_id = uuid.uuid4().hex[:12]
        self.current_generation_id = uuid.uuid4().hex[:12]
        self._interrupted_generation = None
        if self.playback is not None and hasattr(self.playback, "set_current_generation"):
            self.playback.set_current_generation(self.current_generation_id)
        safe = text[:120].encode("ascii", "replace").decode("ascii")
        log_pstn("TURN_START", call_id=self.call_id, turn_id=self.current_turn_id, generation_id=self.current_generation_id, text=safe)
        pstn_media_flow.emit(
            self.call_id,
            "llm_started",
            "outbound",
            turn_id=self.current_turn_id,
            status="processing",
            detail=text[:200],
        )
        cancelled = False
        spoke_from_stream = False
        needs_tts_fallback = False
        try:
            # Finish previous turn's control messages before starting another response;
            # a late carrier clear / Realtime cancel must never target the new turn.
            for control_task in (self._remote_clear_task, self._llm_cancel_task):
                if control_task and not control_task.done():
                    await asyncio.shield(control_task)
            from server.call.live_turn_orchestrator import live_turn_orchestrator
            from server.services.pstn_turn_tts import PstnTurnTtsSession

            pending = ""
            spoke_from_stream = False
            accepted_end_call = False
            first_token_seen = False
            llm_rt = pstn_turn_runtime(self.config_session_id, self.session_id)
            self._clear_tts_text_layers()
            self._tts_started_at = 0.0
            tts_session = PstnTurnTtsSession(self)
            self._active_tts_session = tts_session
            turn_cancelled = False
            async with self._speak_lock:
                self._active_speak_task = asyncio.current_task()
                tts_open = asyncio.create_task(tts_session.open())
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
                        if self.emission_blocked():
                            turn_cancelled = True
                            break
                        if chunk.get("cancelled"):
                            turn_cancelled = True
                        if chunk.get("delta"):
                            if not first_token_seen:
                                first_token_seen = True
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
                            if sentences:
                                await tts_open
                                self._set_tts_active(True)
                                for sent in sentences:
                                    if self.emission_blocked():
                                        turn_cancelled = True
                                        break
                                    await self._send_tts_text(tts_session, sent)
                                    spoke_from_stream = True
                        elif chunk.get("done"):
                            if chunk.get("cancelled"):
                                turn_cancelled = True
                            tail = resolve_stream_tts_tail(
                                pending,
                                chunk.get("text") or "",
                                spoke_from_stream=spoke_from_stream,
                            )
                            if tail and not turn_cancelled and not self.emission_blocked():
                                await tts_open
                                self._set_tts_active(True)
                                await self._send_tts_text(tts_session, tail)
                            pending = ""
                            end_call = chunk.get("end_call") or {}
                            accepted_end_call = bool(
                                isinstance(end_call, dict) and end_call.get("should_end")
                            )
                            # Flush as soon as model text is complete; resuming the
                            # iterator may await ledger writes before it terminates.
                            if tts_session.has_sent_text and not turn_cancelled and not self.emission_blocked():
                                await tts_session.finish()
                    if (spoke_from_stream or tts_session.has_sent_text) and not turn_cancelled and not self.emission_blocked():
                        await tts_open
                        await tts_session.finish()
                        if (
                            getattr(tts_session, "had_error", False)
                            or (
                                getattr(tts_session, "has_sent_text", False)
                                and not getattr(tts_session, "audio_emitted", True)
                            )
                        ):
                            # Retry only after leaving _speak_lock; speak acquires it.
                            needs_tts_fallback = True
                    # Keep ownership through TTS cleanup. Releasing busy here lets
                    # a new turn start while this turn's finally clears its generation.
                    log_pstn(
                        "PSTN_TURN",
                        call_id=self.call_id,
                        event="voice_audio_complete",
                        turn_id=self.current_turn_id,
                        generation_id=self.current_generation_id,
                        cancelled=turn_cancelled,
                    )
                    if accepted_end_call and self.call_id and not turn_cancelled and not self.emission_blocked():
                        from server.call.call_lifecycle_service import call_lifecycle_service

                        # Synthesis complete != playback complete. Keep the voice
                        # generation valid until the carrier has drained the farewell.
                        self._pending_transcript = None
                        if self._on_remote_hangup:
                            try:
                                await self._on_remote_hangup()
                            except Exception as exc:
                                log_pstn("hangup.provider.failed", call_id=self.call_id, error=str(exc)[:200])
                        await self._set_phase_async(PHASE_ENDED)
                        await call_lifecycle_service.end(self.call_id, reason="agent_hangup")
                        return
                finally:
                    self._set_tts_active(False)
                    if not tts_open.done():
                        tts_open.cancel()
                        try:
                            await tts_open
                        except (asyncio.CancelledError, Exception):
                            pass
                    await tts_session.close()
                    self._active_tts_session = None
                    self._active_speak_task = None
            if needs_tts_fallback and not turn_cancelled and not self.emission_blocked():
                from server.prompts.agent_voice_rules import unclear_fallback_for

                log_pstn("tts.fallback_speech", call_id=self.call_id)
                await self.speak(unclear_fallback_for(self._resolve_language()))
        except asyncio.CancelledError:
            cancelled = True
            log_pstn("turn.cancelled", call_id=self.call_id, turn_id=self.current_turn_id)
        except Exception as e:
            logger.warning("[PSTN] turn error: %s", str(e)[:300])
            log_pstn("turn.error", call_id=self.call_id, error=str(e)[:200])
            if not needs_tts_fallback and not spoke_from_stream and self._phase != PHASE_ENDED and not self._closed:
                try:
                    from server.prompts.agent_voice_rules import unclear_fallback_for

                    await self.speak(unclear_fallback_for(self._resolve_language()))
                except Exception as fallback_error:
                    log_pstn("tts.fallback.failed", call_id=self.call_id, error=str(fallback_error)[:200])
            if self.call_id:
                pstn_media_flow.emit(self.call_id, "turn_error", "outbound", status="failed", detail=str(e)[:200])
        finally:
            self._set_tts_active(False)
            self._turn_busy = False
            if self._phase not in (PHASE_ENDED, PHASE_INTERRUPTING):
                self._set_phase(PHASE_LISTENING)
            elif self._phase == PHASE_INTERRUPTING and not self._awaiting_barge_final:
                self._set_phase(PHASE_LISTENING)
            log_pstn("TURN_END", timer_key=self.call_id, call_id=self.call_id, turn_id=self.current_turn_id)
            self.current_turn_id = None
            # Keep generation id briefly for drop guards; clear interrupt marker after pending launch.
            pending = self._pending_transcript
            self._pending_transcript = None
            self.current_generation_id = None
            self._interrupted_generation = None
            if pending and self._phase != PHASE_ENDED:
                # Barge still waiting on final — restore pending for the barge-final launcher.
                if self._awaiting_barge_final or self._phase == PHASE_INTERRUPTING:
                    self._pending_transcript = pending
                elif cancelled:
                    # Don't thrash: wait for a stable pause before re-asking the LLM.
                    self._arm_listen_coalesce(pending)
                else:
                    self._launch_turn(pending)
        if cancelled:
            # Pending already preserved in finally (coalesce / re-queue). Do not
            # re-raise CancelledError here — callers that catch it would lose that state (5.5).
            return

    async def _emit_agent_wire(self, wire: bytes) -> None:
        if not wire or self.emission_blocked():
            return
        # First successfully emitted frames promote queued TTS → heard (echo truth).
        if not getattr(self.playback, "defer_heard_until_sent", False):
            self._promote_queued_tts_to_heard()
        self._wire_frames_out += 1
        self._wire_bytes_out += len(wire)
        if self.call_id:
            self._archive.enqueue(self.call_id, "agent", wire)
        if self.playback is not None and hasattr(self.playback, "note_sent_frames"):
            try:
                # Estimate 20ms frames from wire size when tracker supports it.
                frame_bytes = pstn_frame_bytes(pstn_wire_mode(self.tts_output_codec, self.sample_rate), self.sample_rate)
                n = max(1, len(wire) // max(1, frame_bytes))
                self.playback.note_sent_frames(n)
            except Exception:
                pass
        await self.on_agent_wire(wire)

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
            self._interrupted_generation = None
            if self.playback is not None and hasattr(self.playback, "set_current_generation"):
                self.playback.set_current_generation(self.current_generation_id)
            session = PstnTurnTtsSession(self)
            self._active_tts_session = session
            self._set_tts_active(True)
            try:
                await session.open(speaker=speaker, language_code=language_code)
                self._clear_tts_text_layers()
                self._tts_started_at = 0.0
                await self._send_tts_text(session, text)
                if not self.emission_blocked():
                    await session.finish()
                    if getattr(session, "had_error", False) or not getattr(session, "audio_emitted", True):
                        raise RuntimeError("TTS produced no usable audio or reported an upstream failure")
            finally:
                self._set_tts_active(False)
                await session.close()
                self._active_tts_session = None
                self._active_speak_task = None
                self.current_generation_id = None

    async def interrupt_tts(
        self,
        *,
        skip_playback_clear: bool = False,
        already_invalidated: bool = False,
    ) -> None:
        old_gen = self.current_generation_id
        if not already_invalidated:
            self._interrupted_generation = old_gen
            if self.playback is not None and hasattr(self.playback, "invalidate_generation"):
                try:
                    self.playback.invalidate_generation(old_gen)
                except Exception:
                    pass
        if not skip_playback_clear and self.playback is not None:
            try:
                if hasattr(self.playback, "clear"):
                    drained = self.playback.clear()
                    log_pstn("QUEUE_DRAIN", call_id=self.call_id, frames=drained, generation_id=old_gen)
            except Exception as exc:
                log_pstn("playback.clear.failed", call_id=self.call_id, error=str(exc)[:120])
        self._set_tts_active(False)
        self._tts_queued_text = ""
        # Realtime cancel off the critical audio-stop path.
        if self.call_id:
            async def _bg_cancel(cid: str) -> None:
                try:
                    from server.realtime.manager import realtime_text_manager

                    await realtime_text_manager.cancel(cid)
                    log_pstn("LLM_CANCEL", call_id=cid)
                except Exception as exc:
                    log_pstn("LLM_CANCEL.failed", call_id=cid, error=str(exc)[:120])

            self._llm_cancel_task = asyncio.create_task(_bg_cancel(self.call_id))
        session = self._active_tts_session
        if session is not None:
            log_pstn("TTS_CANCEL", call_id=self.call_id, generation_id=old_gen)
            try:
                await asyncio.wait_for(session.interrupt(), timeout=0.15)
            except (asyncio.TimeoutError, Exception) as exc:
                log_pstn("tts.interrupt.failed", call_id=self.call_id, error=str(exc)[:160])
            finally:
                self._active_tts_session = None
        task = self._active_speak_task
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._set_phase_async(PHASE_ENDED)
        self._cancel_listen_coalesce()
        log_pstn(
            "CLEANUP",
            call_id=self.call_id,
            stt_frames_in=self._stt_frames_in,
            wire_frames_out=self._wire_frames_out,
        )
        try:
            await self.interrupt_tts()
        except Exception:
            pass
        try:
            await self._archive.close()
        except Exception:
            pass
        tasks = (self._stt_task, self._ping_task, self._barge_confirm_task, self._barge_timeout_task,
                 self._remote_clear_task, self._llm_cancel_task, self._orphan_turn_task)
        for task in tasks:
            if task and task is not asyncio.current_task():
                task.cancel()
        await asyncio.gather(*(task for task in tasks if task and task is not asyncio.current_task()), return_exceptions=True)
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
