"""
TTS delivery controls — not LLM-style text prompts.

Cartesia Sonic: generation_config {emotion, speed, volume} (director-style).
Sarvam Bulbul v3: pace + temperature only (no system prompt / SSML).

Voice quality mainly comes from well-punctuated LLM text (see tts_speech_rules);
these knobs refine delivery.
"""
from __future__ import annotations

from typing import Any

# Primary Cartesia emotions with strongest training data (docs).
CARTESIA_SAFE_EMOTIONS = frozenset(
    {
        "neutral",
        "calm",
        "content",
        "happy",
        "sad",
        "angry",
        "scared",
        "confident",
        "curious",
        "sympathetic",
        "grateful",
        "peaceful",
    }
)


def cartesia_generation_config(
    *,
    emotion: str | None = None,
    speed: float | None = None,
    volume: float | None = None,
) -> dict[str, Any]:
    """Build Cartesia generation_config for sonic-3 / sonic-3.5."""
    from server.config.env import get_settings

    settings = get_settings()
    emo = (emotion or getattr(settings, "cartesia_tts_emotion", None) or "calm").strip().lower()
    if emo not in CARTESIA_SAFE_EMOTIONS:
        emo = "calm"
    spd = float(speed if speed is not None else getattr(settings, "cartesia_tts_speed", 1.0))
    vol = float(volume if volume is not None else getattr(settings, "cartesia_tts_volume", 1.0))
    spd = max(0.6, min(1.5, spd))
    vol = max(0.5, min(2.0, vol))
    return {"emotion": emo, "speed": spd, "volume": vol}


def sarvam_delivery_defaults() -> dict[str, float]:
    """Recommended Bulbul v3 pace/temperature for phone agents."""
    from server.config.env import get_settings

    settings = get_settings()
    pace = float(settings.sarvam_tts_pace)
    temp = float(settings.sarvam_tts_temperature)
    return {
        "pace": max(0.5, min(2.0, pace)),
        "temperature": max(0.01, min(1.0, temp)),
    }
