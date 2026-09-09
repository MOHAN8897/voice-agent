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
"""
from __future__ import annotations

from typing import Any, Literal

PRICING_UPDATED_AT = "2026-09-03"

SARVAM_STT_INR_PER_HOUR = 30.0
SARVAM_STT_DIARIZATION_INR_PER_HOUR = 45.0
SARVAM_TTS_INR_PER_1K_CHARS = 3.0

# Cartesia Pro plan default (conservative estimate tier for dev console)
CARTESIA_PRO_USD_PER_CREDIT = 5.0 / 100_000.0
CARTESIA_TTS_USD_PER_M_CHARS = CARTESIA_PRO_USD_PER_CREDIT * 1_000_000.0  # $50/M

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


def cartesia_stt_credits_per_sec(*, model: str = "", realtime: bool = True) -> float:
    """Cartesia STT credit burn rate (Pro-plan credits, not Sarvam)."""
    m = (model or "ink-whisper").lower()
    if "ink-2" in m:
        return 3.0 if realtime else 1.5
    return 1.0 if realtime else 0.5


def build_pricing_metadata(fx_rate_inr: float) -> dict[str, Any]:
    fx = float(fx_rate_inr) or 95.64
    stt_usd_per_hour = SARVAM_STT_INR_PER_HOUR / fx
    tts_usd_per_1k = SARVAM_TTS_INR_PER_1K_CHARS / fx
    cartesia_stt_usd_per_hour_whisper = cartesia_stt_credits_per_sec(model="ink-whisper") * 3600 * CARTESIA_PRO_USD_PER_CREDIT
    cartesia_stt_usd_per_hour_ink2 = cartesia_stt_credits_per_sec(model="ink-2") * 3600 * CARTESIA_PRO_USD_PER_CREDIT
    return {
        "updated_at": PRICING_UPDATED_AT,
        "fx_rate_inr": fx,
        "sources": {
            "sarvam": "https://www.sarvam.ai/api-pricing",
            "openai": "https://developers.openai.com/api/docs/pricing",
            "cartesia": "https://docs.cartesia.ai/pricing",
        },
        "notes": {
            "stt": "Sarvam bills audio duration (₹30/hour). Cartesia STT bills credits/sec (Pro plan default).",
            "tts": "Sarvam bills Unicode characters (₹3 / 1k). Cartesia ~1 credit/char (Pro ≈ $50 / 1M chars).",
            "llm": "OpenAI bills tokenizer tokens. Cache reads are 10% of input; writes are 1.25× input.",
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
            "billing": "tokens_with_cache",
            "updated_at": PRICING_UPDATED_AT,
        },
        "openai:gpt-realtime-2.1": {
            "unit": "1m_tokens",
            "usd_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1"]["input"],
            "usd_cached_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1"]["cached_input"],
            "usd_cache_write_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1"]["cache_write"],
            "usd_output_per_m": OPENAI_USD_PER_M["gpt-realtime-2.1"]["output"],
            "billing": "tokens_with_cache",
            "updated_at": PRICING_UPDATED_AT,
        },
        "openai:gpt-realtime-2": {
            "unit": "1m_tokens",
            "usd_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2"]["input"],
            "usd_cached_input_per_m": OPENAI_USD_PER_M["gpt-realtime-2"]["cached_input"],
            "usd_cache_write_per_m": OPENAI_USD_PER_M["gpt-realtime-2"]["cache_write"],
            "usd_output_per_m": OPENAI_USD_PER_M["gpt-realtime-2"]["output"],
            "billing": "tokens_with_cache",
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
) -> dict[str, float]:
    parts = split_llm_tokens(
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
    )
    rates = openai_rates_for_model(llm_model)
    uncached = parts["uncached"] * rates["input"] / 1_000_000.0
    cached = parts["cached"] * rates["cached_input"] / 1_000_000.0
    written = parts["written"] * rates["cache_write"] / 1_000_000.0
    output = max(0, int(output_tokens or 0)) * rates["output"] / 1_000_000.0
    return {
        "uncached_usd": uncached,
        "cached_usd": cached,
        "cache_write_usd": written,
        "output_usd": output,
        "total_usd": uncached + cached + written + output,
    }


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
) -> dict[str, Any]:
    fx = float(fx_rate_inr or 95.64)
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
