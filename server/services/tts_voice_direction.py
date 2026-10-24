"""
TTS delivery controls — not LLM-style text prompts.

Every provider exposes a different subset of the universal delivery knobs
(speed, pitch, temperature, volume, emotion). `tts_knob_specs` is the single
source of truth for what a provider/model supports, and
`normalize_tts_dynamics`/`provider_tts_payload` guarantee that a saved
universal value reaches the live call in the provider's native shape.

Sarvam Bulbul: v3 pace + temperature; v4-flash pace + pitch + loudness
(temperature is ignored by the engine); v2 pace + pitch + loudness.
Gnani: speed 0.85–1.15, pitch multiplier, volume.
Cartesia Sonic: generation_config {emotion, speed, volume}.
Gemini TTS: pace and pitch via delivery metadata; no numeric temperature.
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

CARTESIA_EMOTION_OPTIONS: tuple[tuple[str, str], ...] = (
    ("neutral", "Neutral · Balanced Natural"),
    ("calm", "Calm · Relaxed & Patient"),
    ("content", "Content · Friendly & Pleasant"),
    ("happy", "Happy · Upbeat & Enthusiastic"),
    ("confident", "Confident · Direct & Professional"),
    ("curious", "Curious · Engaging Questioning"),
    ("grateful", "Grateful · Warm & Welcoming"),
    ("peaceful", "Peaceful · Serene Consultation"),
    ("sympathetic", "Sympathetic · Empathetic Support"),
    ("sad", "Sad · Low & Empathetic"),
    ("angry", "Angry · Firm & Urgent"),
    ("scared", "Scared · Tense & Concerned"),
)

# Universal pitch offset range. Sarvam uses it directly; Gnani maps it onto
# a 0.5–1.5 multiplier; Gemini turns it into a delivery direction.
PITCH_RANGE = (-0.75, 0.75)
GNANI_PITCH_RANGE = (-0.75, 0.75)
GNANI_SPEED_RANGE = (0.85, 1.15)
CARTESIA_SPEED_RANGE = (0.6, 1.5)
CARTESIA_VOLUME_RANGE = (0.5, 2.0)
GEMINI_SPEED_RANGE = (0.25, 2.0)
DEFAULT_SARVAM_SPEED_RANGE = (0.5, 2.0)
DEFAULT_VOLUME_RANGE = (0.5, 2.0)
TEMPERATURE_RANGE = (0.01, 1.0)


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
    spd = max(CARTESIA_SPEED_RANGE[0], min(CARTESIA_SPEED_RANGE[1], spd))
    vol = max(CARTESIA_VOLUME_RANGE[0], min(CARTESIA_VOLUME_RANGE[1], vol))
    return {"emotion": emo, "speed": spd, "volume": vol}


def sarvam_delivery_defaults() -> dict[str, float]:
    """Recommended Bulbul v3 pace/temperature for phone agents."""
    from server.config.env import get_settings

    settings = get_settings()
    pace = float(settings.sarvam_tts_pace)
    temp = float(settings.sarvam_tts_temperature)
    return {
        "pace": max(DEFAULT_SARVAM_SPEED_RANGE[0], min(DEFAULT_SARVAM_SPEED_RANGE[1], pace)),
        "temperature": max(TEMPERATURE_RANGE[0], min(TEMPERATURE_RANGE[1], temp)),
    }


def _sarvam_model_meta(model: str | None) -> dict[str, Any]:
    from server.config.constants import constants

    return constants.TTS_MODELS.get(str(model or "").strip()) or {}


def _pace_range(provider: str, model: str | None = None) -> tuple[float, float]:
    if provider == "sarvam":
        pace = _sarvam_model_meta(model).get("pace")
        if isinstance(pace, (list, tuple)) and len(pace) == 2:
            return (float(pace[0]), float(pace[1]))
        return DEFAULT_SARVAM_SPEED_RANGE
    if provider == "gnani":
        return GNANI_SPEED_RANGE
    if provider == "cartesia":
        return CARTESIA_SPEED_RANGE
    if provider == "gemini":
        return GEMINI_SPEED_RANGE
    return DEFAULT_SARVAM_SPEED_RANGE


def resolve_speech_pace(provider: str, pace: Any = None, *, model: str | None = None) -> float:
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
    lower, upper = _pace_range(provider, model)
    return max(lower, min(upper, value))


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def gnani_pitch_multiplier(pitch: Any) -> float | None:
    """Map a universal pitch offset (-0.75..0.75) onto Gnani's 0.5–1.5 multiplier."""
    value = _as_float(pitch)
    if value is None:
        return None
    low, high = GNANI_PITCH_RANGE
    span = high if high > 0 else 1.0
    fraction = max(-1.0, min(1.0, value / span))
    return round(max(0.5, min(1.5, 1.0 + fraction * 0.5)), 3)


