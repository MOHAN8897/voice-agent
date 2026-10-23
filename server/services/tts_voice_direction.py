"""
TTS delivery controls — not LLM-style text prompts.

Cartesia Sonic: generation_config {emotion, speed, volume} (director-style).
Sarvam Bulbul v3: pace + temperature only (no system prompt / SSML).

Voice quality mainly comes from well-punctuated LLM text (see tts_speech_rules);
these knobs refine delivery.
"""
from __future__ import annotations

import math
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


def resolve_speech_pace(provider: str, pace: Any = None) -> float:
    """Resolve delivery speed before opening a provider; never retime carrier PCM."""
    if pace is None:
        from server.config.env import get_settings

        settings = get_settings()
        if provider == "sarvam":
            pace = settings.sarvam_tts_pace
        elif provider == "cartesia":
            pace = settings.cartesia_tts_speed
        else:
            pace = 1.0
    try:
        value = float(pace)
    except (TypeError, ValueError) as exc:
        raise ValueError("Speech pace must be a finite positive number") from exc
    if isinstance(pace, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError("Speech pace must be a finite positive number")
    if provider == "gnani":
        lower, upper = (0.85, 1.15)
    elif provider == "cartesia":
        lower, upper = (0.6, 1.5)
    elif provider == "gemini":
        lower, upper = (0.25, 2.0)
    else:
        lower, upper = (0.5, 2.0)
    return max(lower, min(upper, value))


def gemini_speech_style(pace: float | None = None) -> str:
    """Gemini controls cadence through delivery directions, not a PCM rate change."""
    speed = resolve_speech_pace("gemini", pace)
    delivery = "Relaxed, warm" if speed < 1.0 else ("Brisk, natural" if speed > 1.05 else "Warm, natural")
    return (
        f"{delivery} conversational delivery at approximately {speed:.2f}x normal speaking pace; "
        "clear articulation, short natural pauses, no drawn-out syllables."
    )
