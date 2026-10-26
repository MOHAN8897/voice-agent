"""Shared PSTN voice loop — STT → brain → TTS (used by Telnyx/Vobiz bridges)."""
from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from server.services.pstn_debug import log_pstn
from server.services.pstn_lexicon import (
    _STRONG_HALT_RE,
    _WEAK_NEGATION_RE,
    agent_asked_question,
    is_backchannel,
    is_single_word_claim,
)
from server.services.pstn_media_flow import pstn_media_flow
from server.services.pstn_text_chunker import (
    drain_complete_sentences,
    extract_opening_greeting,
    join_speakable_chunks,
    resolve_stream_tts_tail,
)
from server.utils.logger import log_error, log_stt, log_tts

logger = logging.getLogger(__name__)

OnAgentWire = Callable[[bytes], Awaitable[None]]

# Barge is ON. Comment kept historically — do not flip without measuring.
ENABLE_PSTN_BARGE_IN = True
# Empirical PSTN starting points; tune against real carrier/handset telemetry.
PSTN_BARGE_MIN_WORDS = 2
PSTN_BARGE_HOLD_S = 0.30
PSTN_NEGATION_HOLD_S = 0.15
# Soft AEC energy is a barge confidence signal only — never a hard STT drop gate.
PSTN_TTS_STT_ENERGY_MIN = 320
PSTN_AEC_VOICE_LATCH_S = 0.8
PSTN_AEC_MAX_CREST_FACTOR = 4.5
# Soft AEC barge hysteresis: open after 2 loud frames; close after 8 quiet frames.
PSTN_AEC_LOUD_OPEN_FRAMES = 2
PSTN_AEC_QUIET_CLOSE_FRAMES = 8
PSTN_BARGE_FINAL_TIMEOUT_S = 0.8
# Shield initial carrier/speakerphone echo; explicit strong halts still win.
PSTN_BARGE_MIN_AFTER_SPEAK_S = 0.35
# Conversational corrections often land <800ms apart; 450ms still blocks echo double-fires.
PSTN_BARGE_DEBOUNCE_S = 0.45
PSTN_BARGE_FINAL_WINDOW_S = 1.5
PSTN_BARGE_FINAL_DEBOUNCE_S = 0.3
PSTN_ECHO_TAIL_S = 0.35
PSTN_THINK_CANCEL_MIN_WORDS = 2
PSTN_THINK_CANCEL_HOLD_S = 0.25
PSTN_DUCK_TIMEOUT_S = 0.85
# After idle STT final: low-latency 30ms coalesce window before launch.
PSTN_LISTEN_COALESCE_S = 0.03
# If user still producing partials near fire time, extend once more.
PSTN_LISTEN_COALESCE_PARTIAL_GRACE_S = 0.2
# Keep enough of a long utterance for the LLM (was 500 — truncated mid-thought).
PSTN_PENDING_TRANSCRIPT_MAX = 1500
# No reply audio within this window after the caller stops → re-ask once.
PSTN_REPLY_WATCHDOG_S = 4.5
# Tool execution is a legitimate wait; never re-ask while an action is in flight.
# The gateway caps each call at 8s and a turn runs at most four, so the budget
# only has to notice a genuinely stuck stream after the tools return.
PSTN_REPLY_WATCHDOG_TOOL_S = 40.0

# Call FSM (mutually exclusive phases).
PHASE_INTRO = "intro"
PHASE_LISTENING = "listening"
PHASE_THINKING = "thinking"
PHASE_SPEAKING = "speaking"
PHASE_INTERRUPTING = "interrupting"
PHASE_CLOSING = "closing"
PHASE_ENDED = "ended"