def gemini_speech_style(pace: float | None = None, pitch: Any = None) -> str:
    """Gemini controls cadence through delivery directions, not a PCM rate change."""
    speed = resolve_speech_pace("gemini", pace)
    delivery = "Relaxed, warm" if speed < 1.0 else ("Brisk, natural" if speed > 1.05 else "Warm, natural")
    register = ""
    pitch_value = _as_float(pitch)
    if pitch_value is not None:
        if pitch_value <= -0.3:
            register = "Use a noticeably deeper, fuller vocal register; "
        elif pitch_value <= -0.08:
            register = "Use a slightly deeper vocal register; "
        elif pitch_value >= 0.3:
            register = "Use a noticeably brighter, higher vocal register; "
        elif pitch_value >= 0.08:
            register = "Use a slightly brighter vocal register; "
    return (
        f"{delivery} conversational delivery at approximately {speed:.2f}x normal speaking pace; "
        f"{register}clear articulation, short natural pauses, no drawn-out syllables."
    )


def _range_spec(
    key: str,
    label: str,
    description: str,
    bounds: tuple[float, float],
    *,
    default: float,
    step: float,
    native: str,
    unit: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "description": description,
        "kind": "range",
        "min": bounds[0],
        "max": bounds[1],
        "step": step,
        "default": default,
        "native": native,
        "unit": unit,
    }


def tts_knob_specs(provider: str, model: str | None = None) -> list[dict[str, Any]]:
    """Every delivery knob the provider/model actually honours, in UI order."""
    provider = str(provider or "").strip().lower()
    specs: list[dict[str, Any]] = []
    if provider == "sarvam":
        meta = _sarvam_model_meta(model)
        pace = meta.get("pace") or DEFAULT_SARVAM_SPEED_RANGE
        specs.append(
            _range_spec(
                "speed",
                "Speaking Pace",
                "Native Bulbul pace control applied to every synthesized turn.",
                (float(pace[0]), float(pace[1])),
                default=1.0,
                step=0.05,
                native="pace",
                unit="x",
            )
        )
        temperature = meta.get("temperature")
        if temperature:
            specs.append(
                _range_spec(
                    "temperature",
                    "Expressive Inflection (Temperature)",
                    "Higher values increase tone variance and prosodic richness.",
                    (float(temperature[0]), float(temperature[1])),
                    default=0.7,
                    step=0.05,
                    native="temperature",
                )
            )
        pitch = meta.get("pitch")
        if pitch:
            specs.append(
                _range_spec(
                    "pitch",
                    "Pitch Offset",
                    "Negative values deepen the voice; positive values raise it.",
                    (float(pitch[0]), float(pitch[1])),
                    default=0.0,
                    step=0.01,
                    native="pitch",
                )
            )
        loudness = meta.get("loudness")
        if loudness:
            specs.append(
                _range_spec(
                    "volume",
                    "Volume (Loudness)",
                    "Native Bulbul loudness multiplier.",
                    (float(loudness[0]), float(loudness[1])),
                    default=1.0,
                    step=0.05,
                    native="loudness",
                    unit="x",
                )
            )
        return specs
    if provider == "gnani":
        specs.append(
            _range_spec(
                "speed",
                "Speaking Pace",
                "Vachana speed control, clamped to the engine's supported band.",
                GNANI_SPEED_RANGE,
                default=1.0,
                step=0.05,
                native="speed",
                unit="x",
            )
        )
        specs.append(
            _range_spec(
                "pitch",
                "Pitch Offset",
                "Mapped onto Vachana's 0.5–1.5 pitch multiplier.",
                GNANI_PITCH_RANGE,
                default=0.0,
                step=0.01,
                native="pitch",
            )
        )
        specs.append(
            _range_spec(
                "volume",
                "Volume Multiplier",
                "Vachana volume multiplier applied to every request.",
                CARTESIA_VOLUME_RANGE,
                default=1.0,
                step=0.05,
                native="volume",
                unit="x",
            )
        )
        return specs
    if provider == "cartesia":
        specs.append(
            _range_spec(
                "speed",
                "Speaking Pace",
                "Sonic generation speed sent in generation_config.",
                CARTESIA_SPEED_RANGE,
                default=1.0,
                step=0.05,
                native="speed",
                unit="x",
            )
        )
        specs.append(
            {
                "key": "emotion",
                "label": "Sonic Emotion Director",
                "description": "Emotion label sent in generation_config.",
                "kind": "select",
                "default": "neutral",
                "native": "emotion",
                "options": [{"value": value, "label": label} for value, label in CARTESIA_EMOTION_OPTIONS],
            }
        )
        specs.append(
            _range_spec(
                "volume",
                "Volume Multiplier",
                "Sonic volume sent in generation_config.",
                CARTESIA_VOLUME_RANGE,
                default=1.0,
                step=0.05,
                native="volume",
                unit="x",
            )
        )
        return specs
    if provider == "gemini":
        specs.append(
            _range_spec(
                "speed",
                "Speaking Pace",
                "Expressed as a Gemini delivery direction, not a PCM retime.",
                GEMINI_SPEED_RANGE,
                default=1.0,
                step=0.05,
                native="pace",
                unit="x",
            )
        )
        specs.append(
            _range_spec(
                "pitch",
                "Pitch Character",
                "Expressed as a deeper or brighter vocal-register direction.",
                PITCH_RANGE,
                default=0.0,
                step=0.01,
                native="pitch",
            )
        )
        return specs
    return specs


