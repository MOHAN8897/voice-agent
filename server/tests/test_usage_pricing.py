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


def test_gemini_live_audio_minute_matches_published_token_rates():
    # Docs: 25 audio tokens/sec → 1500 tokens/min. $3/M in ≈ $0.0045 (published $0.005).
    # $12/M out → $0.018/min.
    one_min_in = cost_llm_usd(
        input_tokens=1500,
        output_tokens=0,
        llm_model="gemini-3.8-live",
        input_audio_tokens=1500,
        output_audio_tokens=0,
    )
    one_min_out = cost_llm_usd(
        input_tokens=0,
        output_tokens=1500,
        llm_model="gemini-3.8-live",
        input_audio_tokens=0,
        output_audio_tokens=1500,
    )
    assert one_min_in["audio_input_usd"] == pytest.approx(0.0045, rel=1e-9)
    assert one_min_out["audio_output_usd"] == pytest.approx(0.018, rel=1e-9)


def test_gemini_image_tokens_use_published_one_dollar_per_million():
    billed = cost_llm_usd(
        input_tokens=1_000_000,
        output_tokens=0,
        llm_model="gemini-3.8-live",
        input_image_tokens=1_000_000,
    )
    assert billed["image_input_usd"] == pytest.approx(1.0, rel=1e-9)
    assert billed["uncached_usd"] == pytest.approx(0.0, rel=1e-9)


def test_gemini_live_text_prompt_is_not_billed_as_audio():
    overcharged = cost_llm_usd(
        input_tokens=5904,
        output_tokens=0,
        llm_model="gemini-3.8-live",
        input_audio_tokens=5904,
        output_audio_tokens=0,
    )
    split = cost_llm_usd(
        input_tokens=5904,
        output_tokens=180,
        llm_model="gemini-3.8-live",
        input_audio_tokens=404,
        output_audio_tokens=180,
    )
    assert split["total_usd"] < overcharged["total_usd"]
    assert split["uncached_usd"] > 0
    assert split["audio_output_usd"] > 0


def test_gemini_live_audio_e2e_cost_uses_gemini_rates():
    gemini = cost_llm_usd(
        input_tokens=5000,
        output_tokens=800,
        llm_model="gemini-3.8-live",
        input_audio_tokens=5000,
        output_audio_tokens=800,
    )
    openai = cost_llm_usd(
        input_tokens=5000,
        output_tokens=800,
        llm_model="gpt-realtime-2.1-mini",
        input_audio_tokens=5000,
        output_audio_tokens=800,
    )
    assert gemini["audio_input_usd"] > 0
    assert gemini["total_usd"] != openai["total_usd"]


def test_pricing_metadata_includes_gemini_live():
    meta = build_pricing_metadata(95.64)
    assert "gemini:gemini-3.8-live" in meta
    assert meta["gemini:gemini-3.8-live"]["usd_audio_output_per_m"] > 0
    assert meta["gemini:gemini-3.8-live"]["usd_image_input_per_m"] == 1.0
    assert meta["gemini:gemini-3.8-live"]["usd_audio_input_per_min_list"] == 0.005
    assert meta["notes"]["inr"]


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
    from server.services.usage_pricing import (
        TELNYX_MEDIA_STREAM_USD_PER_MIN,
        TELNYX_OUTBOUND_USD_PER_MIN,
        TELNYX_VOICE_API_USD_PER_MIN,
        cost_telnyx_call_breakdown,
        cost_telnyx_call_usd,
        telnyx_estimate_call_recording,
    )

    assert cost_telnyx_call_usd(duration_sec=0, direction="outbound") == 0
    pstn = cost_telnyx_call_usd(
        duration_sec=60,
        direction="outbound",
        media_streaming=True,
        call_recording=telnyx_estimate_call_recording(),
    )
    assert pstn > TELNYX_OUTBOUND_USD_PER_MIN
    assert cost_telnyx_call_usd(
        duration_sec=60,
        direction="outbound",
        media_streaming=True,
        call_recording=False,
    ) == pytest.approx(TELNYX_OUTBOUND_USD_PER_MIN)
    inbound = cost_telnyx_call_usd(duration_sec=120, direction="inbound", media_streaming=True)
    outbound = cost_telnyx_call_usd(duration_sec=120, direction="outbound", media_streaming=True)
    assert inbound < outbound
    india = cost_telnyx_call_breakdown(
        duration_sec=60,
        direction="outbound",
        media_streaming=True,
        call_recording=False,
        destination_country="IN",
    )
    us = cost_telnyx_call_breakdown(
        duration_sec=60,
        direction="outbound",
        media_streaming=True,
        call_recording=False,
        destination_country="US",
    )
    assert india["sip_usd"] > us["sip_usd"]
    assert india["media_stream_usd"] == pytest.approx(TELNYX_MEDIA_STREAM_USD_PER_MIN)
    assert india["voice_api_usd"] == pytest.approx(TELNYX_VOICE_API_USD_PER_MIN)
    meta = build_pricing_metadata(95.64)
    assert meta["telnyx:outbound"]["usd_per_unit"] == TELNYX_OUTBOUND_USD_PER_MIN
    assert meta["telnyx:media_stream"]["usd_per_unit"] == TELNYX_MEDIA_STREAM_USD_PER_MIN


def test_fx_live_uses_fetched_rate(monkeypatch):
    from server.config.env import get_settings
    from server.services.usage_pricing import clear_fx_live_cache, resolve_fx_rate_inr

    clear_fx_live_cache()
    monkeypatch.setenv("FX_RATE_LIVE", "true")
    monkeypatch.setenv("FX_RATE_INR", "95.64")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "server.services.usage_pricing._fetch_usd_inr",
        lambda: (88.0, "2026-09-23"),
    )
    info = resolve_fx_rate_inr()
    assert info["rate"] == 88.0
    assert info["source"] == "live"
    cached = resolve_fx_rate_inr()
    assert cached["source"] == "live_cache"
    get_settings.cache_clear()
    clear_fx_live_cache()


def test_fx_env_skips_live_fetch(monkeypatch):
    from server.config.env import get_settings
    from server.services.usage_pricing import clear_fx_live_cache, resolve_fx_rate_inr

    clear_fx_live_cache()
    monkeypatch.setenv("FX_RATE_LIVE", "false")
    monkeypatch.setenv("FX_RATE_INR", "95.64")
    get_settings.cache_clear()
    info = resolve_fx_rate_inr()
    assert info["rate"] == pytest.approx(95.64)
    assert info["source"] == "env"
    get_settings.cache_clear()