# PSTN telephony: 8 kHz (Vobiz μ-law) or 16 kHz (Telnyx L16).
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

    saved = saved_call_config(config_session_id) if config_session_id else {}
    from server.config.constants import normalize_supported_language

    local_stack = local.get("stack_override")
    if inherit:
        stack_override = merge_stack(saved.get("stack_override"), local_stack)
    elif local_stack:
        stack_override = local_stack
    else:
        stack_override = None

    return {
        "tier": local.get("tier") or saved.get("tier"),
        "stack_override": stack_override,
        "language": normalize_supported_language(local.get("language") or saved.get("language")),
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
        stack_override: dict[str, Any] | None = None,
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
        self.stack_override = dict(stack_override or {})
        self._stt_cm = None
        self._stt = None
        self._stt_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._barge_confirm_task: asyncio.Task | None = None
        self._barge_timeout_task: asyncio.Task | None = None
        self._remote_clear_task: asyncio.Task | None = None
        self._llm_cancel_task: asyncio.Task | None = None
        self._latest_interrupt_text = ""
        self._latest_interrupt_is_final = False
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
        self._on_session_error: Callable[[str], Awaitable[None]] | None = None
        self._speak_lock = asyncio.Lock()
        self._wire_frames_out = 0
        self._wire_bytes_out = 0
        self.current_turn_id: str | None = None
        self.current_generation_id: str | None = None
        self._interrupted_generation: str | None = None
        self._barge_generation: str | None = None
        self._active_speak_task: asyncio.Task | None = None
        self._active_tts_session = None
        self._call_tts_session = None
        # Evidence for routing a speech failure: only a session that actually
        # failed can prove a provider outage.
        self._last_tts_session = None
        self._pending_transcript: str | None = None
        self.current_output_codec = "L16" if sample_rate >= TELNYX_PCM_SAMPLE_RATE else "PCMU"
        self._last_barge_at = 0.0
        self._barge_epoch = 0.0
        self._awaiting_barge_final = False
        self._last_barge_partial: str | None = None
        self._on_remote_hangup: Callable[[], Awaitable[None]] | None = None
        self._on_turn_audio_done: Callable[[], Awaitable[None]] | None = None
        self._hangup_started = False
        self._background_hangup_task: asyncio.Task | None = None
        self._technical_fallback_played = False
        self._technical_fallback_active = False
        self._turn_audio_delivered = False
        self._tts_retry_used_for_turn = False
        self._turn_tool_wait = False
        self._watchdog_retry_used = False
        # TTS text layers: generated/queued ≠ heard (echo must use heard only).
        self._tts_generated_text = ""
        self._tts_queued_text = ""
        self._tts_heard_text = ""
        self._last_tts_text = ""  # alias of heard — kept for existing callers
        self._heard_sentences: list[str] = []
        self._turn_tts_accum = ""
        self._backchannel_playing = False
        self._backchannel_task: asyncio.Task | None = None
        self._backchannel_lock = asyncio.Lock()
        self._tts_started_at = 0.0
        self._partial_started_at = 0.0
        self._partial_kind = ""
        self._think_partial_started_at = 0.0
        self._think_partial_kind = ""
        self._expects_answer: bool | None = None
        self._reset_ducking()
        self._tts_tail_until = 0.0
        self._coalesce_task: asyncio.Task | None = None
        self._coalesce_epoch = 0
        self._coalesce_transcript: str | None = None
        self._last_user_partial_at = 0.0
        self._current_turn_transcript: str = ""
        self._think_cancel_relaunch: str | None = None
        self._voice_turn_generation: str | None = None
        from server.services.pstn_archive_writer import PstnArchiveWriter

        self._archive = PstnArchiveWriter()
        self._aec_loud_streak = 0
        self._aec_quiet_streak = 0
        self._aec_barge_open = False
        self._composed_stt_bytes_sent = 0
        from server.services.runtime_settings import runtime_settings

        self._barge_runtime = runtime_settings.get(config_session_id or session_id)
        self._last_vad_voice_at = 0.0
        from server.services.pstn_backchannel import PstnBackchannelController

        self._backchannel = PstnBackchannelController(self)

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
        if not self._tts_heard_text:
            # Anchor the onset shield to heard audio, including deferred RTP
            # sends; synthesis/queue time can precede playback by hundreds of ms.
            self._tts_started_at = time.monotonic()
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
        self._turn_tts_accum = ""
        self._expects_answer = None

    def _set_phase(self, phase: str) -> None:
        # ENDED is terminal — never reopen the FSM after hangup (8.3).
        if self._phase == PHASE_ENDED and phase != PHASE_ENDED:
            return
        if self._phase == PHASE_CLOSING and phase not in (PHASE_CLOSING, PHASE_ENDED):
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
        if self._backchannel_playing:
            return False
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
            if not was_active:
                self._reset_ducking()
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

    def _reset_ducking(self) -> None:
        self._tts_ducked = False
        self._tts_duck_at = 0.0
        self._tts_current_factor = 1.0
        self._tts_target_factor = 1.0

    def _on_vad_speech_onset(self) -> None:
        if self._agent_audio_playing() and self.tts_output_codec != "mp3":
            if not self._tts_ducked:
                log_pstn("TTS_DUCK_TRIGGERED", call_id=self.call_id,
                         provider_queued_ms=round(self._provider_queued_ms(), 1))
            self._tts_ducked = True
            self._tts_duck_at = time.monotonic()
            self._tts_target_factor = 0.2

    def set_barge_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_barge = fn

    def set_error_handler(self, fn: Callable[[str], Awaitable[None]]) -> None:
        self._on_session_error = fn

    def set_hangup_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_remote_hangup = fn

    def _farewell_still_on_the_line(self) -> bool:
        """Playback still leaving the phone — ignore echo-tail used for barge AEC."""
        if self._tts_active:
            return True
        if self.playback is not None and hasattr(self.playback, "is_active"):
            try:
                if self.playback.is_active():
                    return True
            except Exception:
                pass
        if self.is_agent_audio_active is not None:
            try:
                return bool(self.is_agent_audio_active())
            except Exception:
                return False
        return False

    def _close_revocable_text(self, text: str) -> bool:
        """True when a caller turn should cancel a pending goodbye.

        A question, a new request, a correction or a "wait" reopens the call.
        The caller's own goodbye/refusal, a thanks, or an acknowledgement does
        not — those let the close finish.
        """
        from server.call.caller_intent import (
            caller_revoked_callback,
            has_future_interest,
            is_negated_end,
            is_wait_or_continue,
        )
        from server.call.end_call_validate import (
            caller_close_reason,
            caller_engaged_in_turn,
            caller_stop_contact,
            caller_wants_to_continue,
            looks_like_question,
        )
        from server.call.hangup_judge import caller_polite_thanks_only

        cleaned = (text or "").strip()
        if not cleaned:
            return False
        if is_backchannel(cleaned):
            # "Okay"/"yes" acknowledges the goodbye unless a question is open.
            return self._agent_expects_answer()
        if caller_polite_thanks_only(cleaned):
            return False
        # Holding the line open outranks a close phrase in the same turn; this
        # is the same precedence the turn gate uses ("Call cut చేయకండి").
        if is_negated_end(cleaned) or is_wait_or_continue(cleaned):
            return True
        # An explicit opt-out outranks a stray "future" mention ("remove me from
        # future calls" is not future interest).
        if caller_stop_contact(cleaned):
            return False
        if caller_revoked_callback(cleaned) or has_future_interest(cleaned):
            return True
        if caller_close_reason(cleaned) is not None:
            return False
        if looks_like_question(cleaned) or caller_wants_to_continue(cleaned):
            return True
        if _STRONG_HALT_RE.fullmatch(cleaned) or _WEAK_NEGATION_RE.fullmatch(cleaned):
            return True
        return bool(
            caller_engaged_in_turn(cleaned)
            and self._accepts_user_turn(cleaned, after_barge=True)
        )

    def _pending_caller_turn(self) -> str | None:
        for candidate in (self._pending_transcript, self._coalesce_transcript):
            text = (candidate or "").strip()
            if text and self._close_revocable_text(text):
                return text
        return None

    def _close_still_authorized(self) -> bool:
        """The provider hangup stays revocable while the caller takes the turn."""
        if self._closed or self._phase == PHASE_ENDED:
            return True
        if self._awaiting_barge_final:
            return False
        return self._pending_caller_turn() is None

    async def _revoke_agent_hangup(self, *, source: str) -> None:
        """Undo a close that never reached the provider and resume listening."""
        pending = self._pending_caller_turn() or ""
        self._hangup_started = False
        if self.call_id:
            from server.call.call_context import get as get_ctx

            ctx = get_ctx(self.call_id)
            if ctx is not None:
                ctx.agent_hangup_armed = False
        reopened = False
        async with self._phase_lock:
            if self._phase == PHASE_CLOSING:
                # The one legitimate exit from CLOSING besides ENDED: the
                # caller proved the goodbye was premature.
                self._phase = PHASE_LISTENING
                self._intro_phase = False
                reopened = True
                if self.call_id:
                    pstn_media_flow.emit(
                        self.call_id,
                        "fsm_phase",
                        "internal",
                        detail=PHASE_LISTENING,
                        turn_id=self.current_turn_id,
                        generation_id=self.current_generation_id,
                    )
        log_pstn(
            "hangup.revoked",
            call_id=self.call_id,
            source=source,
            text=pending[:80],
        )
        if reopened and self.call_id:
            pstn_media_flow.emit(
                self.call_id,
                "hangup_revoked",
                "internal",
                detail=source,
                status="healthy",
            )

    async def _finish_agent_hangup(
        self,
        *,
        reason: str = "agent_hangup",
        spoke_farewell: bool = True,
        trail_sec: float | None = None,
        playback_timeout_sec: float | None = None,
        revocable: bool = True,
    ) -> None:
        """Speak-complete hangup: drain farewell, pause, then disconnect.

        ``revocable`` is true only for a conversational goodbye. Failure
        teardowns (no usable voice / model outage) must still end the line, so
        they pass False.
        """
        if self._hangup_started or self._phase == PHASE_ENDED or self._closed:
            return
        if revocable and self._pending_caller_turn() is not None:
            # The caller already took the turn back; keep the line and let the
            # pending turn answer instead of speaking a goodbye they did not ask for.
            await self._revoke_agent_hangup(source="caller_turn_before_close")
            return
        self._hangup_started = True
        self._pending_transcript = None
        from server.call.close_call_executor import execute_agent_close

        async def enter_closing():
            await self._set_phase_async(PHASE_CLOSING)

        async def enter_ended():
            await self._set_phase_async(PHASE_ENDED)

        try:
            result = await execute_agent_close(
                call_id=self.call_id,
                reason=reason,
                spoke_farewell=spoke_farewell,
                is_playing=self._farewell_still_on_the_line,
                on_closing=enter_closing,
                on_provider_hangup=self._on_remote_hangup,
                on_ended=enter_ended,
                trail_sec=trail_sec,
                playback_timeout_sec=playback_timeout_sec,
                can_disconnect=self._close_still_authorized if revocable else None,
            )
            if result.cancelled:
                await self._revoke_agent_hangup(source="caller_turn_before_disconnect")
                return
            self._background_hangup_task = result.background_task
        except (Exception, asyncio.CancelledError):
            self._hangup_started = False
            raise

    async def _record_failed_reply(self, *, defect: str, clip: bool = True) -> None:
        log_pstn("tts.fallback_speech", call_id=self.call_id, recorded=clip, defect=defect)
        if self.stack_override.get("pipeline") != "composed_voice":
            return
        await self._record_tts_failure(defect=defect)
        from server.services.saas.session_failure_log import record_session_failure

        record_session_failure(
            channel="voice", code="voice_turn_failed",
            message="The selected speech service returned no usable audio.",
            call_id=self.call_id, detail=defect,
        )

    def _speech_outage_evidence(self, session: Any = None) -> dict[str, Any] | None:
        """Only a retained provider balance/rejection failure proves an outage."""
        from server.services.pstn_turn_tts import OUTAGE_EVIDENCE_KINDS

        target = session if session is not None else self._last_tts_session
        evidence = getattr(target, "failure_evidence", None)
        if not isinstance(evidence, dict):
            return None
        if evidence.get("kind") not in OUTAGE_EVIDENCE_KINDS:
            return None
        if evidence.get("retained") is not True:
            return None
        return dict(evidence)

    async def _end_without_farewell(self, *, reason: str = "agent_hangup") -> None:
        """No usable voice and no proven outage: leave a short tail, then end."""
        if self._hangup_started or self._closed or self._phase == PHASE_ENDED:
            return
        from server.services.pstn_technical_fallback import FALLBACK_TAIL_SEC

        await asyncio.sleep(FALLBACK_TAIL_SEC)
        await self._finish_agent_hangup(
            reason=reason,
            spoke_farewell=False,
            trail_sec=FALLBACK_TAIL_SEC,
            revocable=False,
        )

    async def _close_after_tts_failure(
        self,
        *,
        defect: str,
        session: Any,
        trigger: str,
        reason: str = "agent_hangup",
        retry_farewell: bool = True,
    ) -> None:
        """Prefer a healthy-voice farewell; the recorded clip needs provider proof."""
        evidence = self._speech_outage_evidence(session)
        await self._record_failed_reply(defect=defect, clip=evidence is not None)
        if evidence is None:
            failure = getattr(session, "failure_evidence", None) or {}
            log_pstn(
                "speech.outage_unproven",
                call_id=self.call_id,
                defect=defect,
                failure_kind=str(failure.get("kind") or "none"),
            )
            if retry_farewell:
                await self._close_after_non_tts_failure(reason=reason, session=session)
            else:
                await self._end_without_farewell(reason=reason)
            return
        log_pstn(
            "speech.outage_proven",
            call_id=self.call_id,
            defect=defect,
            kind=evidence.get("kind"),
            provider=evidence.get("provider"),
            code=evidence.get("code"),
            status=evidence.get("status"),
        )
        await self._play_technical_fallback_and_hangup(trigger=trigger)

    async def _close_after_non_tts_failure(
        self,
        *,
        reason: str = "agent_hangup",
        session: Any = None,
        technical: bool = False,
    ) -> None:
        """Use the working voice for a courteous close; the clip needs outage proof.

        ``technical`` is an unrecovered model failure, not a conversation that
        reached its end. The caller hears the honest localized technical line
        instead of a normal goodbye, so a failed turn is never presented as a
        successful close.
        """
        if self._hangup_started or self._closed or self._phase == PHASE_ENDED:
            return
        from server.call.hangup_judge import default_farewell_for
        from server.services.pstn_technical_fallback import CALL_BACK, fallback_text

        farewell = (
            fallback_text(self._resolve_language(), CALL_BACK)
            if technical
            else default_farewell_for(self._resolve_language())
        )
        await self._recover_tts_after_failure(session)
        frames_before = self._wire_frames_out
        try:
            await self.speak(farewell, language_code=self._resolve_language())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_pstn("turn.close.tts_failed", call_id=self.call_id, error_type=type(exc).__name__)
            await self._close_after_tts_failure(
                defect="failure_farewell_tts",
                session=self._last_tts_session,
                trigger="tts_failure",
                reason=reason,
                retry_farewell=False,
            )
            return
        if self._closed or self._hangup_started:
            return
        if self._wire_frames_out == frames_before:
            await self._close_after_tts_failure(
                defect="failure_farewell_empty_audio",
                session=self._last_tts_session,
                trigger="tts_failure",
                reason=reason,
                retry_farewell=False,
            )
            return
        if self.call_id:
            try:
                from server.call.call_ledger import call_ledger

                await call_ledger.append_assistant_turn(self.call_id, farewell)
            except Exception as exc:
                log_pstn("turn.close.ledger_failed", call_id=self.call_id, error_type=type(exc).__name__)
        await self._finish_agent_hangup(reason=reason, revocable=False)

    async def _play_technical_fallback_and_hangup(self, *, trigger: str) -> None:
        """Play a pre-recorded apology in the call language, then close the line.

        The clip never touches the configured TTS/LLM, which is the thing that
        just failed. Playback stops any in-flight speech first, ignores barge-in
        for the terminal message, waits for the carrier queue to drain, leaves a
        short tail pause, and ends through the normal lifecycle.
        """
        if trigger not in {"tts_failure", "farewell_tts_failure"}:
            raise ValueError("Recorded speech outage requires a TTS failure")
        if self._technical_fallback_played or self._hangup_started or self._closed:
            return
        self._technical_fallback_played = True
        self._technical_fallback_active = True
        from server.services.pstn_technical_fallback import (
            FALLBACK_SETTLE_SEC,
            FALLBACK_TAIL_SEC,
            infer_voice_identity,
            prepare_technical_fallback_plan,
            stamp_fallback_meta,
        )

        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id) if self.call_id else None
        provider, model, voice_id = infer_voice_identity(
            resolved_stack=ctx.resolved_stack if ctx else None,
            stack_override=self.stack_override,
        )
        try:
            plan = await prepare_technical_fallback_plan(
                call_id=self.call_id,
                tenant_id=ctx.tenant_id if ctx else None,
                agent_id=ctx.agent_id if ctx else None,
                direction=ctx.direction if ctx else None,
                language=self._resolve_language(),
                trigger=trigger,
                voice_provider=provider,
                voice_model=model,
                voice_id=voice_id,
            )
        except Exception as exc:
            log_pstn("fallback.resolve.failed", call_id=self.call_id, error=str(exc)[:160])
            await self._finish_agent_hangup(
                reason="technical_fallback",
                spoke_farewell=False,
                trail_sec=FALLBACK_TAIL_SEC,
                revocable=False,
            )
            return

        # Stop whatever the failed turn already put on the wire before the
        # terminal announcement starts; queued TTS must not talk over it.
        try:
            await self.interrupt_tts()
        except Exception as exc:
            log_pstn("fallback.interrupt.failed", call_id=self.call_id, error=str(exc)[:160])
        if self._on_barge:
            # Clear frames the carrier already queued as well; local queues alone
            # do not stop a tail that has left the process.
            try:
                await asyncio.wait_for(self._on_barge(), timeout=1.0)
            except Exception as exc:
                log_pstn("fallback.remote_clear.failed", call_id=self.call_id, error=str(exc)[:160])

        frames = plan.disclosure_frames(
            output_codec=self.tts_output_codec,
            sample_rate=self.sample_rate,
        ) + plan.technical_frames(
            output_codec=self.tts_output_codec,
            sample_rate=self.sample_rate,
        )
        played = 0
        defect = plan.defect
        if frames:
            sent_box = {"count": 0}

            async def _emit() -> int:
                async with self._speak_lock:
                    self._clear_tts_text_layers()
                    self.current_generation_id = uuid.uuid4().hex[:12]
                    self._interrupted_generation = None
                    if self.playback is not None and hasattr(self.playback, "set_current_generation"):
                        self.playback.set_current_generation(self.current_generation_id)
                    self._set_tts_active(True)
                    try:
                        if frames:
                            # The carrier still plays its jitter buffer briefly;
                            # speaking into it clips the apology's first word.
                            await asyncio.sleep(FALLBACK_SETTLE_SEC)
                        for wire in frames:
                            if self._closed:
                                break
                            await self._emit_agent_wire(wire)
                            sent_box["count"] += 1
                    finally:
                        self._reset_ducking()
                        self._set_tts_active(False)
                        self.current_generation_id = None
                return sent_box["count"]

            try:
                played = await asyncio.wait_for(_emit(), timeout=plan.watchdog_sec())
            except asyncio.TimeoutError:
                played = sent_box["count"]
                defect = "playback_watchdog"
                log_pstn(
                    "fallback.play.watchdog",
                    call_id=self.call_id,
                    variant=plan.variant,
                    language=plan.language,
                )
            except Exception as exc:
                played = sent_box["count"]
                defect = defect or "playback_failed"
                log_pstn("fallback.play.failed", call_id=self.call_id, error=str(exc)[:160])
        elif not defect:
            defect = "codec_unsupported"

        disclosure_played = bool(plan.disclosure_pcm and played)
        if disclosure_played and self.call_id:
            try:
                from server.call.call_ledger import call_ledger

                await call_ledger.append_assistant_turn(self.call_id, plan.disclosure_text)
            except Exception as exc:
                log_pstn("fallback.ledger.failed", call_id=self.call_id, error=str(exc)[:160])
        if played and plan.pcm and self.call_id:
            try:
                from server.call.call_ledger import call_ledger

                await call_ledger.append_assistant_turn(self.call_id, plan.text)
            except Exception as exc:
                log_pstn("fallback.ledger.failed", call_id=self.call_id, error=str(exc)[:160])
        stamp_fallback_meta(
            self.call_id,
            plan,
            trigger=trigger,
            played=bool(played),
            disclosure_played=disclosure_played,
            defect=defect,
        )
        log_pstn(
            "fallback.played",
            call_id=self.call_id,
            language=plan.language,
            variant=plan.variant,
            source=plan.source,
            frames=played,
            trigger=trigger,
            asset=bool(frames),
            defect=defect,
        )
        if not played:
            # No usable recording: leave the same short tail a person would
            # before releasing the line, then end without leaving dead air.
            await asyncio.sleep(FALLBACK_TAIL_SEC)
        await self._finish_agent_hangup(
            reason="technical_fallback",
            spoke_farewell=bool(played),
            trail_sec=FALLBACK_TAIL_SEC,
            # A broken wire cannot drain; do not hold the caller for the 14 s cap.
            playback_timeout_sec=0.0 if defect in ("playback_watchdog", "playback_failed") else None,
            revocable=False,
        )

    def set_turn_audio_done_handler(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._on_turn_audio_done = fn

    def on_playback_drained(self) -> None:
        """Release speech received after generation finished but before RTP drained."""
        if (self._closed or self._turn_busy or self._intro_phase or self._awaiting_barge_final
                or self._phase in (PHASE_ENDED, PHASE_INTERRUPTING)
                or (self._agent_audio_playing() and not self._in_echo_tail_only())):
            return
        pending = self._filter_pending_backchannel(self._pending_transcript)
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
        cleaned = (text or "").strip()
        if not cleaned:
            return
        if not self._accepts_user_turn(cleaned, after_barge=after_barge):
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
            if self._agent_audio_playing() and not self._in_echo_tail_only():
                self._queue_user_transcript(text)
                return
            log_pstn("LISTEN_COALESCE_FIRE", call_id=self.call_id, text=text[:80])
            self._launch_turn(text)
        except asyncio.CancelledError:
            return

    def _agent_expects_answer(self) -> bool:
        return agent_asked_question(
            self._tts_heard_text or self._last_tts_text, expects_answer=self._expects_answer,
        )

    def _accepts_user_turn(self, text: str, *, after_barge: bool = False) -> bool:
        if self._technical_fallback_active:
            return False
        from server.services.transcript_gate import is_substantive_transcript

        return bool(
            _STRONG_HALT_RE.fullmatch(text) or _WEAK_NEGATION_RE.fullmatch(text)
            or is_single_word_claim(text)
            or (is_backchannel(text) and self._agent_expects_answer())
            or is_substantive_transcript(text, after_barge=after_barge)
        )

    def _filter_pending_backchannel(self, pending: str | None) -> str | None:
        if not pending or not is_backchannel(pending):
            return pending
        keep = self._agent_expects_answer()
        log_pstn(
            "PENDING_KEPT_ANSWER_TO_QUESTION" if keep else "PENDING_PURGED_BACKCHANNEL",
            call_id=self.call_id, chars=len(pending),
        )
        return pending if keep else None

    def _has_barge_voice(self, now: float, *, started_at: float = 0.0, hold: float = 0.0) -> bool:
        if self._last_vad_voice_at <= 0:
            return False
        if 0 <= now - self._last_vad_voice_at <= PSTN_AEC_VOICE_LATCH_S:
            return True
        # Preserve voice evidence accepted when a delayed transcript armed its
        # local hold. Otherwise an 800ms STT delay + 300ms hold races the latch.
        return bool(
            started_at > 0 and 0 <= now - started_at <= hold + 0.05
            and 0 <= started_at - self._last_vad_voice_at <= PSTN_AEC_VOICE_LATCH_S
        )

    @staticmethod
    def _echo_protected_reply(text: str) -> bool:
        words = text.lower().strip(".!?,। ").split()
        number_words = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "oh"}
        return bool(
            len(words) < 3
            or (words and all(word.isdigit() or word in number_words | {"am", "pm"} for word in words))
            or _STRONG_HALT_RE.fullmatch(text) or _WEAK_NEGATION_RE.fullmatch(text)
            or is_backchannel(text)
        )

    def _is_partial_self_echo(self, text: str) -> bool:
        from server.services.echo_guard import echo_overlap_ratio, window_assistant_text

        if self._echo_protected_reply(text):
            return False
        heard = window_assistant_text(self._tts_heard_text or self._last_tts_text)
        return bool(heard and echo_overlap_ratio(text, heard) >= 0.5)

    def _should_commit_barge(self, text: str) -> bool:
        if self._technical_fallback_active:
            return False
        from server.services.echo_guard import (
            echo_overlap_ratio,
            is_barge_echo,
            window_assistant_text,
        )
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
        cleaned = (text or "").strip()
        strong = bool(_STRONG_HALT_RE.fullmatch(cleaned))
        negation = bool(_WEAK_NEGATION_RE.fullmatch(cleaned))
        nod = is_backchannel(cleaned)
        single_claim = is_single_word_claim(cleaned)
        substantive = is_substantive_transcript(cleaned, after_barge=True) or single_claim
        kind = "negation" if negation else "speech"
        if kind != self._partial_kind:
            self._partial_started_at = 0.0
            self._partial_kind = kind
        hold = PSTN_NEGATION_HOLD_S if negation else PSTN_BARGE_HOLD_S

        result = True
        reason = "ok"
        if not ENABLE_PSTN_BARGE_IN:
            result, reason = False, "disabled"
        elif self._closed or self._phase in (PHASE_CLOSING, PHASE_ENDED):
            result, reason = False, "closing"
        elif not speaking:
            # Do not reset the hold timer on brief not-speaking gaps (chunk boundaries /
            # end-of-TTS edge). Resetting here caused barge attempts to never commit (4.3).
            result, reason = False, "not_speaking"
        elif now - self._last_barge_at < PSTN_BARGE_DEBOUNCE_S:
            result, reason = False, "debounce"
        elif nod:
            self._partial_started_at = 0.0
            result, reason = False, "backchannel_ignored"
        elif strong:
            result, reason = True, "strong_halt"
        elif not self._has_barge_voice(now, started_at=self._partial_started_at, hold=hold):
            self._partial_started_at = 0.0
            result, reason = False, "energy_below_floor"
        elif words < int(self._barge_runtime.get("bargeMinWords") or PSTN_BARGE_MIN_WORDS) and not (negation or single_claim):
            self._partial_started_at = 0.0
            result, reason = False, "min_words"
        elif not (substantive or negation):
            self._partial_started_at = 0.0
            result, reason = False, "not_substantive"
        elif not self._echo_protected_reply(cleaned) and is_barge_echo(cleaned, heard_ref):
            self._partial_started_at = 0.0
            result, reason = False, "echo"
        elif self._partial_started_at <= 0:
            self._partial_started_at = now
            result, reason = False, "hold_start"
        elif now - self._partial_started_at < hold:
            result, reason = False, "hold"
        elif self._tts_started_at and now - self._tts_started_at < PSTN_BARGE_MIN_AFTER_SPEAK_S:
            result, reason = False, "min_after_speak_echo_shield"
        elif negation:
            result, reason = True, "weak_negation_committed"

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
        return bool(result)

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
        if is_backchannel(cleaned):
            self._think_partial_started_at = 0.0
            return False
        if _STRONG_HALT_RE.fullmatch(cleaned):
            return True
        prior = (self._current_turn_transcript or "").casefold().rstrip(" .!?।")
        current = cleaned.casefold().rstrip(" .!?।")
        if not _WEAK_NEGATION_RE.fullmatch(cleaned) and prior and current in prior:
            # STT repeats/refines the same request while its reply is buffered.
            # Only new caller information should restart that generation.
            self._think_partial_started_at = 0.0
            return False
        now = time.monotonic()
        negation = bool(_WEAK_NEGATION_RE.fullmatch(cleaned))
        hold = PSTN_NEGATION_HOLD_S if negation else PSTN_THINK_CANCEL_HOLD_S
        kind = "negation" if negation else "speech"
        if kind != self._think_partial_kind:
            self._think_partial_started_at = 0.0
            self._think_partial_kind = kind
        if not self._has_barge_voice(now, started_at=self._think_partial_started_at, hold=hold):
            self._think_partial_started_at = 0.0
            return False
        words = effective_word_count(cleaned)
        single_claim = is_single_word_claim(cleaned)
        if words < PSTN_THINK_CANCEL_MIN_WORDS and not (negation or single_claim):
            self._think_partial_started_at = 0.0
            return False
        if not (negation or single_claim or is_substantive_transcript(cleaned, after_barge=True)):
            self._think_partial_started_at = 0.0
            return False
        if self._think_partial_started_at <= 0:
            self._think_partial_started_at = now
            return False
        return (now - self._think_partial_started_at) >= hold

    def _should_think_continue_final(self, text: str) -> bool:
        """STT final while THINKING: merge continuation into the in-flight turn."""
        if self._phase != PHASE_THINKING or not self._turn_busy or self._agent_audio_playing():
            return False
        cleaned = (text or "").strip()
        if not cleaned:
            return False
        prior = (self._current_turn_transcript or "").strip().lower()
        current = cleaned.lower()
        if prior and current == prior:
            return False
        if prior and current in prior:
            return False
        return self._should_think_cancel(cleaned)

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

    async def _prepare_realtime_think_cancel(self, merged: str) -> None:
        if not self.call_id:
            return
        try:
            from server.realtime.manager import realtime_text_manager

            session = realtime_text_manager.get(self.call_id)
            if session is not None and merged:
                await session.prepare_think_cancel_retry(merged)
            elif session is not None:
                await session.cancel_response()
            else:
                await realtime_text_manager.cancel(self.call_id)
        except Exception as exc:
            log_pstn("THINK_CANCEL.llm_failed", call_id=self.call_id, error=str(exc)[:120])

    async def _think_cancel(self, heard: str | None = None, *, immediate: bool = False) -> None:
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
            immediate=immediate,
        )
        if self.call_id and merged:
            if immediate:
                await self._prepare_realtime_think_cancel(merged)
            else:
                asyncio.create_task(self._prepare_realtime_think_cancel(merged))
        elif self.call_id:
            asyncio.create_task(self._prepare_realtime_think_cancel(""))
        self._think_cancel_relaunch = "immediate" if immediate else "coalesce"
        task = self._active_speak_task
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _queue_user_transcript(self, text: str, *, intro: bool = False, barge_final: bool = False) -> None:
        cleaned = (text or "").strip()
        if not cleaned or self._technical_fallback_active:
            return
        from server.services.echo_guard import is_barge_final_echo, is_final_echo

        protected = self._echo_protected_reply(cleaned)
        if barge_final and not protected:
            if is_barge_final_echo(cleaned, self._tts_heard_text or self._last_tts_text):
                log_pstn("stt.echo_drop", call_id=self.call_id, text=cleaned[:80], rail="barge_final")
                return
        elif (intro or self._intro_phase) and not protected:
            if is_final_echo(cleaned, self._tts_heard_text or self._last_tts_text, in_echo_tail=True):
                log_pstn("stt.echo_drop", call_id=self.call_id, text=cleaned[:80], rail="intro")
                return
        elif not protected and is_final_echo(
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
        if not self._turn_busy and self._in_echo_tail_only():
            # The drain callback may precede this delayed STT final. An echo
            # shield alone must not strand a real answer with no future wakeup.
            self.on_playback_drained()

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
        idle_since: float | None = None
        while not self._closed and self._intro_phase:
            now = time.monotonic()
            if self._agent_audio_playing():
                idle_since = None
            elif idle_since is None:
                # A carrier worker can briefly empty its queue between frames.
                # Require a short quiet window so the final frame is not mistaken
                # for completed playback while it is moving into the send path.
                idle_since = now
            elif now - idle_since >= 0.04:
                return
            if now >= deadline:
                raise TimeoutError("PSTN greeting playback did not drain")
            await asyncio.sleep(0.005)

    def _cancel_backchannel(self) -> None:
        task = self._backchannel_task
        gen = self.current_generation_id
        if task and not task.done():
            task.cancel()
        if self.playback is not None and hasattr(self.playback, "invalidate_generation"):
            try:
                if gen and str(gen).startswith("bc-"):
                    self.playback.invalidate_generation(gen)
            except Exception:
                pass
        self._backchannel_playing = False

    async def _play_backchannel(self, phrase: str) -> None:
        """Short listening sound — no LLM turn, no phase change, no history."""
        if not phrase or self._closed or self._turn_busy:
            return
        from server.services.pstn_turn_tts import PstnTurnTtsSession
        from server.services.spoken_numbers import prepare_spoken_reply

        async with self._backchannel_lock:
            if self._backchannel_task and not self._backchannel_task.done():
                return
            self._backchannel_task = asyncio.current_task()
            bc_gen = f"bc-{uuid.uuid4().hex[:12]}"
            saved_gen = self.current_generation_id
            self._backchannel_playing = True
            self.current_generation_id = bc_gen
            if self.playback is not None and hasattr(self.playback, "set_current_generation"):
                self.playback.set_current_generation(bc_gen)
            session = PstnTurnTtsSession(self)
            try:
                text = prepare_spoken_reply(phrase, ensure_terminal=True)
                await session.open()
                await session.send_text(text)
                if not self.emission_blocked():
                    await session.finish()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_pstn("backchannel.failed", call_id=self.call_id, error=str(exc)[:160])
            finally:
                self._backchannel_playing = False
                self.current_generation_id = saved_gen
                if self.playback is not None and hasattr(self.playback, "set_current_generation"):
                    self.playback.set_current_generation(saved_gen)
                await session.close()
                self._backchannel_task = None

    def _tts_provider_name(self) -> str | None:
        try:
            from server.call.call_context import get as get_ctx

            ctx = get_ctx(self.call_id) if self.call_id else None
            if ctx and ctx.resolved_stack and getattr(ctx.resolved_stack, "tts", None):
                return str(getattr(ctx.resolved_stack.tts, "provider", "") or "") or None
        except Exception:
            pass
        return None

    def _prepare_tts_chunk_text(self, text: str, *, ensure_terminal: bool = False) -> str:
        from server.call.call_context import get as get_ctx
        from server.services.spoken_numbers import prepare_spoken_reply
        from server.services.voice_pipeline_limits import spoken_delta_after_collapse

        ctx = get_ctx(self.call_id) if self.call_id else None
        selection = getattr(getattr(ctx, "resolved_stack", None), "tts", None)
        expanded = prepare_spoken_reply(
            text or "",
            provider=self._tts_provider_name(),
            model=getattr(selection, "model", None),
            ensure_terminal=ensure_terminal,
        )
        expanded, self._turn_tts_accum = spoken_delta_after_collapse(self._turn_tts_accum, expanded)
        return expanded.strip()

    def _queue_tts_text_for_turn(self, expanded: str) -> None:
        if not expanded:
            return
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
        if self.call_id:
            pstn_media_flow.increment(self.call_id, "text_queued_count", 1)
            pstn_media_flow.emit(
                self.call_id,
                "tts_text_queued",
                "outbound",
                turn_id=self.current_turn_id,
                generation_id=self.current_generation_id,
                status="processing",
                detail=expanded[:200],
            )

    async def _send_tts_text(self, session: Any, text: str) -> Any:
        if self.emission_blocked():
            return session
        expanded = self._prepare_tts_chunk_text(text, ensure_terminal=False)
        if not expanded:
            return session
        if self.emission_blocked():
            return session
        self._set_tts_active(True)
        self._queue_tts_text_for_turn(expanded)
        try:
            await session.send_text(expanded)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._tts_retry_used_for_turn or not self._is_transient_tts_error(exc):
                raise
            # One reconnect per turn: a stalled socket mid-reply must not cost
            # the caller the rest of the answer (or the whole call).
            self._tts_retry_used_for_turn = True
            log_pstn(
                "tts.send.retry",
                call_id=self.call_id,
                error=type(exc).__name__,
                detail=str(exc)[:160],
            )
            session = await self._restart_tts_session(session)
            await session.send_text(expanded)
        return session

    @staticmethod
    def _is_transient_tts_error(exc: BaseException) -> bool:
        if isinstance(exc, (OSError, TimeoutError, asyncio.TimeoutError)):
            return True
        return type(exc).__name__ in {
            "ConnectionClosed",
            "ConnectionClosedError",
            "ConnectionClosedOK",
            "WebSocketException",
            "ClientConnectionError",
            "ServerDisconnectedError",
        }

    async def _restart_tts_session(self, failed: Any) -> Any:
        try:
            await failed.close()
        except Exception:
            pass
        if self._call_tts_session is failed:
            self._call_tts_session = None
        session = self._get_call_tts_session()
        self._active_tts_session = session
        await session.prepare_for_turn()
        log_pstn("tts.session.restarted", call_id=self.call_id)
        return session

    async def _recover_tts_after_failure(self, session: Any) -> None:
        """Drop a socket that just raised so the next turn opens a clean one."""
        if session is None:
            return
        try:
            await session.close()
        except Exception:
            pass
        if self._call_tts_session is session:
            self._call_tts_session = None
        if self._active_tts_session is session:
            self._active_tts_session = None

    def _get_call_tts_session(self) -> Any:
        from server.services.pstn_turn_tts import PstnTurnTtsSession

        if self._call_tts_session is None or self._call_tts_session._closed:
            self._call_tts_session = PstnTurnTtsSession(self)
        return self._call_tts_session

    async def _acquire_tts_session(self) -> Any:
        session = self._get_call_tts_session()
        await session.prepare_for_turn()
        return session

    def _begin_turn_playout_metrics(self) -> None:
        begin = getattr(self.playback, "begin_turn_metrics", None) if self.playback else None
        if callable(begin):
            begin()

    async def _release_tts_turn(self, session: Any) -> None:
        await session.end_turn()
        self._log_playout_turn_metrics()

    def _log_playout_turn_metrics(self) -> None:
        end_turn = getattr(self.playback, "end_turn_metrics", None) if self.playback else None
        if callable(end_turn):
            metrics = end_turn()
        else:
            snapshot = getattr(self.playback, "metrics_snapshot", None) if self.playback else None
            if not callable(snapshot):
                return
            metrics = snapshot()
        log_pstn(
            "playout.turn_metrics",
            call_id=self.call_id,
            turn_id=self.current_turn_id,
            generation_id=self.current_generation_id,
            underruns=metrics.get("playout_underrun_count", 0),
            concealment_frames=metrics.get("playout_concealment_frames", 0),
            hold_clock_frames=metrics.get("playout_hold_clock_frames", 0),
            backpressure_waits=metrics.get("producer_backpressure_wait_count", 0),
            backpressure_wait_ms=metrics.get("producer_backpressure_wait_ms", 0),
            queue_peak=metrics.get("queue_peak", 0),
        )

    async def _warm_tts_connection(self) -> None:
        """Open the call-level TTS socket during call start (overlaps with greeting/STT)."""
        try:
            session = self._get_call_tts_session()
            if getattr(session, "_opened", False) and not getattr(session, "_closed", True):
                return
            await session.open(language_code=self._resolve_language())
            log_pstn("tts.warm.ready", call_id=self.call_id)
        except Exception as exc:
            log_pstn("tts.warm.failed", call_id=self.call_id, error=str(exc)[:160])

    def _resolve_language(self) -> str:
        if not self.call_id:
            return "te-IN"
        from server.prompts.agent_voice_rules import normalize_compile_language

        cached = getattr(self, "_cached_resolve_language", None)
        if cached:
            return cached
        from server.call.call_ledger import call_ledger

        meta_lang = (call_ledger.read_meta(self.call_id) or {}).get("language")
        if meta_lang:
            self._cached_resolve_language = normalize_compile_language(str(meta_lang))
            return self._cached_resolve_language
        from server.call.call_context import get as get_ctx

        ctx = get_ctx(self.call_id)
        if ctx and ctx.resolved_stack:
            self._cached_resolve_language = normalize_compile_language(
                ctx.resolved_stack.language or "te-IN"
            )
            return self._cached_resolve_language
        self._cached_resolve_language = "te-IN"
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
        greeting_tts_attempted = False
        if greeting is None and play_greeting and self.call_id:
            from server.call.call_context import get as get_ctx

            ctx = get_ctx(self.call_id)
            greeting = extract_opening_greeting(
                ctx.compiled_brain_text if ctx else None,
                self._resolve_language(),
            )

        jobs: list[asyncio.Task] = [
            asyncio.create_task(self.open_stt()),
            asyncio.create_task(self._warm_tts_connection()),
        ]
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
            async def speak_opening() -> None:
                nonlocal greeting, greeting_tts_attempted
                if self.stack_override.get("pipeline") == "composed_voice":
                    from server.call.call_context import get as get_ctx
                    from server.services.composed_voice_session import localize_composed_opening
                    from server.services.saas.composed_costing import composed_llm_usage, record_composed_stage_usage

                    ctx = get_ctx(self.call_id) if self.call_id else None
                    if ctx is None:
                        raise RuntimeError("The selected opening has no admitted voice session")
                    greeting, usage = await localize_composed_opening(
                        greeting, language=self._resolve_language(), llm=ctx.resolved_stack.llm,
                    )
                    if usage:
                        record_composed_stage_usage(self.call_id, "llm", composed_llm_usage(usage))
                    self._tts_generated_text = greeting
                greeting_tts_attempted = True
                await self.speak(greeting)

            jobs.append(asyncio.create_task(speak_opening()))

        before_frames = self._wire_frames_out
        results = await asyncio.gather(*jobs, return_exceptions=True)
        stt_err = results[0] if isinstance(results[0], BaseException) else None
        if greeting:
            greet_err = results[2] if len(results) > 2 and isinstance(results[2], BaseException) else None
            if greet_err and not isinstance(greet_err, asyncio.CancelledError):
                log_pstn("greeting.failed", call_id=self.call_id, error=str(greet_err)[:200])
                if self.stack_override.get("pipeline") == "composed_voice":
                    if greeting_tts_attempted:
                        await self._close_after_tts_failure(
                            defect="greeting_tts_failed",
                            session=self._last_tts_session,
                            trigger="tts_failure",
                        )
                    else:
                        await self._close_after_non_tts_failure()
                    raise greet_err
                if self._wire_frames_out == before_frames and not self._closed:
                    # Retry a cold greeting once; a second failure closes with a
                    # farewell when the voice works, or the clip when the outage
                    # itself is proven by the provider.
                    try:
                        await self.speak(greeting)
                    except Exception as retry_error:
                        log_pstn("greeting.retry.failed", call_id=self.call_id, error=str(retry_error)[:200])
                        await self._close_after_tts_failure(
                            defect="greeting_retry_tts_failed",
                            session=self._last_tts_session,
                            trigger="tts_failure",
                        )
                        raise
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
            await self._close_after_non_tts_failure()
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
            self._reset_ducking()
            self._set_tts_active(False)

    async def _note_opening_spoken(self, greeting: str) -> None:
        if not self.call_id or not greeting:
            return
        from server.realtime.manager import realtime_text_manager

        # Assistant history = what was spoken; plus a clear do-not-repeat marker for the model.
        spoken_note = (
            f"{greeting.strip()}\n"
            "[Opening already spoken aloud — do not greet, restart or introduce yourself again. "
            "If the caller asks who is calling or why, give your name, company and purpose once.]"
        )
        if self.stack_override.get("pipeline") == "composed_voice":
            from server.agent.conversation_manager import conversation_manager

            conversation_manager.add_turn(self.session_id, "", spoken_note)
            return
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
        expected_pipeline, pinned_stack = self._stt_pipeline_options()
        self._stt_cm = _connect_stt_upstream(
            session_id=self.config_session_id or self.session_id,
            call_id=self.call_id,
            expected_pipeline=expected_pipeline,
            pinned_stack=pinned_stack,
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

    def _stt_pipeline_options(self) -> tuple[str | None, dict[str, Any] | None]:
        """Carry composed intent through connect/reconnect so STT cannot re-resolve."""
        override_pipeline = str(self.stack_override.get("pipeline") or "").strip().lower()
        context_pipeline = None
        if self.call_id:
            from server.call.call_context import get as get_call_ctx

            ctx = get_call_ctx(self.call_id)
            context_pipeline = str(getattr(ctx, "pipeline", "") or "").strip().lower() or None
        if override_pipeline == "composed_voice" and context_pipeline not in (None, "composed_voice"):
            raise RuntimeError("Composed PSTN call context does not match its pinned stack")
        if override_pipeline == "composed_voice" or context_pipeline == "composed_voice":
            return "composed_voice", self.stack_override if override_pipeline == "composed_voice" else None
        return None, None

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
            expected_pipeline, pinned_stack = self._stt_pipeline_options()
            self._stt_cm = _connect_stt_upstream(
                session_id=self.config_session_id or self.session_id,
                call_id=self.call_id,
                expected_pipeline=expected_pipeline,
                pinned_stack=pinned_stack,
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
        log_pstn("stt.terminal_failed", call_id=self.call_id, error=detail[:200])
        if self.call_id:
            pstn_media_flow.emit(self.call_id, "stt_stream", "inbound", status="failed", detail=detail[:200])
        if self._closed or self._hangup_started:
            self._set_phase(PHASE_ENDED)
            return

        async def _announce_then_hangup() -> None:
            try:
                await self._close_after_non_tts_failure()
            except Exception as exc:
                log_pstn("stt.terminal_fallback.failed", call_id=self.call_id, error=str(exc)[:160])
                self._set_phase(PHASE_ENDED)
                if self._on_remote_hangup:
                    try:
                        await self._on_remote_hangup()
                    except Exception as hangup_error:
                        log_pstn("stt.terminal_hangup.failed", call_id=self.call_id, error=str(hangup_error)[:160])

        asyncio.create_task(_announce_then_hangup())

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
                    used = False
                    if fallback and self._accepts_user_turn(fallback, after_barge=True):
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
                elif ev == "vad.speech_start":
                    # Provider-confirmed speech also satisfies the optional VAD
                    # barge gate for quiet callers; energy alone is insufficient.
                    self._last_vad_voice_at = time.monotonic()
                    self._on_vad_speech_onset()
                elif ev == "transcript.partial":
                    text = (msg.get("text") or (msg.get("data") or {}).get("text") or "").strip()
                    if text and self._agent_audio_playing() and self._is_partial_self_echo(text):
                        # A longer STT refinement can reveal that its short prefix
                        # was echo. Do not let that earlier candidate fire later.
                        self._latest_interrupt_text = ""
                        self._partial_started_at = 0.0
                        if self._barge_confirm_task and not self._barge_confirm_task.done():
                            self._barge_confirm_task.cancel()
                        self._tts_ducked = False
                        self._tts_target_factor = 1.0
                        log_pstn("PARTIAL_SELF_ECHO_DROPPED", call_id=self.call_id,
                                 partial_words=len(text.split()))
                        continue
                    if text:
                        if is_backchannel(text):
                            # A semantic nod releases provisional VAD ducking smoothly.
                            self._tts_ducked = False
                            self._tts_target_factor = 1.0
                        else:
                            self._on_vad_speech_onset()
                        self._last_user_partial_at = time.monotonic()
                        self._backchannel.note_partial(text)
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
                    self._backchannel.note_final()
                    self._cancel_backchannel()
                    if text:
                        self._last_user_partial_at = 0.0
                        if self.call_id:
                            from server.call.call_context import get as get_ctx

                            ctx = get_ctx(self.call_id)
                            if ctx:
                                ctx.last_stt_partial_at = 0.0
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
                    self._schedule_interrupt_confirmation(text, final=True)
                    now = time.monotonic()
                    barge_final = bool(
                        self._awaiting_barge_final
                        and self._barge_epoch
                    )
                    if self._intro_phase or self._phase == PHASE_INTRO:
                        self._queue_user_transcript(text, intro=True)
                    elif barge_final:
                        if not self._accepts_user_turn(text, after_barge=True):
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
                        self._awaiting_barge_final_at = 0.0
                        self._last_barge_partial = None
                        if not self._turn_busy:
                            # The final may have been rejected as echo. The old
                            # generation already ended, so no turn-finally remains
                            # to release INTERRUPTING. Later caller speech must
                            # still reach normal listening/coalescing.
                            if self._phase == PHASE_INTERRUPTING:
                                self._set_phase(PHASE_LISTENING)
                            pending = self._pending_transcript
                            self._pending_transcript = None
                            if pending:
                                self._launch_turn(pending)
                            else:
                                # Rejected echo is not a caller turn to debounce.
                                self._barge_epoch = 0.0
                    elif self._phase == PHASE_THINKING and self._turn_busy and not self._agent_audio_playing():
                        if self._should_think_continue_final(text):
                            await self._think_cancel(text, immediate=True)
                        elif (self._think_partial_started_at > 0
                              and text.lower() not in self._current_turn_transcript.lower()):
                            # If this generation finishes before the hold, retain the
                            # accepted continuation for completion instead of losing it.
                            self._pending_transcript = self._merge_pending_transcript(
                                self._pending_transcript or "", text,
                            )
                    elif self._phase == PHASE_CLOSING:
                        # The goodbye is revocable until the carrier hangup; keep
                        # a new question instead of dropping it with the closing line.
                        if self._close_revocable_text(text):
                            self._queue_user_transcript(text)
                            log_pstn(
                                "hangup.revoke_queued",
                                call_id=self.call_id,
                                text=text[:80],
                            )
                    elif self._turn_busy or self._phase in (PHASE_THINKING, PHASE_SPEAKING, PHASE_INTERRUPTING):
                        if (is_backchannel(text) or _STRONG_HALT_RE.fullmatch(text)
                                or self._has_barge_voice(now, started_at=self._partial_started_at,
                                                         hold=PSTN_BARGE_HOLD_S)):
                            self._queue_user_transcript(text)
                    elif self._agent_audio_playing():
                        # Provider still playing but turn not busy — hold as pending.
                        if (is_backchannel(text) or _STRONG_HALT_RE.fullmatch(text)
                                or self._has_barge_voice(now, started_at=self._partial_started_at,
                                                         hold=PSTN_BARGE_HOLD_S)):
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

    def _schedule_interrupt_confirmation(self, text: str, *, final: bool = False) -> None:
        """Confirm once after the hold, even if STT emits only one short result."""
        if not text or self._closed or self._awaiting_barge_final:
            return
        if self._phase not in (PHASE_INTRO, PHASE_SPEAKING, PHASE_THINKING) and not self._agent_audio_playing():
            return
        self._latest_interrupt_text = text
        self._latest_interrupt_is_final = final
        if self._barge_confirm_task and not self._barge_confirm_task.done():
            # Wake a sleeping general hold when a halt/negation/refinement arrives.
            # Candidate timestamps survive, so repeated partials do not extend it.
            self._barge_confirm_task.cancel()
        generation = self.current_generation_id or (self.playback.current_generation() if self.playback else None)
        if self._phase == PHASE_THINKING:
            self._should_think_cancel(text)
        else:
            self._should_commit_barge(text)

        async def confirm() -> None:
            while True:
                active_generation = self.current_generation_id or (self.playback.current_generation() if self.playback else None)
                if self._closed or generation != active_generation or self._awaiting_barge_final:
                    return
                latest = self._latest_interrupt_text
                thinking = self._phase == PHASE_THINKING and not self._agent_audio_playing()
                ready = self._should_think_cancel(latest) if thinking else self._should_commit_barge(latest)
                if ready:
                    if thinking:
                        if not self._latest_interrupt_is_final or self._should_think_continue_final(latest):
                            await self._think_cancel(latest, immediate=self._latest_interrupt_is_final)
                    else:
                        await self._commit_barge(latest)
                    return
                started = self._think_partial_started_at if thinking else self._partial_started_at
                if started <= 0:
                    return
                hold = PSTN_NEGATION_HOLD_S if _WEAK_NEGATION_RE.fullmatch(latest) else (
                    PSTN_THINK_CANCEL_HOLD_S if thinking else PSTN_BARGE_HOLD_S
                )
                now = time.monotonic()
                delay = hold - (now - started)
                if not thinking and self._tts_started_at:
                    delay = max(delay, PSTN_BARGE_MIN_AFTER_SPEAK_S - (now - self._tts_started_at))
                if delay <= 0:
                    return
                # Recheck after a newer partial changes the candidate or hold kind.
                await asyncio.sleep(max(0.01, delay))

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
        was_intro = self._intro_phase
        now = time.monotonic()
        self._reset_ducking()
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
                if not was_intro:
                    from server.services.user_turn_hints import note_caller_interruption

                    note_caller_interruption(ctx)
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
        if agent_playing or self._phase in (PHASE_THINKING, PHASE_LISTENING):
            try:
                from server.services.audio_transcode import pcm16_crest_factor, pcm16_rms

                rms = pcm16_rms(pcm16)
                if rms >= PSTN_TTS_STT_ENERGY_MIN and pcm16_crest_factor(pcm16, rms) <= PSTN_AEC_MAX_CREST_FACTOR:
                    self._aec_loud_streak += 1
                    self._aec_quiet_streak = 0
                    if self._aec_loud_streak >= PSTN_AEC_LOUD_OPEN_FRAMES:
                        self._aec_barge_open = True
                        self._last_vad_voice_at = time.monotonic()
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
            if self.stack_override.get("pipeline") == "composed_voice":
                self._composed_stt_bytes_sent += len(pcm16)
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

    async def _flush_stale_outbound_playback(self, *, reason: str) -> None:
        """Drop prior-turn PSTN playout before starting a new spoken reply."""
        playback = self.playback
        old_gen = None
        if playback is not None and hasattr(playback, "current_generation"):
            old_gen = playback.current_generation()
        old_gen = old_gen or self.current_generation_id
        active = False
        if playback is not None and hasattr(playback, "is_active"):
            try:
                active = bool(playback.is_active())
            except Exception:
                active = False
        if not old_gen and not active:
            return
        if old_gen:
            self._interrupted_generation = old_gen
            if hasattr(playback, "invalidate_generation"):
                playback.invalidate_generation(old_gen)
        drained = 0
        if playback is not None and hasattr(playback, "clear"):
            try:
                drained = int(playback.clear() or 0)
            except Exception:
                pass
        if drained or active:
            if self._on_barge:
                try:
                    await asyncio.wait_for(self._on_barge(), timeout=1.0)
                except Exception as exc:
                    log_pstn("playback.remote_clear.failed", call_id=self.call_id, error=str(exc)[:160])
            log_pstn(
                "playback.flush",
                call_id=self.call_id,
                reason=reason,
                generation_id=old_gen,
                frames=drained,
                queue_ms=round(self._provider_queued_ms(), 1),
            )

    def _launch_turn(self, text: str) -> None:
        if self._technical_fallback_active:
            return
        self._cancel_listen_coalesce()
        self._backchannel.reset()
        self._cancel_backchannel()
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

    def _reply_watchdog_budget(self) -> float:
        return PSTN_REPLY_WATCHDOG_TOOL_S if self._turn_tool_wait else PSTN_REPLY_WATCHDOG_S

    def _watchdog_retry_allowed(self) -> bool:
        if self._turn_tool_wait or self._turn_audio_delivered:
            return False
        session = self._active_tts_session
        if session is not None and getattr(session, "has_sent_text", False):
            return False
        return not self._technical_fallback_active and self._phase != PHASE_ENDED

    async def _watched_turn_stream(
        self, turn_kwargs: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """Run one turn; re-ask once when the first attempt never starts speaking."""
        from server.call.live_turn_orchestrator import live_turn_orchestrator

        kwargs = dict(turn_kwargs)
        retry_used = False
        started = False
        stream = live_turn_orchestrator.handle_user_turn_stream(**kwargs)
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        stream.__anext__(),
                        timeout=None if started else self._reply_watchdog_budget(),
                    )
                except StopAsyncIteration:
                    return
                except asyncio.TimeoutError:
                    await self._close_stream(stream)
                    if not retry_used and not started and self._watchdog_retry_allowed():
                        retry_used = True
                        self._watchdog_retry_used = True
                        log_pstn(
                            "turn.watchdog",
                            call_id=self.call_id,
                            turn_id=self.current_turn_id,
                            event="reask",
                            timeout_s=self._reply_watchdog_budget(),
                        )
                        kwargs["retry_attempt"] = True
                        stream = live_turn_orchestrator.handle_user_turn_stream(**kwargs)
                        yield {"status": "watchdog_retry"}
                        continue
                    log_pstn(
                        "turn.watchdog",
                        call_id=self.call_id,
                        turn_id=self.current_turn_id,
                        event="gave_up",
                        timeout_s=self._reply_watchdog_budget(),
                        retry_used=retry_used,
                    )
                    raise TimeoutError("The selected voice service did not answer in time") from None
                if (
                    chunk.get("delta")
                    or chunk.get("done")
                    or chunk.get("status") in {"close_pending", "reply_buffered"}
                ):
                    # The stream is alive and may already hold a close decision;
                    # re-asking would repeat the caller turn for no benefit.
                    started = True
                yield chunk
        finally:
            await self._close_stream(stream)

    @staticmethod
    async def _close_stream(stream: AsyncIterator[dict[str, Any]]) -> None:
        close = getattr(stream, "aclose", None)
        if close is None:
            return
        try:
            await close()
        except (RuntimeError, GeneratorExit):
            pass

    async def _record_agent_failure(
        self,
        exc: BaseException,
        *,
        delivered: bool,
        turn_completed: bool,
    ) -> None:
        if not self.call_id:
            return
        from server.call.call_context import get as get_ctx
        from server.services.turn_failure_log import record_turn_failure

        ctx = get_ctx(self.call_id)
        try:
            await record_turn_failure(
                call_id=self.call_id,
                tenant_id=str(ctx.tenant_id) if ctx and ctx.tenant_id else None,
                agent_id=str(ctx.agent_id) if ctx and ctx.agent_id else None,
                transcript=self._current_turn_transcript,
                partial_text=str(getattr(exc, "partial_text", "") or ""),
                finish_reason=getattr(exc, "finish_reason", None),
                error_type=type(exc).__name__,
                error=str(exc)[:300],
                delivered=delivered,
                turn_completed=turn_completed,
                retry_used=bool(getattr(exc, "retry_used", False)),
                watchdog_retry=self._watchdog_retry_used,
                tool_wait=self._turn_tool_wait,
            )
        except Exception as record_error:
            log_pstn(
                "turn.failure.record_failed",
                call_id=self.call_id,
                error_type=type(record_error).__name__,
            )

    async def _record_watchdog_recovery(self) -> None:
        """Keep a recovered silence event visible: the turn was late, then safe."""
        if not self.call_id:
            return
        from server.call.call_context import get as get_ctx
        from server.services.turn_failure_log import record_turn_failure

        ctx = get_ctx(self.call_id)
        try:
            await record_turn_failure(
                call_id=self.call_id,
                tenant_id=str(ctx.tenant_id) if ctx and ctx.tenant_id else None,
                agent_id=str(ctx.agent_id) if ctx and ctx.agent_id else None,
                transcript=self._current_turn_transcript,
                partial_text="",
                finish_reason="watchdog_timeout",
                error_type="ReplyWatchdogTimeout",
                error=(
                    f"No reply within {self._reply_watchdog_budget():.1f}s; "
                    "the watchdog re-asked once and the retry completed."
                ),
                delivered=True,
                turn_completed=True,
                retry_used=False,
                watchdog_retry=True,
                tool_wait=False,
            )
        except Exception as record_error:
            log_pstn(
                "turn.watchdog.record_failed",
                call_id=self.call_id,
                error_type=type(record_error).__name__,
            )

    async def _record_tts_failure(self, *, defect: str) -> None:
        """The model finished but the speech service returned no usable audio."""
        if not self.call_id:
            return
        from server.call.call_context import get as get_ctx
        from server.services.turn_failure_log import record_turn_failure

        ctx = get_ctx(self.call_id)
        try:
            await record_turn_failure(
                call_id=self.call_id,
                tenant_id=str(ctx.tenant_id) if ctx and ctx.tenant_id else None,
                agent_id=str(ctx.agent_id) if ctx and ctx.agent_id else None,
                transcript=self._current_turn_transcript,
                partial_text=str(self._tts_generated_text or ""),
                finish_reason="tts_empty_audio",
                error_type="TTSAudioFailure",
                error=f"Speech synthesis produced no usable audio ({defect}).",
                delivered=False,
                turn_completed=True,
                retry_used=self._tts_retry_used_for_turn,
                watchdog_retry=self._watchdog_retry_used,
                tool_wait=self._turn_tool_wait,
            )
        except Exception as record_error:
            log_pstn(
                "turn.tts.record_failed",
                call_id=self.call_id,
                error_type=type(record_error).__name__,
            )

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
        # Synthesis may finish before the carrier drains; flush stale playout so the
        # new reply cannot overlap the tail of the previous answer.
        await self._flush_stale_outbound_playback(reason="turn_start")
        self.current_turn_id = uuid.uuid4().hex[:12]
        self.current_generation_id = uuid.uuid4().hex[:12]
        self._interrupted_generation = None
        if self.playback is not None and hasattr(self.playback, "set_current_generation"):
            self.playback.set_current_generation(self.current_generation_id)
        safe = text[:120].encode("ascii", "replace").decode("ascii")
        log_pstn("TURN_START", call_id=self.call_id, turn_id=self.current_turn_id, generation_id=self.current_generation_id, text=safe)
        self._begin_turn_playout_metrics()
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
        tts_session = None
        accepted_end_call = False
        hangup_reason = "agent_hangup"
        self._tts_retry_used_for_turn = False
        self._turn_audio_delivered = False
        self._turn_tool_wait = False
        self._watchdog_retry_used = False
        turn_completed = False
        try:
            # Finish previous turn's control messages before starting another response;
            # a late carrier clear / Realtime cancel must never target the new turn.
            for control_task in (self._remote_clear_task, self._llm_cancel_task):
                if control_task and not control_task.done():
                    await asyncio.shield(control_task)
            from server.call.live_turn_orchestrator import live_turn_orchestrator

            pending = ""
            spoke_from_stream = False
            first_token_seen = False
            llm_rt = pstn_turn_runtime(self.config_session_id, self.session_id)
            self._clear_tts_text_layers()
            self._tts_started_at = 0.0
            tts_session = self._get_call_tts_session()
            self._last_tts_session = tts_session
            self._active_tts_session = tts_session
            turn_cancelled = False
            async with self._speak_lock:
                self._active_speak_task = asyncio.current_task()
                tts_prepare = asyncio.create_task(tts_session.prepare_for_turn())
                try:
                    turn_kwargs = dict(
                        transcript=text,
                        language_code=self._resolve_language(),
                        session_id=self.session_id,
                        call_id=self.call_id,
                        openai_model=llm_rt.get("openai_model"),
                        temperature=llm_rt.get("temperature"),
                        reasoning_effort=llm_rt.get("reasoning_effort"),
                        max_output_tokens=llm_rt.get("max_output_tokens"),
                    )
                    async for chunk in self._watched_turn_stream(turn_kwargs):
                        if chunk.get("status") == "tool_wait":
                            # An action is in flight; a re-ask could repeat its side effect.
                            self._turn_tool_wait = True
                            continue
                        if chunk.get("status") == "watchdog_retry":
                            # Nothing from the first attempt reached TTS or the wire.
                            pending = ""
                            first_token_seen = False
                            continue
                        if self.emission_blocked():
                            turn_cancelled = True
                            break
                        if isinstance(chunk.get("expects_answer"), bool):
                            self._expects_answer = chunk["expects_answer"]
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
                                await tts_prepare
                                self._set_tts_active(True)
                                combined = join_speakable_chunks(sentences)
                                if combined:
                                    if self.emission_blocked():
                                        turn_cancelled = True
                                        break
                                    tts_session = await self._send_tts_text(tts_session, combined)
                                    spoke_from_stream = True
                        elif chunk.get("done"):
                            turn_completed = True
                            if chunk.get("cancelled"):
                                turn_cancelled = True
                            tail = (
                                (chunk.get("text") or "").strip()
                                if chunk.get("replace_speech")
                                else resolve_stream_tts_tail(
                                    pending,
                                    chunk.get("text") or "",
                                    spoke_from_stream=spoke_from_stream,
                                )
                            )
                            if tail and not turn_cancelled and not self.emission_blocked():
                                await tts_prepare
                                self._set_tts_active(True)
                                tts_session = await self._send_tts_text(tts_session, tail)
                            pending = ""
                            end_call = chunk.get("end_call") or {}
                            accepted_end_call = bool(
                                isinstance(end_call, dict) and end_call.get("should_end")
                            )
                            if accepted_end_call:
                                hangup_reason = str(end_call.get("reason") or hangup_reason or "agent_hangup")
                            if tts_session.has_sent_text and not turn_cancelled and not self.emission_blocked():
                                await tts_session.finish()
                    if (spoke_from_stream or tts_session.has_sent_text) and not turn_cancelled and not self.emission_blocked():
                        await tts_prepare
                        await tts_session.finish()
                        # Audio already on the wire is a delivered reply. A late
                        # reader/flush error must not replace it with the outage
                        # apology and end the call.
                        session_audio_emitted = bool(getattr(tts_session, "audio_emitted", True))
                        if (
                            getattr(tts_session, "has_sent_text", False)
                            and not self._turn_audio_delivered
                            and not session_audio_emitted
                        ):
                            needs_tts_fallback = True
                        elif getattr(tts_session, "had_error", False):
                            log_pstn(
                                "tts.turn.degraded",
                                call_id=self.call_id,
                                turn_id=self.current_turn_id,
                                chars=getattr(tts_session, "_chars_sent", 0),
                            )
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
                finally:
                    self._set_tts_active(False)
                    if not tts_prepare.done():
                        tts_prepare.cancel()
                        try:
                            await tts_prepare
                        except (asyncio.CancelledError, Exception):
                            pass
                    await self._release_tts_turn(tts_session)
                    self._active_tts_session = None
                    self._active_speak_task = None
            if (
                self._watchdog_retry_used
                and turn_completed
                and not turn_cancelled
                and not self.emission_blocked()
            ):
                await self._record_watchdog_recovery()
            if accepted_end_call and self.call_id and not turn_cancelled and not self.emission_blocked():
                # Synthesis complete != playback complete, and the TTS turn is
                # released so a failed farewell can be replaced by the clip.
                self._set_tts_active(False)
                if needs_tts_fallback:
                    await self._close_after_tts_failure(
                        defect="empty_tts_audio",
                        session=tts_session,
                        trigger="farewell_tts_failure",
                        reason=hangup_reason,
                    )
                else:
                    await self._finish_agent_hangup(reason=hangup_reason)
                return
            if needs_tts_fallback and not turn_cancelled and not self.emission_blocked():
                await self._close_after_tts_failure(
                    defect="empty_tts_audio",
                    session=tts_session,
                    trigger="tts_failure",
                )
                return
        except asyncio.CancelledError:
            cancelled = True
            log_pstn("turn.cancelled", call_id=self.call_id, turn_id=self.current_turn_id)
        except Exception as e:
            detail = f"{type(e).__name__}: {str(e)[:160]}"
            logger.warning("[PSTN] turn error: %s", detail)
            finish_reason = getattr(e, "finish_reason", None)
            log_pstn(
                "turn.error",
                call_id=self.call_id,
                error_type=type(e).__name__,
                finish_reason=str(finish_reason) if finish_reason else None,
                partial_chars=len(getattr(e, "partial_text", "") or ""),
                retry_used=bool(getattr(e, "retry_used", False)),
                delivered=turn_completed,
            )
            tts_audio_emitted = bool(getattr(tts_session, "audio_emitted", False))
            # A reply counts as delivered only when the model finished the turn.
            # Partial audio from an early stop is exactly the dead air the
            # outage apology exists to replace.
            delivered = bool(turn_completed and (self._turn_audio_delivered or tts_audio_emitted))
            if self.stack_override.get("pipeline") == "composed_voice":
                from server.services.saas.session_failure_log import record_session_failure

                record_session_failure(
                    channel="voice", code="voice_turn_failed",
                    message="The selected voice service could not complete the reply.",
                    call_id=self.call_id, detail=detail,
                )
                await self._record_agent_failure(
                    e,
                    delivered=delivered,
                    turn_completed=turn_completed,
                )
                if self._on_session_error:
                    try:
                        await self._on_session_error("The selected voice service could not complete the reply.")
                    except Exception as notify_error:
                        log_pstn("turn.error.notify_failed", call_id=self.call_id, error_type=type(notify_error).__name__)
                if delivered:
                    log_pstn(
                        "turn.error.audio_delivered",
                        call_id=self.call_id,
                        turn_id=self.current_turn_id,
                        error_type=type(e).__name__,
                    )
                    await self._recover_tts_after_failure(tts_session)
                    if accepted_end_call and not turn_cancelled and not self.emission_blocked():
                        await self._finish_agent_hangup(reason=hangup_reason)
                else:
                    from server.call.end_call_validate import caller_close_reason

                    caller_reason = caller_close_reason(text)
                    reason = caller_reason or "agent_hangup"
                    if getattr(tts_session, "had_error", False):
                        await self._close_after_tts_failure(
                            defect="tts_provider_error",
                            session=tts_session,
                            trigger="tts_failure",
                            reason=reason,
                        )
                    else:
                        # No caller close + no delivered reply = the model stopped
                        # early. Say the honest technical line, not a goodbye.
                        await self._close_after_non_tts_failure(
                            reason=reason,
                            session=tts_session,
                            technical=caller_reason is None,
                        )
            elif not spoke_from_stream and not delivered and self._phase != PHASE_ENDED and not self._closed:
                await self._close_after_non_tts_failure(session=tts_session)
            if self.call_id:
                pstn_media_flow.emit(self.call_id, "turn_error", "outbound", status="failed", detail=detail)
        finally:
            self._reset_ducking()
            self._set_tts_active(False)
            self._turn_busy = False
            self._turn_tool_wait = False
            if self._phase not in (PHASE_ENDED, PHASE_INTERRUPTING):
                self._set_phase(PHASE_LISTENING)
            elif self._phase == PHASE_INTERRUPTING and not self._awaiting_barge_final:
                self._set_phase(PHASE_LISTENING)
            log_pstn("TURN_END", timer_key=self.call_id, call_id=self.call_id, turn_id=self.current_turn_id)
            self.current_turn_id = None
            # Keep generation id briefly for drop guards; clear interrupt marker after pending launch.
            pending = self._filter_pending_backchannel(self._pending_transcript)
            self._pending_transcript = None
            self.current_generation_id = None
            self._interrupted_generation = None
            if pending and self._phase != PHASE_ENDED:
                # Barge still waiting on final — restore pending for the barge-final launcher.
                if self._awaiting_barge_final or self._phase == PHASE_INTERRUPTING:
                    self._pending_transcript = pending
                elif cancelled and self._think_cancel_relaunch == "immediate":
                    self._think_cancel_relaunch = None
                    self._launch_turn(pending)
                elif cancelled:
                    # Partial think-cancel: wait for a stable pause before re-asking the LLM.
                    self._think_cancel_relaunch = None
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
        if self.tts_output_codec != "mp3":
            from server.services.audio_transcode import scale_wire_volume

            if (self._tts_ducked and not self._awaiting_barge_final
                    and time.monotonic() - self._tts_duck_at > PSTN_DUCK_TIMEOUT_S):
                self._tts_ducked = False
                self._tts_target_factor = 1.0
                log_pstn("TTS_UNDUCK_RESTORED", call_id=self.call_id)
            frame_bytes = pstn_frame_bytes(pstn_wire_mode(self.tts_output_codec, self.sample_rate), self.sample_rate)
            frames = []
            for offset in range(0, len(wire), frame_bytes):
                frame = wire[offset:offset + frame_bytes]
                start = self._tts_current_factor
                step = 0.2 * len(frame) / frame_bytes
                if start < self._tts_target_factor:
                    self._tts_current_factor = min(self._tts_target_factor, start + step)
                else:
                    self._tts_current_factor = max(self._tts_target_factor, start - step)
                frames.append(scale_wire_volume(
                    frame, self.tts_output_codec, self._tts_current_factor, start_factor=start,
                ))
            wire = b"".join(frames)
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
        res = self.on_agent_wire(wire)
        if inspect.isawaitable(res):
            await res
        if self._turn_busy and not self._technical_fallback_active:
            self._turn_audio_delivered = True

    async def speak(
        self,
        text: str,
        *,
        speaker: str | None = None,
        language_code: str | None = None,
    ) -> None:
        if not text or self._closed or self._hangup_started:
            return
        async with self._speak_lock:
            if self._closed or self._hangup_started:
                return
            self._active_speak_task = asyncio.current_task()
            await self._flush_stale_outbound_playback(reason="speak")
            self.current_generation_id = uuid.uuid4().hex[:12]
            self._interrupted_generation = None
            if self.playback is not None and hasattr(self.playback, "set_current_generation"):
                self.playback.set_current_generation(self.current_generation_id)
            self._begin_turn_playout_metrics()
            session = await self._acquire_tts_session()
            self._last_tts_session = session
            if speaker or language_code:
                await session.open(speaker=speaker, language_code=language_code)
            self._active_tts_session = session
            try:
                self._clear_tts_text_layers()
                self._tts_started_at = 0.0
                self._set_tts_active(True)
                await self._send_tts_text(session, text)
                if not self.emission_blocked():
                    await session.finish()
                    if getattr(session, "had_error", False) or not getattr(session, "audio_emitted", True):
                        raise RuntimeError("TTS produced no usable audio or reported an upstream failure")
            finally:
                self._reset_ducking()
                self._set_tts_active(False)
                await self._release_tts_turn(session)
                self._active_tts_session = None
                self._active_speak_task = None
                self.current_generation_id = None

    async def interrupt_tts(
        self,
        *,
        skip_playback_clear: bool = False,
        already_invalidated: bool = False,
    ) -> None:
        self._reset_ducking()
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
        self._reset_ducking()
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
        if self._call_tts_session is not None:
            try:
                await self._call_tts_session.close()
            except Exception:
                pass
            self._call_tts_session = None
        if self.call_id and self.stack_override.get("pipeline") == "composed_voice":
            from server.services.saas.composed_costing import record_composed_stage_usage

            # Persist once after the media loop closes, outside the frame path.
            await asyncio.to_thread(
                record_composed_stage_usage,
                self.call_id,
                "stt",
                {"audio_seconds": self._composed_stt_bytes_sent / (self.sample_rate * 2)},
                accumulate=False,
            )
