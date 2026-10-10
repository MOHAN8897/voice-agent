"""
Official provider rates for Test Studio cost estimates.

Sources (verified 2026-09-03):
  Sarvam  — https://www.sarvam.ai/api-pricing
            STT realtime/streaming/batch ₹30/hour (diarization ₹45/hour)
            TTS bulbul realtime/streaming ₹3.00 per 1,000 characters
  OpenAI  — https://developers.openai.com/api/docs/pricing
            gpt-5.6-luna short: $0.20/M in, $0.02/M cached, $0.25/M write, $1.20/M out
            gpt-5.5 short: $5.00/M in, $0.50/M cached, $6.25/M write, $30/M out
            gpt-5.4 short: $2.50/M in, $0.25/M cached, $3.125/M write, $15/M out
  Cartesia — https://docs.cartesia.ai/pricing + https://cartesia.ai/pricing
            TTS ~1 credit/character; Pro $5 / 100K credits ≈ $50 / 1M chars
            STT ink-whisper websocket 1 credit/sec; ink-2 websocket 3 credits/sec
  Telnyx  — https://telnyx.com/pricing/voice-api (Voice API + SIP trunk + optional features)
            Components (pay-as-you-go list): Voice API $0.002/min, SIP from $0.005/min outbound
            (destination-specific — use rate deck / TELNYX_SIP_OUTBOUND_INDIA_USD_PER_MIN for IN),
            Media streaming WebSockets $0.0035/min, call recording $0.002/min when enabled.
  Gemini  — https://ai.google.dev/gemini-api/docs/pricing (Live API)
            Billed on actual text/audio/image tokens; usage_metadata is session-cumulative and
            prior context can be re-billed each turn — not wall-clock × list $/audio-minute.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Literal

PRICING_UPDATED_AT = "2026-09-27"

DEFAULT_FX_RATE_INR = 96.78

SARVAM_STT_INR_PER_HOUR = 30.0
SARVAM_STT_DIARIZATION_INR_PER_HOUR = 45.0
SARVAM_TTS_INR_PER_1K_CHARS = 3.0

# Vobiz Voice API rates (official pay-as-you-go list, Sep 2026).
# Voice API ₹0.65/min (inbound & outbound), Recording ₹0.0012/min, Transcription ₹0.0098/min.
VOBIZ_VOICE_OUTBOUND_INR_PER_MIN = 0.65
VOBIZ_VOICE_INBOUND_INR_PER_MIN = 0.65
VOBIZ_CALL_RECORDING_INR_PER_MIN = 0.0012
VOBIZ_CALL_TRANSCRIPTION_INR_PER_MIN = 0.0098
VOBIZ_MEDIA_STREAM_INR_PER_MIN = 0.0

# Cartesia Pro plan default (conservative estimate tier for dev console)
CARTESIA_PRO_USD_PER_CREDIT = 5.0 / 100_000.0
CARTESIA_TTS_USD_PER_M_CHARS = CARTESIA_PRO_USD_PER_CREDIT * 1_000_000.0  # $50/M

# Telnyx list rates (Voice API pricing, Sep 2026). PSTN realtime = API + SIP + media stream.
TELNYX_VOICE_API_USD_PER_MIN = 0.002
TELNYX_SIP_OUTBOUND_USD_PER_MIN = 0.005  # US / generic list; India varies — see below.
TELNYX_SIP_INBOUND_USD_PER_MIN = 0.0032
TELNYX_MEDIA_STREAM_USD_PER_MIN = 0.0035
TELNYX_CALL_RECORDING_USD_PER_MIN = 0.002
# Destination deck default for +91 outbound (override to match your Telnyx invoice).
TELNYX_SIP_OUTBOUND_INDIA_USD_PER_MIN = 0.009

# Legacy single-line aliases (US outbound + media, no recording) for quick comparisons.
TELNYX_OUTBOUND_USD_PER_MIN = (
    TELNYX_VOICE_API_USD_PER_MIN + TELNYX_SIP_OUTBOUND_USD_PER_MIN + TELNYX_MEDIA_STREAM_USD_PER_MIN
)
TELNYX_INBOUND_USD_PER_MIN = (
    TELNYX_VOICE_API_USD_PER_MIN + TELNYX_SIP_INBOUND_USD_PER_MIN + TELNYX_MEDIA_STREAM_USD_PER_MIN
)

OPENAI_USD_PER_M: dict[str, dict[str, float]] = {
    "gpt-realtime-2.1-mini": {
        "input": 0.60,
        "cached_input": 0.06,
        "cache_write": 0.60,
        "output": 2.40,
    },
    "gpt-realtime-2.1": {
        "input": 4.00,
        "cached_input": 0.40,
        "cache_write": 4.00,
        "output": 24.00,
    },
    "gpt-realtime-2": {
        "input": 4.00,
        "cached_input": 0.40,
        "cache_write": 4.00,
        "output": 24.00,
    },
    "gpt-5.6-luna": {
        "input": 0.20,
        "cached_input": 0.02,
        "cache_write": 0.25,
        "output": 1.20,
    },
    "gpt-5.5": {
        "input": 5.00,
        "cached_input": 0.50,
        "cache_write": 6.25,
        "output": 30.00,
    },
    "gpt-5.4": {
        "input": 2.50,
        "cached_input": 0.25,
        "cache_write": 3.125,
        "output": 15.00,
    },
    "gpt-5": {
        "input": 5.00,
        "cached_input": 0.50,
        "cache_write": 6.25,
        "output": 30.00,
    },
}

# Gemini Live native audio — ai.google.dev/gemini-api/docs/pricing (Live API, Sep 2026).
# gemini-3.8-live: text $0.75 / $4.50; audio $3.00 / $12.00; image/video $1.00/M.
# Published audio list minutes: $0.005 in / $0.018 out ≈ 25 tok/s × token rates
# ($3/M × 1500 tok/min = $0.0045, docs round to $0.005). Caching is not supported.
# gemini-2.5-flash-native-audio: text $0.50 / $2.00; audio $3.00 / $12.00;
# audio/video share the $3 input rate.
GEMINI_LIVE_AUDIO_TOKENS_PER_SEC = 25
GEMINI_LIVE_AUDIO_INPUT_USD_PER_MIN = 0.005
GEMINI_LIVE_AUDIO_OUTPUT_USD_PER_MIN = 0.018
# gemini-3.5-transcribe batch (post-call); list ≈ $0.009/min blended (preview).
GEMINI_35_TRANSCRIBE_USD_PER_MIN = 0.009


def cost_gemini_post_call_transcribe(*, duration_sec: float, model: str) -> dict[str, float]:
    minutes = max(0.0, float(duration_sec or 0)) / 60.0
    rate = GEMINI_35_TRANSCRIBE_USD_PER_MIN
    return {"usd": minutes * rate, "minutes": minutes, "usd_per_min": rate, "model": (model or "gemini-3.5-transcribe")}


OPENAI_MINI_TRANSCRIBE_USD_PER_MIN = 0.003


def cost_openai_live_transcribe(*, duration_sec: float, model: str = "gpt-4o-mini-transcribe") -> dict[str, float]:
    minutes = max(0.0, float(duration_sec or 0)) / 60.0
    rate = OPENAI_MINI_TRANSCRIBE_USD_PER_MIN
    return {"usd": minutes * rate, "minutes": minutes, "usd_per_min": rate, "model": model or "gpt-4o-mini-transcribe"}

GEMINI_LIVE_USD_PER_M: dict[str, dict[str, float]] = {
    "gemini-3.8-live": {
        "input": 0.75,
        "cached_input": 0.0,
        "cache_write": 0.0,
        "output": 4.50,
    },
    "gemini-2.5-flash-native-audio-latest": {
        "input": 0.50,
        "cached_input": 0.0,
        "cache_write": 0.0,
        "output": 2.00,
    },
}

GEMINI_LIVE_AUDIO_USD_PER_M: dict[str, dict[str, float]] = {
    "gemini-3.8-live": {
        "input": 3.00,
        "cached_input": 0.0,
        "output": 12.00,
    },
    "gemini-2.5-flash-native-audio-latest": {
        "input": 3.00,
        "cached_input": 0.0,
        "output": 12.00,
    },
}

GEMINI_LIVE_IMAGE_USD_PER_M: dict[str, float] = {
    "gemini-3.8-live": 1.00,
    "gemini-2.5-flash-native-audio-latest": 3.00,
}

OPENAI_AUDIO_USD_PER_M: dict[str, dict[str, float]] = {
    "gpt-realtime-2.1-mini": {
        "input": 10.00,
        "cached_input": 0.30,
        "output": 20.00,
    },
    "gpt-realtime-2.1": {
        "input": 32.00,
        "cached_input": 0.40,
        "output": 64.00,
    },
    "gpt-realtime-2": {
        "input": 32.00,
        "cached_input": 0.40,
        "output": 64.00,
    },
}

CacheEvent = Literal["cache_hit", "cache_write", "partial_hit", "cache_miss"]


def resolve_tts_provider(*, provider: str, model: str = "") -> str:
    p = (provider or "sarvam").lower()
    m = (model or "").lower()
    if p == "cartesia" or m.startswith("sonic"):
        return "cartesia"
    return "sarvam"


def resolve_stt_provider(*, provider: str, model: str = "") -> str:
    p = (provider or "sarvam").lower()
    m = (model or "").lower()
    if p == "cartesia" or m.startswith("ink"):
        return "cartesia"
    return "sarvam"


def openai_rates_for_model(model: str | None) -> dict[str, float]:
    m = (model or "gpt-realtime-2.1-mini").lower().strip()
    if m in OPENAI_USD_PER_M:
        return OPENAI_USD_PER_M[m]
    for key in sorted(OPENAI_USD_PER_M, key=len, reverse=True):
        if m.startswith(key):
            return OPENAI_USD_PER_M[key]
    return OPENAI_USD_PER_M["gpt-5.6-luna"]


def gemini_rates_for_model(model: str | None) -> dict[str, float]:
    from server.realtime.models import is_gemini_live_voice_model

    m = (model or "gemini-3.8-live").lower().strip()
    if m in GEMINI_LIVE_USD_PER_M:
        return GEMINI_LIVE_USD_PER_M[m]
    if is_gemini_live_voice_model(m):
        return GEMINI_LIVE_USD_PER_M["gemini-3.8-live"]
    return GEMINI_LIVE_USD_PER_M["gemini-3.8-live"]


def gemini_audio_rates_for_model(model: str | None) -> dict[str, float]:
    from server.realtime.models import is_gemini_live_voice_model

    m = (model or "gemini-3.8-live").lower().strip()
    if m in GEMINI_LIVE_AUDIO_USD_PER_M:
        return GEMINI_LIVE_AUDIO_USD_PER_M[m]
    if is_gemini_live_voice_model(m):
        return GEMINI_LIVE_AUDIO_USD_PER_M["gemini-3.8-live"]
    return GEMINI_LIVE_AUDIO_USD_PER_M["gemini-3.8-live"]


def gemini_image_rate_for_model(model: str | None) -> float:
    from server.realtime.models import is_gemini_live_voice_model

    m = (model or "gemini-3.8-live").lower().strip()
    if m in GEMINI_LIVE_IMAGE_USD_PER_M:
        return GEMINI_LIVE_IMAGE_USD_PER_M[m]
    if is_gemini_live_voice_model(m):
        return GEMINI_LIVE_IMAGE_USD_PER_M["gemini-3.8-live"]
    return GEMINI_LIVE_IMAGE_USD_PER_M["gemini-3.8-live"]


def openai_audio_rates_for_model(model: str | None) -> dict[str, float]:
    m = (model or "gpt-realtime-2.1-mini").lower().strip()
    if m in OPENAI_AUDIO_USD_PER_M:
        return OPENAI_AUDIO_USD_PER_M[m]
    for key in sorted(OPENAI_AUDIO_USD_PER_M, key=len, reverse=True):
        if m.startswith(key):
            return OPENAI_AUDIO_USD_PER_M[key]
    return OPENAI_AUDIO_USD_PER_M["gpt-realtime-2.1-mini"]


def cartesia_stt_credits_per_sec(*, model: str = "", realtime: bool = True) -> float:
    """Cartesia STT credit burn rate (Pro-plan credits, not Sarvam)."""
    m = (model or "ink-whisper").lower()
    if "ink-2" in m:
        return 3.0 if realtime else 1.5
    return 1.0 if realtime else 0.5


_FX_LIVE: dict[str, Any] = {"rate": None, "fetched_at": 0.0, "as_of": None}


def clear_fx_live_cache() -> None:
    _FX_LIVE.update({"rate": None, "fetched_at": 0.0, "as_of": None})


def _fetch_usd_inr() -> tuple[float | None, str | None]:
    try:
        import httpx

        response = httpx.get("https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR", timeout=3.0, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
        rate = float((data.get("rates") or {}).get("INR") or 0)
        as_of = str(data.get("date") or "") or None
        if rate > 0:
            return rate, as_of
    except Exception:
        return None, None
    return None, None


def resolve_fx_rate_inr(*, preferred: float | None = None) -> dict[str, Any]:
    """USD→INR for display. Gemini/OpenAI invoice USD; GST is not added."""
    from server.config.env import get_settings

    settings = get_settings()
    env_rate = float(preferred or 0) or float(getattr(settings, "fx_rate_inr", 0) or DEFAULT_FX_RATE_INR)
    if env_rate <= 0:
        env_rate = DEFAULT_FX_RATE_INR
    live = bool(getattr(settings, "fx_rate_live", False))
    if not live:
        return {"rate": env_rate, "source": "env", "as_of": None}
    now = time.monotonic()
    ttl = float(getattr(settings, "fx_rate_live_ttl_sec", 21600) or 21600)
    cached = _FX_LIVE.get("rate")
    fetched_at = float(_FX_LIVE.get("fetched_at") or 0)
    if cached and (now - fetched_at) < ttl:
        return {"rate": float(cached), "source": "live_cache", "as_of": _FX_LIVE.get("as_of")}
    rate, as_of = _fetch_usd_inr()
    if rate and rate > 0:
        _FX_LIVE.update({"rate": rate, "fetched_at": now, "as_of": as_of})
        return {"rate": float(rate), "source": "live", "as_of": as_of}
    return {"rate": env_rate, "source": "env_fallback", "as_of": None}


def build_pricing_metadata(fx_rate_inr: float) -> dict[str, Any]:
    fx = float(fx_rate_inr) or DEFAULT_FX_RATE_INR
    stt_usd_per_hour = SARVAM_STT_INR_PER_HOUR / fx
    tts_usd_per_1k = SARVAM_TTS_INR_PER_1K_CHARS / fx
    cartesia_stt_usd_per_hour_whisper = cartesia_stt_credits_per_sec(model="ink-whisper") * 3600 * CARTESIA_PRO_USD_PER_CREDIT
    cartesia_stt_usd_per_hour_ink2 = cartesia_stt_credits_per_sec(model="ink-2") * 3600 * CARTESIA_PRO_USD_PER_CREDIT
    return {
        "updated_at": PRICING_UPDATED_AT,
        "openai:gpt-4o-mini-transcribe": {"usd_per_minute": 0.003},
        "transcription_note": "Gemini PSTN realtime_voice uses post-call gemini-3.5-transcribe on Telnyx recordings (separate line item). OpenAI Realtime uses gpt-4o-mini-transcribe during the call.",
        "fx_rate_inr": fx,
        "sources": {
            "sarvam": "https://www.sarvam.ai/api-pricing",
            "openai": "https://developers.openai.com/api/docs/pricing",
            "cartesia": "https://docs.cartesia.ai/pricing",
            "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
            "telnyx": "https://telnyx.com/pricing/call-control",
        },
        "notes": {
            "stt": "Sarvam bills audio duration (₹30/hour). Cartesia STT bills credits/sec (Pro plan default).",
            "tts": "Sarvam bills Unicode characters (₹3 / 1k). Cartesia ~1 credit/char (Pro ≈ $50 / 1M chars).",
            "llm": "OpenAI bills tokenizer tokens. Gemini Live bills text/audio/image tokens (no prompt cache on 3.8-live).",
            "inr": "INR is USD×FX for display. Providers invoice USD. GST is not added.",
            "cost_inr_per_min": "All-in (model tokens + Telnyx wall-clock components), prorated by connected seconds.",
            "telnyx": "Sum of Voice API + SIP (destination) + media WebSocket (+ recording if estimated). Not one flat ₹/min.",
            "gemini_live": "Model cost from cumulative usage_metadata deltas (text+audio+image tokens). "
            "List $0.005/$0.018 audio-min is reference only — silence does not bill output audio.",
            "gemini_audio_list": "Published $0.005 in / $0.018 out per continuous audio minute ≈ 25 tok/s × $3/$12 per 1M.",
        },
        "sarvam:saaras:v3": {
            "unit": "minute",
            "usd_per_unit": stt_usd_per_hour / 60.0,
            "inr_per_hour": SARVAM_STT_INR_PER_HOUR,
            "billing": "audio_seconds",
            "updated_at": PRICING_UPDATED_AT,
        },
        "sarvam:saaras:v3-realtime": {
            "unit": "minute",
            "usd_per_unit": stt_usd_per_hour / 60.0,
            "inr_per_hour": SARVAM_STT_INR_PER_HOUR,
            "billing": "audio_seconds",
            "updated_at": PRICING_UPDATED_AT,
        },
        "sarvam:bulbul:v3": {
            "unit": "1k_chars",
            "usd_per_unit": tts_usd_per_1k,
            "inr_per_1k_chars": SARVAM_TTS_INR_PER_1K_CHARS,
            "billing": "characters",
            "updated_at": PRICING_UPDATED_AT,
        },
        "sarvam:bulbul:v2": {
            "unit": "1k_chars",
            "usd_per_unit": tts_usd_per_1k,
            "inr_per_1k_chars": SARVAM_TTS_INR_PER_1K_CHARS,
            "billing": "characters",
            "updated_at": PRICING_UPDATED_AT,
        },
        "openai:gpt-realtime-2.1-mini": {
            "unit": "1m_tokens",
            "usd_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1-mini"]["input"],
            "usd_cached_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1-mini"]["cached_input"],
            "usd_cache_write_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1-mini"]["cache_write"],
            "usd_output_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1-mini"]["output"],
            "usd_audio_input_per_m": OPENAI_AUDIO_USD_PER_M["gpt-realtime-2.1-mini"]["input"],
            "usd_audio_cached_input_per_m": OPENAI_AUDIO_USD_PER_M["gpt-realtime-2.1-mini"]["cached_input"],
            "usd_audio_output_per_m": OPENAI_AUDIO_USD_PER_M["gpt-realtime-2.1-mini"]["output"],
            "billing": "tokens_with_cache",
            "updated_at": PRICING_UPDATED_AT,
        },
        "openai:gpt-realtime-2.1": {
            "unit": "1m_tokens",
            "usd_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1"]["input"],
            "usd_cached_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1"]["cached_input"],
            "usd_cache_write_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1"]["cache_write"],
            "usd_output_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1"]["output"],
            "usd_audio_input_per_m": OPENAI_AUDIO_USD_PER_M["gpt-realtime-2.1"]["input"],
            "usd_audio_cached_input_per_m": OPENAI_AUDIO_USD_PER_M["gpt-realtime-2.1"]["cached_input"],
            "usd_audio_output_per_m": OPENAI_AUDIO_USD_PER_M["gpt-realtime-2.1"]["output"],
            "billing": "tokens_with_cache",
            "updated_at": PRICING_UPDATED_AT,
        },
        "openai:gpt-realtime-2": {
            "unit": "1m_tokens",
            "usd_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2"]["input"],
            "usd_cached_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2"]["cached_input"],
            "usd_cache_write_per_m": OPENAI_USD_PER_M["gpt-realtime-2"]["cache_write"],
            "usd_output_per_m": OPENAI_USD_PER_M["gpt-realtime-2"]["output"],
            "usd_audio_input_per_m": OPENAI_AUDIO_USD_PER_M["gpt-realtime-2"]["input"],
            "usd_audio_cached_input_per_m": OPENAI_AUDIO_USD_PER_M["gpt-realtime-2"]["cached_input"],
            "usd_audio_output_per_m": OPENAI_AUDIO_USD_PER_M["gpt-realtime-2"]["output"],
            "billing": "tokens_with_cache",
            "updated_at": PRICING_UPDATED_AT,
        },
        "gemini:gemini-3.8-live": {
            "unit": "1m_tokens",
            "usd_input_per_m": GEMINI_LIVE_USD_PER_M["gemini-3.8-live"]["input"],
            "usd_cached_input_per_m": GEMINI_LIVE_USD_PER_M["gemini-3.8-live"]["cached_input"],
            "usd_cache_write_per_m": GEMINI_LIVE_USD_PER_M["gemini-3.8-live"]["cache_write"],
            "usd_output_per_m": GEMINI_LIVE_USD_PER_M["gemini-3.8-live"]["output"],
            "usd_audio_input_per_m": GEMINI_LIVE_AUDIO_USD_PER_M["gemini-3.8-live"]["input"],
            "usd_audio_cached_input_per_m": GEMINI_LIVE_AUDIO_USD_PER_M["gemini-3.8-live"]["cached_input"],
            "usd_audio_output_per_m": GEMINI_LIVE_AUDIO_USD_PER_M["gemini-3.8-live"]["output"],
            "usd_image_input_per_m": GEMINI_LIVE_IMAGE_USD_PER_M["gemini-3.8-live"],
            "usd_audio_input_per_min_list": GEMINI_LIVE_AUDIO_INPUT_USD_PER_MIN,
            "usd_audio_output_per_min_list": GEMINI_LIVE_AUDIO_OUTPUT_USD_PER_MIN,
            "billing": "tokens_audio_native",
            "updated_at": PRICING_UPDATED_AT,
        },
        "gemini:gemini-2.5-flash-native-audio-latest": {
            "unit": "1m_tokens",
            "usd_input_per_m": GEMINI_LIVE_USD_PER_M["gemini-2.5-flash-native-audio-latest"]["input"],
            "usd_cached_input_per_m": GEMINI_LIVE_USD_PER_M["gemini-2.5-flash-native-audio-latest"]["cached_input"],
            "usd_cache_write_per_m": GEMINI_LIVE_USD_PER_M["gemini-2.5-flash-native-audio-latest"]["cache_write"],
            "usd_output_per_m": GEMINI_LIVE_USD_PER_M["gemini-2.5-flash-native-audio-latest"]["output"],
            "usd_audio_input_per_m": GEMINI_LIVE_AUDIO_USD_PER_M["gemini-2.5-flash-native-audio-latest"]["input"],
            "usd_audio_cached_input_per_m": GEMINI_LIVE_AUDIO_USD_PER_M["gemini-2.5-flash-native-audio-latest"]["cached_input"],
            "usd_audio_output_per_m": GEMINI_LIVE_AUDIO_USD_PER_M["gemini-2.5-flash-native-audio-latest"]["output"],
            "usd_image_input_per_m": GEMINI_LIVE_IMAGE_USD_PER_M["gemini-2.5-flash-native-audio-latest"],
            "usd_audio_input_per_min_list": GEMINI_LIVE_AUDIO_INPUT_USD_PER_MIN,
            "usd_audio_output_per_min_list": GEMINI_LIVE_AUDIO_OUTPUT_USD_PER_MIN,
            "billing": "tokens_audio_native",
            "updated_at": PRICING_UPDATED_AT,
        },
        "openai:gpt-5.6-luna": {
            "unit": "1m_tokens",
            "usd_per_unit": OPENAI_USD_PER_M["gpt-5.6-luna"]["input"] / 1000.0,
            "usd_input_per_m": OPENAI_USD_PER_M["gpt-5.6-luna"]["input"],
            "usd_cached_input_per_m": OPENAI_USD_PER_M["gpt-5.6-luna"]["cached_input"],
            "usd_cache_write_per_m": OPENAI_USD_PER_M["gpt-5.6-luna"]["cache_write"],
            "usd_output_per_m": OPENAI_USD_PER_M["gpt-5.6-luna"]["output"],
            "billing": "tokens_with_cache",
            "updated_at": PRICING_UPDATED_AT,
        },
        "openai:gpt-5.5": {
            "unit": "1m_tokens",
            "usd_input_per_m": OPENAI_USD_PER_M["gpt-5.5"]["input"],
            "usd_cached_input_per_m": OPENAI_USD_PER_M["gpt-5.5"]["cached_input"],
            "usd_cache_write_per_m": OPENAI_USD_PER_M["gpt-5.5"]["cache_write"],
            "usd_output_per_m": OPENAI_USD_PER_M["gpt-5.5"]["output"],
            "billing": "tokens_with_cache",
            "updated_at": PRICING_UPDATED_AT,
        },
        "openai:gpt-5.4": {
            "unit": "1m_tokens",
            "usd_input_per_m": OPENAI_USD_PER_M["gpt-5.4"]["input"],
            "usd_cached_input_per_m": OPENAI_USD_PER_M["gpt-5.4"]["cached_input"],
            "usd_cache_write_per_m": OPENAI_USD_PER_M["gpt-5.4"]["cache_write"],
            "usd_output_per_m": OPENAI_USD_PER_M["gpt-5.4"]["output"],
            "billing": "tokens_with_cache",
            "updated_at": PRICING_UPDATED_AT,
        },
        "cartesia:sonic-3.5": {
            "unit": "1m_chars",
            "usd_per_unit": CARTESIA_TTS_USD_PER_M_CHARS,
            "billing": "characters",
            "updated_at": PRICING_UPDATED_AT,
        },
        "cartesia:sonic-3": {
            "unit": "1m_chars",
            "usd_per_unit": CARTESIA_TTS_USD_PER_M_CHARS,
            "billing": "characters",
            "updated_at": PRICING_UPDATED_AT,
        },
        "cartesia:ink-whisper": {
            "unit": "second",
            "credits_per_sec": cartesia_stt_credits_per_sec(model="ink-whisper"),
            "usd_per_hour": cartesia_stt_usd_per_hour_whisper,
            "billing": "audio_seconds",
            "updated_at": PRICING_UPDATED_AT,
        },
        "cartesia:ink-2": {
            "unit": "second",
            "credits_per_sec": cartesia_stt_credits_per_sec(model="ink-2"),
            "usd_per_hour": cartesia_stt_usd_per_hour_ink2,
            "billing": "audio_seconds",
            "updated_at": PRICING_UPDATED_AT,
        },
        "telnyx:voice_api": {
            "unit": "minute",
            "usd_per_unit": TELNYX_VOICE_API_USD_PER_MIN,
            "billing": "connected_call",
            "updated_at": PRICING_UPDATED_AT,
        },
        "telnyx:sip_outbound": {
            "unit": "minute",
            "usd_per_unit": TELNYX_SIP_OUTBOUND_USD_PER_MIN,
            "billing": "destination_specific",
            "updated_at": PRICING_UPDATED_AT,
        },
        "telnyx:sip_outbound_india": {
            "unit": "minute",
            "usd_per_unit": _telnyx_sip_outbound_india_rate(),
            "billing": "destination_specific",
            "updated_at": PRICING_UPDATED_AT,
        },
        "telnyx:sip_inbound": {
            "unit": "minute",
            "usd_per_unit": TELNYX_SIP_INBOUND_USD_PER_MIN,
            "billing": "connected_call",
            "updated_at": PRICING_UPDATED_AT,
        },
        "telnyx:media_stream": {
            "unit": "minute",
            "usd_per_unit": TELNYX_MEDIA_STREAM_USD_PER_MIN,
            "billing": "websocket_media",
            "updated_at": PRICING_UPDATED_AT,
        },
        "telnyx:call_recording": {
            "unit": "minute",
            "usd_per_unit": TELNYX_CALL_RECORDING_USD_PER_MIN,
            "billing": "optional",
            "updated_at": PRICING_UPDATED_AT,
        },
        "telnyx:outbound": {
            "unit": "minute",
            "usd_per_unit": TELNYX_OUTBOUND_USD_PER_MIN,
            "billing": "voice_api_plus_sip_us_plus_media",
            "updated_at": PRICING_UPDATED_AT,
        },
        "telnyx:inbound": {
            "unit": "minute",
            "usd_per_unit": TELNYX_INBOUND_USD_PER_MIN,
            "billing": "voice_api_plus_sip_inbound_plus_media",
            "updated_at": PRICING_UPDATED_AT,
        },
        "vobiz:voice_outbound": {
            "unit": "minute",
            "inr_per_unit": VOBIZ_VOICE_OUTBOUND_INR_PER_MIN,
            "usd_per_unit": VOBIZ_VOICE_OUTBOUND_INR_PER_MIN / fx,
            "billing": "connected_call_prorated",
            "updated_at": PRICING_UPDATED_AT,
        },
        "vobiz:voice_inbound": {
            "unit": "minute",
            "inr_per_unit": VOBIZ_VOICE_INBOUND_INR_PER_MIN,
            "usd_per_unit": VOBIZ_VOICE_INBOUND_INR_PER_MIN / fx,
            "billing": "connected_call_prorated",
            "updated_at": PRICING_UPDATED_AT,
        },
        "vobiz:call_recording": {
            "unit": "minute",
            "inr_per_unit": VOBIZ_CALL_RECORDING_INR_PER_MIN,
            "usd_per_unit": VOBIZ_CALL_RECORDING_INR_PER_MIN / fx,
            "billing": "optional",
            "updated_at": PRICING_UPDATED_AT,
        },
        "vobiz:call_transcription": {
            "unit": "minute",
            "inr_per_unit": VOBIZ_CALL_TRANSCRIPTION_INR_PER_MIN,
            "usd_per_unit": VOBIZ_CALL_TRANSCRIPTION_INR_PER_MIN / fx,
            "billing": "optional",
            "updated_at": PRICING_UPDATED_AT,
        },
    }


def classify_cache_event(*, input_tokens: int, cached_tokens: int, cache_write_tokens: int) -> CacheEvent:
    cached = max(0, int(cached_tokens or 0))
    written = max(0, int(cache_write_tokens or 0))
    if cached > 0 and written > 0:
        return "partial_hit"
    if cached > 0:
        return "cache_hit"
    if written > 0:
        return "cache_write"
    return "cache_miss"


def split_llm_tokens(*, input_tokens: int, cached_tokens: int, cache_write_tokens: int) -> dict[str, int]:
    """Mutually exclusive billing buckets.

    OpenAI reports cached_tokens and cache_write_tokens as usage details.
    Writes are billed at 1.25× instead of the uncached input rate, not in addition
    to it. If write+cached exceeds input (known API quirk), writes are capped.
    """
    inp = max(0, int(input_tokens or 0))
    cached = min(inp, max(0, int(cached_tokens or 0)))
    written = max(0, int(cache_write_tokens or 0))
    written_billed = min(written, max(0, inp - cached))
    uncached = max(0, inp - cached - written_billed)
    return {
        "input": inp,
        "cached": cached,
        "written": written_billed,
        "uncached": uncached,
    }


def cost_stt_usd(
    *,
    audio_sec: float,
    fx_rate_inr: float,
    stt_provider: str = "sarvam",
    stt_model: str = "",
) -> float:
    sec = max(0.0, float(audio_sec or 0))
    if resolve_stt_provider(provider=stt_provider, model=stt_model) == "cartesia":
        credits = cartesia_stt_credits_per_sec(model=stt_model, realtime=True) * sec
        return credits * CARTESIA_PRO_USD_PER_CREDIT
    hours = sec / 3600.0
    return (hours * SARVAM_STT_INR_PER_HOUR) / float(fx_rate_inr or 95.64)


def cost_tts_usd(
    *,
    chars: int,
    provider: str,
    model: str = "",
    fx_rate_inr: float,
) -> float:
    n = max(0, int(chars or 0))
    if resolve_tts_provider(provider=provider, model=model) == "cartesia":
        return n * CARTESIA_TTS_USD_PER_M_CHARS / 1_000_000.0
    return (n / 1000.0 * SARVAM_TTS_INR_PER_1K_CHARS) / float(fx_rate_inr or 95.64)


def cost_llm_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    llm_model: str | None = None,
    input_audio_tokens: int = 0,
    output_audio_tokens: int = 0,
    cached_audio_tokens: int = 0,
    input_image_tokens: int = 0,
) -> dict[str, float]:
    audio_in_tok = max(0, int(input_audio_tokens or 0))
    audio_out_tok = max(0, int(output_audio_tokens or 0))
    image_in_tok = max(0, int(input_image_tokens or 0))
    text_in = max(0, int(input_tokens or 0) - audio_in_tok - image_in_tok)
    text_out = max(0, int(output_tokens or 0) - audio_out_tok)
    audio_cached = min(audio_in_tok, max(0, int(cached_audio_tokens or 0)))
    if audio_cached == 0 and cached_tokens:
        audio_cached = min(audio_in_tok, max(0, int(cached_tokens or 0) - text_in))
    text_cached = max(0, int(cached_tokens or 0) - audio_cached)
    parts = split_llm_tokens(
        input_tokens=text_in,
        cached_tokens=text_cached,
        cache_write_tokens=cache_write_tokens,
    )
    from server.realtime.models import is_gemini_live_voice_model

    gemini = is_gemini_live_voice_model(llm_model)
    if gemini:
        rates = gemini_rates_for_model(llm_model)
        audio_rates = gemini_audio_rates_for_model(llm_model)
    else:
        rates = openai_rates_for_model(llm_model)
        audio_rates = openai_audio_rates_for_model(llm_model)
    uncached = parts["uncached"] * rates["input"] / 1_000_000.0
    cached = parts["cached"] * rates["cached_input"] / 1_000_000.0
    written = parts["written"] * rates["cache_write"] / 1_000_000.0
    output = text_out * rates["output"] / 1_000_000.0
    audio_uncached = audio_in_tok - audio_cached
    audio_in = (
        audio_uncached * audio_rates["input"]
        + audio_cached * audio_rates.get("cached_input", audio_rates["input"])
    ) / 1_000_000.0
    audio_out = audio_out_tok * audio_rates["output"] / 1_000_000.0
    image_in = (image_in_tok * gemini_image_rate_for_model(llm_model) / 1_000_000.0) if gemini else 0.0
    return {
        "uncached_usd": uncached,
        "cached_usd": cached,
        "cache_write_usd": written,
        "output_usd": output,
        "audio_input_usd": audio_in,
        "audio_output_usd": audio_out,
        "image_input_usd": image_in,
        "total_usd": uncached + cached + written + output + audio_in + audio_out + image_in,
    }


def _telnyx_env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def telnyx_estimate_call_recording() -> bool:
    """Whether to include Telnyx call-recording $/min in PSTN estimates (default on)."""
    return os.getenv("TELNYX_ESTIMATE_CALL_RECORDING", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _telnyx_sip_outbound_india_rate() -> float:
    return _telnyx_env_float("TELNYX_SIP_OUTBOUND_INDIA_USD_PER_MIN", TELNYX_SIP_OUTBOUND_INDIA_USD_PER_MIN)


def telnyx_destination_country_from_e164(e164: str | None) -> str | None:
    digits = re.sub(r"\D", "", str(e164 or ""))
    if not digits:
        return None
    if digits.startswith("91") and len(digits) >= 12:
        return "IN"
    if digits.startswith("1") and len(digits) >= 11:
        return "US"
    return None


def telnyx_sip_usd_per_min(*, direction: str | None, destination_country: str | None) -> float:
    inbound = str(direction or "outbound").strip().lower() == "inbound"
    if inbound:
        return _telnyx_env_float("TELNYX_SIP_INBOUND_USD_PER_MIN", TELNYX_SIP_INBOUND_USD_PER_MIN)
    country = (destination_country or "").strip().upper()
    if country == "IN":
        return _telnyx_sip_outbound_india_rate()
    return _telnyx_env_float("TELNYX_SIP_OUTBOUND_USD_PER_MIN", TELNYX_SIP_OUTBOUND_USD_PER_MIN)


def cost_telnyx_call_breakdown(
    *,
    duration_sec: float | int | None,
    direction: str | None = "outbound",
    media_streaming: bool = False,
    call_recording: bool = False,
    destination_country: str | None = None,
) -> dict[str, float | str | None]:
    """Telnyx Voice API + SIP + optional media stream / recording (wall-clock minutes)."""
    minutes = max(0.0, float(duration_sec or 0)) / 60.0
    if minutes <= 0:
        return {
            "minutes": 0.0,
            "voice_api_usd": 0.0,
            "sip_usd": 0.0,
            "media_stream_usd": 0.0,
            "call_recording_usd": 0.0,
            "total_usd": 0.0,
            "destination_country": destination_country,
            "sip_usd_per_min": 0.0,
        }
    voice_rate = _telnyx_env_float("TELNYX_VOICE_API_USD_PER_MIN", TELNYX_VOICE_API_USD_PER_MIN)
    sip_rate = telnyx_sip_usd_per_min(direction=direction, destination_country=destination_country)
    media_rate = (
        _telnyx_env_float("TELNYX_MEDIA_STREAM_USD_PER_MIN", TELNYX_MEDIA_STREAM_USD_PER_MIN)
        if media_streaming
        else 0.0
    )
    recording_rate = (
        _telnyx_env_float("TELNYX_CALL_RECORDING_USD_PER_MIN", TELNYX_CALL_RECORDING_USD_PER_MIN)
        if call_recording
        else 0.0
    )
    voice_api = minutes * voice_rate
    sip = minutes * sip_rate
    media = minutes * media_rate
    recording = minutes * recording_rate
    return {
        "minutes": minutes,
        "voice_api_usd": voice_api,
        "sip_usd": sip,
        "media_stream_usd": media,
        "call_recording_usd": recording,
        "total_usd": voice_api + sip + media + recording,
        "destination_country": destination_country,
        "sip_usd_per_min": sip_rate,
    }


def cost_telnyx_call_usd(
    *,
    duration_sec: float | int | None,
    direction: str | None = "outbound",
    media_streaming: bool = False,
    call_recording: bool = False,
    destination_country: str | None = None,
) -> float:
    return float(
        cost_telnyx_call_breakdown(
            duration_sec=duration_sec,
            direction=direction,
            media_streaming=media_streaming,
            call_recording=call_recording,
            destination_country=destination_country,
        )["total_usd"]
    )


def _vobiz_env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def cost_vobiz_call_breakdown(
    *,
    duration_sec: float | int | None,
    direction: str | None = "outbound",
    call_recording: bool = False,
    call_transcription: bool = False,
    fx_rate_inr: float = 96.78,
) -> dict[str, float | str | None]:
    """Vobiz Voice API + optional call recording / transcription (prorated wall-clock minutes)."""
    minutes = max(0.0, float(duration_sec or 0)) / 60.0
    fx = float(fx_rate_inr or DEFAULT_FX_RATE_INR)
    if minutes <= 0:
        return {
            "minutes": 0.0,
            "voice_inr": 0.0,
            "voice_usd": 0.0,
            "recording_inr": 0.0,
            "recording_usd": 0.0,
            "transcription_inr": 0.0,
            "transcription_usd": 0.0,
            "total_inr": 0.0,
            "total_usd": 0.0,
            "rate_inr_per_min": 0.0,
            "rate_usd_per_min": 0.0,
            "direction": direction,
        }
    inbound = str(direction or "outbound").strip().lower() == "inbound"
    base_voice_rate = _vobiz_env_float(
        "VOBIZ_VOICE_INBOUND_INR_PER_MIN" if inbound else "VOBIZ_VOICE_OUTBOUND_INR_PER_MIN",
        VOBIZ_VOICE_INBOUND_INR_PER_MIN if inbound else VOBIZ_VOICE_OUTBOUND_INR_PER_MIN,
    )
    recording_rate = (
        _vobiz_env_float("VOBIZ_CALL_RECORDING_INR_PER_MIN", VOBIZ_CALL_RECORDING_INR_PER_MIN)
        if call_recording
        else 0.0
    )
    transcription_rate = (
        _vobiz_env_float("VOBIZ_CALL_TRANSCRIPTION_INR_PER_MIN", VOBIZ_CALL_TRANSCRIPTION_INR_PER_MIN)
        if call_transcription
        else 0.0
    )
    voice_inr = minutes * base_voice_rate
    recording_inr = minutes * recording_rate
    transcription_inr = minutes * transcription_rate
    total_inr = voice_inr + recording_inr + transcription_inr
    total_usd = total_inr / fx if fx > 0 else 0.0
    rate_inr_per_min = base_voice_rate + recording_rate + transcription_rate
    rate_usd_per_min = rate_inr_per_min / fx if fx > 0 else 0.0
    return {
        "minutes": minutes,
        "voice_inr": voice_inr,
        "voice_usd": voice_inr / fx if fx > 0 else 0.0,
        "recording_inr": recording_inr,
        "recording_usd": recording_inr / fx if fx > 0 else 0.0,
        "transcription_inr": transcription_inr,
        "transcription_usd": transcription_inr / fx if fx > 0 else 0.0,
        "total_inr": total_inr,
        "total_usd": total_usd,
        "rate_inr_per_min": rate_inr_per_min,
        "rate_usd_per_min": rate_usd_per_min,
        "direction": direction,
    }


def cost_vobiz_call_usd(
    *,
    duration_sec: float | int | None,
    direction: str | None = "outbound",
    call_recording: bool = False,
    call_transcription: bool = False,
    fx_rate_inr: float = 96.78,
) -> float:
    return float(
        cost_vobiz_call_breakdown(
            duration_sec=duration_sec,
            direction=direction,
            call_recording=call_recording,
            call_transcription=call_transcription,
            fx_rate_inr=fx_rate_inr,
        )["total_usd"]
    )



def estimate_turn_cost(
    *,
    stt_audio_sec: float,
    tts_chars: int,
    tts_provider: str,
    tts_model: str = "",
    stt_provider: str = "sarvam",
    stt_model: str = "",
    llm_model: str | None = None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    cache_write_tokens: int,
    fx_rate_inr: float,
    input_audio_tokens: int = 0,
    output_audio_tokens: int = 0,
    cached_audio_tokens: int = 0,
    input_image_tokens: int = 0,
) -> dict[str, Any]:
    fx = float(fx_rate_inr or DEFAULT_FX_RATE_INR)
    stt = cost_stt_usd(
        audio_sec=stt_audio_sec,
        fx_rate_inr=fx,
        stt_provider=stt_provider,
        stt_model=stt_model,
    )
    tts = cost_tts_usd(
        chars=tts_chars,
        provider=tts_provider,
        model=tts_model,
        fx_rate_inr=fx,
    )
    llm = cost_llm_usd(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
        llm_model=llm_model,
        input_audio_tokens=input_audio_tokens,
        output_audio_tokens=output_audio_tokens,
        cached_audio_tokens=cached_audio_tokens,
        input_image_tokens=input_image_tokens,
    )
    total = stt + tts + llm["total_usd"]
    return {
        "stt_usd": stt,
        "tts_usd": tts,
        "llm_usd": llm["total_usd"],
        "llm": llm,
        "total_usd": total,
        "stt_inr": stt * fx,
        "tts_inr": tts * fx,
        "llm_inr": llm["total_usd"] * fx,
        "total_inr": total * fx,
        "cache_event": classify_cache_event(
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
        ),
        "fx_rate_inr": fx,
        "resolved_tts_provider": resolve_tts_provider(provider=tts_provider, model=tts_model),
        "resolved_stt_provider": resolve_stt_provider(provider=stt_provider, model=stt_model),
        "llm_model": llm_model or "gpt-realtime-2.1-mini",
    }
