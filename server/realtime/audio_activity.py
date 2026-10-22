"""Conservative local end-of-speech fallback; provider VAD stays authoritative."""
from __future__ import annotations

from dataclasses import dataclass

from server.services.audio_transcode import pcm16_rms


@dataclass
class InputAudioActivity:
    quiet_seconds: float = 1.8
    speech_ms: float = 0.0
    quiet_ms: float = 0.0
    last_audio_at: float | None = None
    last_voice_at: float | None = None
    speaking: bool = False

    def feed(self, pcm: bytes, *, sample_rate: int, now: float) -> bool:
        """Return True only at the start of sustained, non-silent input."""
        self.last_audio_at = now
        duration_ms = len(pcm) * 500 / sample_rate
        if pcm16_rms(pcm) >= 500:
            self.speech_ms += duration_ms
            self.quiet_ms = 0.0
            self.last_voice_at = now
            if not self.speaking and self.speech_ms >= 180:
                self.speaking = True
                return True
        else:
            self.quiet_ms += duration_ms
            if not self.speaking and self.quiet_ms >= 200:
                self.speech_ms = 0.0
        return False

    def should_finalize(self, now: float) -> bool:
        if not self.speaking or self.last_voice_at is None or self.last_audio_at is None:
            return False
        # Require real observed silence OR an interrupted audio stream. Elapsed
        # utterance length alone must never cut off a caller who is still talking.
        return (
            self.quiet_ms >= self.quiet_seconds * 1000
            or now - self.last_audio_at >= self.quiet_seconds
        )

    def reset(self) -> None:
        self.speech_ms = self.quiet_ms = 0.0
        self.last_audio_at = self.last_voice_at = None
        self.speaking = False
