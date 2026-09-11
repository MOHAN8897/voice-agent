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
    "te-IN": ["Hmm.", "Mhm.", "Aha.", "Sare.", "Avunu."],
    "hi-IN": ["Hmm.", "Haan.", "Achha.", "Theek hai."],
}


def pick_backchannel_phrase(language: str | None) -> str:
    lang = normalize_compile_language(language)
    pool = BACKCHANNEL_PHRASES.get(lang) or BACKCHANNEL_PHRASES["en-IN"]
    return random.choice(pool)


class PstnBackchannelController:
    def __init__(self, voice: PstnVoiceLoop) -> None:
        self._voice = voice
        self._speech_started_at = 0.0
        self._last_partial_at = 0.0
        self._last_fire_at = 0.0
        self._watch_task: asyncio.Task | None = None
        self._watch_epoch = 0

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
