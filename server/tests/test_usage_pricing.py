from server.services.usage_pricing import (
    classify_cache_event,
    cost_llm_usd,
    cost_stt_usd,
    cost_tts_usd,
    estimate_turn_cost,
    split_llm_tokens,
)


def test_sarvam_stt_is_thirty_rupees_per_hour():
    fx = 95.64
    usd = cost_stt_usd(audio_sec=3600, fx_rate_inr=fx)
    assert abs(usd * fx - 30.0) < 1e-9


def test_sarvam_tts_three_rupees_per_1k_chars():
    fx = 95.64
    usd = cost_tts_usd(chars=1000, provider="sarvam", fx_rate_inr=fx)
    assert abs(usd * fx - 3.0) < 1e-9


def test_cache_hit_uses_cached_rate_not_full_input():
    hit = cost_llm_usd(input_tokens=2000, output_tokens=40, cached_tokens=1800, cache_write_tokens=0)
    miss = cost_llm_usd(input_tokens=2000, output_tokens=40, cached_tokens=0, cache_write_tokens=0)
    assert hit["cached_usd"] > 0
    assert hit["total_usd"] < miss["total_usd"]
    assert classify_cache_event(input_tokens=2000, cached_tokens=1800, cache_write_tokens=0) == "cache_hit"


def test_cache_write_not_double_counted_with_uncached():
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
        input_tokens=1900,
        output_tokens=35,
        cached_tokens=1700,
        cache_write_tokens=0,
        fx_rate_inr=95.64,
    )
    assert row["total_usd"] > 0
    assert abs(row["total_inr"] - row["total_usd"] * 95.64) < 1e-9
    assert row["cache_event"] == "cache_hit"
