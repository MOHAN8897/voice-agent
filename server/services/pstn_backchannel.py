"""Out-of-band listening sounds while the caller is still speaking (PSTN).

Industry pattern (Pipecat / Inworld): short continuers on brief mid-utterance pauses.
Never reaches the LLM context or conversation history.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING

from server.prompts.agent_voice_rules import normalize_compile_language
from server.services.pstn_debug import log_pstn
from server.services.transcript_gate import effective_word_count

if TYPE_CHECKING:
    from server.services.pstn_voice_core import PstnVoiceLoop

MIN_SPEECH_BEFORE_ELIGIBLE_S = 0.75
PAUSE_BEFORE_FIRE_S = 0.28
COOLDOWN_S = 2.5
FIRE_PROBABILITY = 0.72
MIN_WORDS = 4

BACKCHANNEL_PHRASES: dict[str, list[str]] = {
    "en-IN": ["Hmm.", "Mhm.", "Right.", "I see.", "Okay."],
    "en-US": ["Hmm.", "Mhm.", "Right.", "Got it.", "Okay."],
    "te-IN": ["సరే.", "అవును.", "అలాగే."],
    "hi-IN": ["हाँ.", "अच्छा.", "ठीक है."],
    "ta-IN": ["ஆம்.", "சரி.", "சரிங்க."],
    "kn-IN": ["ಹೌದು.", "ಸರಿ.", "ಆಯಿತು.", "ಚೆನ್ನಾಗಿದೆ."],
    "ml-IN": ["അതെ.", "ശരി.", "ശരിയാണ്.", "കൊള്ളാം."],
    "mr-IN": ["हो.", "होय.", "बरे.", "ठीक आहे.", "समजले."],
    "bn-IN": ["হ্যাঁ.", "ঠিক আছে.", "বেশ.", "বুঝেছি."],
    "gu-IN": ["હા.", "હાજી.", "બરાબર છે.", "સારું.", "સમજાયું."],
    "pa-IN": ["ਹਾਂ.", "ਹਾਂਜੀ.", "ਠੀਕ ਹੈ.", "ਚੰਗਾ.", "ਸਮਝ ਗਿਆ."],
}


def pick_backchannel_phrase(language: str | None) -> str:
    lang = normalize_compile_language(language)
    pool = BACKCHANNEL_PHRASES.get(lang) or BACKCHANNEL_PHRASES["en-IN"]
    return random.choice(pool)


# Holding line when a composed reply is slow to arrive. Neutral "one moment":
# an acknowledgement such as "okay" would echo the caller's filler (call 35002575).
HOLD_AFTER_S = 1.5
# The caller is still talking (or resumed) if a partial arrived this recently.
HOLD_CALLER_QUIET_S = 0.6
HOLDING_PHRASES: dict[str, str] = {
    "en-IN": "One moment.",
    "en-US": "One moment.",
    "te-IN": "ఒక్క నిమిషం.",
    "hi-IN": "एक सेकंड।",
    "ta-IN": "ஒரு நிமிஷம்.",
    "kn-IN": "ಒಂದು ನಿಮಿಷ.",
    "ml-IN": "ഒരു നിമിഷം.",
    "mr-IN": "एक मिनिट.",
    "bn-IN": "এক মিনিট।",
    "gu-IN": "એક મિનિટ.",
    "pa-IN": "ਇੱਕ ਮਿੰਟ।",
}


def holding_phrase_for(language: str | None) -> str:
    lang = normalize_compile_language(language)
    return HOLDING_PHRASES.get(lang) or HOLDING_PHRASES["en-IN"]


class PstnBackchannelController:
    def __init__(self, voice: PstnVoiceLoop) -> None:
        self._voice = voice
        self._speech_started_at = 0.0
        self._last_partial_at = 0.0
        self._last_fire_at = 0.0
        self._watch_task: asyncio.Task | None = None
        self._watch_epoch = 0
        self._hold_frames: list[bytes] = []
        self._hold_prewarm: asyncio.Task | None = None
        self._hold_task: asyncio.Task | None = None
        self._held_last_turn = False

    def reset(self) -> None:
        self._cancel_watch()
        self._speech_started_at = 0.0
        self._last_partial_at = 0.0

    def note_partial(self, text: str) -> None:
        if self._voice._closed or self._voice._turn_busy:
            return
        from server.services.pstn_voice_core import PHASE_LISTENING

        if self._voice._phase != PHASE_LISTENING or self._voice._intro_phase:
            return
        words = effective_word_count(text or "")
        if words < MIN_WORDS:
            return
        now = time.monotonic()
        if self._speech_started_at <= 0:
            self._speech_started_at = now
        self._last_partial_at = now
        if self._voice._backchannel_playing:
            self._voice._cancel_backchannel()
        self._schedule_watch()

    def note_final(self) -> None:
        self.reset()

    def _schedule_watch(self) -> None:
        self._watch_epoch += 1
        epoch = self._watch_epoch
        prev = self._watch_task
        self._watch_task = asyncio.create_task(self._watch_pause(epoch))
        if prev and not prev.done():
            prev.cancel()

    def _cancel_watch(self) -> None:
        task = self._watch_task
        self._watch_task = None
        if task and not task.done():
            task.cancel()

    async def _watch_pause(self, epoch: int) -> None:
        try:
            await asyncio.sleep(PAUSE_BEFORE_FIRE_S)
            if epoch != self._watch_epoch:
                return
            voice = self._voice
            from server.services.pstn_voice_core import PHASE_LISTENING

            if voice._closed or voice._turn_busy or voice._phase != PHASE_LISTENING:
                return
            if voice._intro_phase:
                return
            if voice._agent_audio_playing():
                return
            now = time.monotonic()
            if now - voice._last_user_partial_at < PAUSE_BEFORE_FIRE_S * 0.85:
                return
            if self._speech_started_at <= 0 or now - self._speech_started_at < MIN_SPEECH_BEFORE_ELIGIBLE_S:
                return
            if self._last_fire_at and now - self._last_fire_at < COOLDOWN_S:
                return
            if random.random() > FIRE_PROBABILITY:
                return
            phrase = pick_backchannel_phrase(voice._resolve_language())
            self._last_fire_at = now
            log_pstn("backchannel.fire", call_id=voice.call_id, phrase=phrase[:40])
            await voice._play_backchannel(phrase)
        except asyncio.CancelledError:
            return

    # --- Holding line for slow replies (composed calls) -------------------------

    def prewarm_hold(self) -> None:
        """Synthesize the holding line once per call, off the reply path."""
        voice = self._voice
        if self._hold_frames or voice._closed:
            return
        if self._hold_prewarm is not None and not self._hold_prewarm.done():
            return
        self._hold_prewarm = asyncio.create_task(self._synthesize_hold())

    async def _synthesize_hold(self) -> None:
        from server.services.pstn_turn_tts import PstnTurnTtsSession
        from server.services.spoken_numbers import prepare_spoken_reply

        voice = self._voice
        session = PstnTurnTtsSession(voice)
        try:
            text = prepare_spoken_reply(holding_phrase_for(voice._resolve_language()), ensure_terminal=True)
            frames = await session.synthesize_detached(text)
            if frames:
                self._hold_frames = frames
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_pstn("hold.prewarm_failed", call_id=voice.call_id, error=str(exc)[:160])
        finally:
            await session.close()

    def start_hold(self, turn_id: str | None) -> None:
        """Arm the holding line for this turn; never on two turns in a row."""
        self.cancel_hold()
        allowed = not self._held_last_turn
        self._held_last_turn = False
        if not allowed or not turn_id:
            return
        self._hold_task = asyncio.create_task(self._hold_after_delay(turn_id))

    def cancel_hold(self) -> None:
        task = self._hold_task
        self._hold_task = None
        if task is not None and not task.done():
            task.cancel()

    async def settle_hold(self) -> None:
        """Before reply speech: drop an unfired holding line, finish a playing one.

        Its frames are already queued ahead of the reply, so waiting here keeps the
        two from interleaving; the line is never cut mid-word.
        """
        task = self._hold_task
        if task is None or task.done():
            return
        if not self._voice._backchannel_playing:
            self.cancel_hold()
            return
        try:
            await asyncio.shield(task)
        except (asyncio.CancelledError, Exception):
            pass

    def _hold_stale(self, turn_id: str) -> bool:
        voice = self._voice
        from server.services.pstn_voice_core import PHASE_THINKING

        session = voice._active_tts_session
        return bool(
            voice._closed
            or not voice._turn_busy
            or voice.current_turn_id != turn_id
            or voice._phase != PHASE_THINKING
            or voice.emission_blocked()
            or (session is not None and getattr(session, "has_sent_text", False))
        )

    async def _hold_after_delay(self, turn_id: str) -> None:
        voice = self._voice
        try:
            await asyncio.sleep(HOLD_AFTER_S)
            if self._hold_stale(turn_id):
                return
            if time.monotonic() - voice._last_user_partial_at < HOLD_CALLER_QUIET_S:
                return
            if not self._hold_frames:
                # Not ready on this turn; the next slow turn can use it.
                self.prewarm_hold()
                return
            async with voice._backchannel_lock:
                if voice._backchannel_task and not voice._backchannel_task.done():
                    return
                voice._backchannel_task = asyncio.current_task()
                voice._backchannel_playing = True
                # The holding line is not the reply: it must not count as a
                # delivered answer for the watchdog or the outage fallback.
                delivered = voice._turn_audio_delivered
                self._held_last_turn = True
                log_pstn("hold.fire", call_id=voice.call_id, turn_id=turn_id, frames=len(self._hold_frames))
                try:
                    for frame in self._hold_frames:
                        if self._hold_stale(turn_id):
                            break
                        await voice._emit_agent_wire(frame)
                finally:
                    voice._turn_audio_delivered = delivered
                    voice._backchannel_playing = False
                    voice._backchannel_task = None
        except asyncio.CancelledError:
            return

