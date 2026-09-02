"""
Official provider rates for Test Studio cost estimates.

Sources (verified 2026-09-02):
  Sarvam  — https://www.sarvam.ai/api-pricing
            STT realtime/streaming/batch ₹30/hour of audio (diarization ₹45/hour)
            TTS bulbul realtime/streaming ₹3.00 per 1,000 characters
  OpenAI  — https://developers.openai.com/api/docs/models/gpt-5.6-luna
            gpt-5.6-luna short context: $0.20/M uncached input, $0.02/M cached input,
            cache writes 1.25× input = $0.25/M, output $1.20/M
  Cartesia — https://docs.cartesia.ai/pricing
            Sonic TTS ~1 credit/character; Pro plan effective ~$50 / 1M characters
"""
from __future__ import annotations

from typing import Any, Literal

PRICING_UPDATED_AT = "2026-09-02"

SARVAM_STT_INR_PER_HOUR = 30.0
SARVAM_STT_DIARIZATION_INR_PER_HOUR = 45.0
SARVAM_TTS_INR_PER_1K_CHARS = 3.0

OPENAI_LUNA_USD_PER_M = {
    "input": 0.20,
    "cached_input": 0.02,
    "cache_write": 0.25,
    "output": 1.20,
}

CARTESIA_TTS_USD_PER_M_CHARS = 50.0

CacheEvent = Literal["cache_hit", "cache_write", "partial_hit", "cache_miss"]


def build_pricing_metadata(fx_rate_inr: float) -> dict[str, Any]:
    fx = float(fx_rate_inr) or 95.64
    stt_usd_per_hour = SARVAM_STT_INR_PER_HOUR / fx
    tts_usd_per_1k = SARVAM_TTS_INR_PER_1K_CHARS / fx
    return {
        "updated_at": PRICING_UPDATED_AT,
        "fx_rate_inr": fx,
        "sources": {
            "sarvam": "https://www.sarvam.ai/api-pricing",
            "openai": "https://developers.openai.com/api/docs/models/gpt-5.6-luna",
            "cartesia": "https://docs.cartesia.ai/pricing",
        },
        "notes": {
            "stt": "Sarvam bills audio duration (₹30/hour). Telugu character count is not billed for STT.",
            "tts": "Sarvam bills Unicode characters including Telugu code points (₹3 / 1k chars).",
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
        "openai:gpt-5.6-luna": {
            "unit": "1m_tokens",
            "usd_per_unit": OPENAI_LUNA_USD_PER_M["input"] / 1000.0,
            "usd_input_per_m": OPENAI_LUNA_USD_PER_M["input"],
            "usd_cached_input_per_m": OPENAI_LUNA_USD_PER_M["cached_input"],
            "usd_cache_write_per_m": OPENAI_LUNA_USD_PER_M["cache_write"],
            "usd_output_per_m": OPENAI_LUNA_USD_PER_M["output"],
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


def cost_stt_usd(*, audio_sec: float, fx_rate_inr: float) -> float:
    hours = max(0.0, float(audio_sec or 0)) / 3600.0
    return (hours * SARVAM_STT_INR_PER_HOUR) / float(fx_rate_inr or 95.64)


def cost_tts_usd(*, chars: int, provider: str, fx_rate_inr: float) -> float:
    n = max(0, int(chars or 0))
    if str(provider or "").startswith("cartesia") or str(provider or "").startswith("sonic"):
        return n * CARTESIA_TTS_USD_PER_M_CHARS / 1_000_000.0
    return (n / 1000.0 * SARVAM_TTS_INR_PER_1K_CHARS) / float(fx_rate_inr or 95.64)


def cost_llm_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> dict[str, float]:
    parts = split_llm_tokens(
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
    )
    rates = OPENAI_LUNA_USD_PER_M
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
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    cache_write_tokens: int,
    fx_rate_inr: float,
) -> dict[str, Any]:
    fx = float(fx_rate_inr or 95.64)
    stt = cost_stt_usd(audio_sec=stt_audio_sec, fx_rate_inr=fx)
    tts = cost_tts_usd(chars=tts_chars, provider=tts_provider, fx_rate_inr=fx)
    llm = cost_llm_usd(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
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
    }
