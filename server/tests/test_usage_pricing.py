from server.services.usage_pricing import (
    build_pricing_metadata,
    classify_cache_event,
    cost_llm_usd,
    cost_stt_usd,
    cost_tts_usd,
    estimate_turn_cost,
    resolve_tts_provider,
    split_llm_tokens,
)

import pytest


def test_sarvam_stt_is_thirty_rupees_per_hour():
    fx = 95.64
    usd = cost_stt_usd(audio_sec=3600, fx_rate_inr=fx)
    assert abs(usd * fx - 30.0) < 1e-9


def test_cartesia_stt_ink_whisper_pro_plan():
    # Pro: $5 / 100K credits, 1 credit/sec → 3600 sec = $0.18/hr
    usd = cost_stt_usd(
        audio_sec=3600,
        fx_rate_inr=95.64,
        stt_provider="cartesia",
        stt_model="ink-whisper",
    )
    assert abs(usd - 0.18) < 1e-9


def test_sarvam_tts_three_rupees_per_1k_chars():
    fx = 95.64
    usd = cost_tts_usd(chars=1000, provider="sarvam", fx_rate_inr=fx)
    assert abs(usd * fx - 3.0) < 1e-9


def test_cartesia_tts_fifty_usd_per_million_chars():
    usd = cost_tts_usd(chars=1_000_000, provider="cartesia", model="sonic-3.5", fx_rate_inr=95.64)
    assert abs(usd - 50.0) < 1e-9


def test_sonic_model_on_sarvam_provider_uses_cartesia_tts_rate():
    assert resolve_tts_provider(provider="sarvam", model="sonic-3.5") == "cartesia"
    usd = cost_tts_usd(chars=1_000_000, provider="sarvam", model="sonic-3.5", fx_rate_inr=95.64)
    assert abs(usd - 50.0) < 1e-9


def test_cache_hit_uses_cached_rate_not_full_input():
    hit = cost_llm_usd(input_tokens=2000, output_tokens=40, cached_tokens=1800, cache_write_tokens=0)
    miss = cost_llm_usd(input_tokens=2000, output_tokens=40, cached_tokens=0, cache_write_tokens=0)
    assert hit["cached_usd"] > 0
    assert hit["total_usd"] < miss["total_usd"]
    assert classify_cache_event(input_tokens=2000, cached_tokens=1800, cache_write_tokens=0) == "cache_hit"


def test_gpt_55_costs_more_than_luna():
    luna = cost_llm_usd(input_tokens=2000, output_tokens=40, llm_model="gpt-5.6-luna")
    g55 = cost_llm_usd(input_tokens=2000, output_tokens=40, llm_model="gpt-5.5")
    assert g55["total_usd"] > luna["total_usd"]


def test_cache_write_not_double_counted_with_uncached(monkeypatch):
    # Test accounting independently of the current default model's price.
    monkeypatch.setattr("server.services.usage_pricing.openai_rates_for_model", lambda model: {
        "input": 0.20, "cached_input": 0.05, "cache_write": 0.25, "output": 1.0,
    })
    parts = split_llm_tokens(input_tokens=2000, cached_tokens=0, cache_write_tokens=1800)
    assert parts["written"] == 1800
    assert parts["uncached"] == 200
    write = cost_llm_usd(input_tokens=2000, output_tokens=0, cached_tokens=0, cache_write_tokens=1800)
    # 1800 * 0.25/M + 200 * 0.20/M
    assert abs(write["total_usd"] - (1800 * 0.25 + 200 * 0.20) / 1e6) < 1e-12
    assert classify_cache_event(input_tokens=2000, cached_tokens=0, cache_write_tokens=1800) == "cache_write"


def test_turn_cost_includes_inr_and_usd():
    row = estimate_turn_cost(
        stt_audio_sec=8,
        tts_chars=40,
        tts_provider="sarvam",
        tts_model="bulbul:v3",
        stt_provider="sarvam",
        stt_model="saaras:v3-realtime",
        llm_model="gpt-5.6-luna",
        input_tokens=1900,
        output_tokens=35,
        cached_tokens=1700,
        cache_write_tokens=0,
        fx_rate_inr=95.64,
    )
    assert row["total_usd"] > 0
    assert abs(row["total_inr"] - row["total_usd"] * 95.64) < 1e-9
    assert row["cache_event"] == "cache_hit"
    assert row["resolved_tts_provider"] == "sarvam"


def test_pricing_metadata_includes_audio_rates_for_all_realtime_models():
    meta = build_pricing_metadata(95.64)
    for slug in ("gpt-realtime-2.1-mini", "gpt-realtime-2.1", "gpt-realtime-2"):
        block = meta[f"openai:{slug}"]
        assert block["usd_audio_input_per_m"] > 0
        assert block["usd_audio_output_per_m"] > 0
    mini = estimate_turn_cost(
        stt_audio_sec=0,
        tts_chars=0,
        tts_provider="openai",
        llm_model="gpt-realtime-2.1-mini",
        input_tokens=600,
        output_tokens=1200,
        cached_tokens=0,
        cache_write_tokens=0,
        fx_rate_inr=95.64,
        input_audio_tokens=600,
        output_audio_tokens=1200,
    )
    assert mini["stt_usd"] == 0
    assert mini["tts_usd"] == 0
    assert mini["total_usd"] == pytest.approx(0.03, rel=1e-6)


def test_telnyx_per_minute_and_pricing_metadata():
    from server.services.usage_pricing import TELNYX_OUTBOUND_USD_PER_MIN, cost_telnyx_call_usd

    assert cost_telnyx_call_usd(duration_sec=0, direction="outbound") == 0
    assert cost_telnyx_call_usd(duration_sec=60, direction="outbound") == pytest.approx(
        TELNYX_OUTBOUND_USD_PER_MIN
    )
    inbound = cost_telnyx_call_usd(duration_sec=120, direction="inbound")
    outbound = cost_telnyx_call_usd(duration_sec=120, direction="outbound")
    assert inbound < outbound
    meta = build_pricing_metadata(95.64)
    assert meta["telnyx:outbound"]["usd_per_unit"] == TELNYX_OUTBOUND_USD_PER_MIN