def normalize_tts_dynamics(
    provider: str,
    model: str | None,
    values: dict[str, Any] | None,
) -> dict[str, Any]:
    """Keep only supported knobs, clamped to the selected provider/model."""
    source = values if isinstance(values, dict) else {}
    normalized: dict[str, Any] = {}
    for spec in tts_knob_specs(provider, model):
        key = spec["key"]
        raw = source.get(key)
        if raw is None:
            continue
        if spec["kind"] == "select":
            text = str(raw).strip().lower()
            allowed = {option["value"] for option in spec.get("options") or []}
            if text in allowed:
                normalized[key] = text
            continue
        number = _as_float(raw)
        if number is None:
            continue
        normalized[key] = round(_clamp(number, (float(spec["min"]), float(spec["max"]))), 3)
    return normalized


def provider_tts_payload(
    provider: str,
    model: str | None,
    dynamics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Translate universal dynamics into the provider's native stream config keys."""
    provider = str(provider or "").strip().lower()
    values = normalize_tts_dynamics(provider, model, dynamics)
    payload: dict[str, Any] = {}
    if provider == "sarvam":
        if "speed" in values:
            payload["pace"] = values["speed"]
        if "temperature" in values:
            payload["temperature"] = values["temperature"]
        if "pitch" in values:
            payload["pitch"] = values["pitch"]
        if "volume" in values:
            payload["loudness"] = values["volume"]
        return payload
    if provider == "gnani":
        if "speed" in values:
            payload["pace"] = values["speed"]
        pitch = gnani_pitch_multiplier(values.get("pitch"))
        if pitch is not None:
            payload["pitch"] = pitch
        if "volume" in values:
            payload["volume"] = values["volume"]
        return payload
    if provider == "cartesia":
        if "speed" in values:
            payload["pace"] = values["speed"]
            payload["speed"] = values["speed"]
        if "emotion" in values:
            payload["emotion"] = values["emotion"]
        if "volume" in values:
            payload["volume"] = values["volume"]
        return payload
    if provider == "gemini":
        if "speed" in values:
            payload["pace"] = values["speed"]
        if "pitch" in values:
            payload["pitch"] = values["pitch"]
        return payload
    return payload
