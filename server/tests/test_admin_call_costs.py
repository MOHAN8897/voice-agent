"""Admin call costing reads pinned snapshots and never invents missing prices."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from server.services.saas import composed_costing as costs
from server.services.saas.admin_call_costs import build_call_costs
from server.services.saas.cost_insights import build_insights


def _ready_supplier(stt=1.0, llm=2.0, tts=2.0):
    stages = {
        stage: {
            "status": "ready",
            "costInr": value,
            "costUsd": value / 100,
            "components": [{"rateId": f"{stage}-rate"}],
        }
        for stage, value in (("stt", stt), ("llm", llm), ("tts", tts))
    }
    return {
        "status": "ready",
        "missing": [],
        "totalInr": stt + llm + tts,
        "totalUsd": (stt + llm + tts) / 100,
        "stages": stages,
    }


def test_ready_call_uses_pinned_retail_and_actual_carrier_cost():
    meta = {
        "rate_snapshot": {"inrPaisePerMin": 500, "usdMicrosPerMin": 53191, "fxRateInr": 95},
        "provider_cost_result": _ready_supplier(),
        "carrier_billing": {"source": "vobiz_cdr", "amount": 1.5, "currency": "INR", "billable_seconds": 120},
        "usage": {},
    }
    result = build_call_costs(
        meta=meta,
        channel="pstn",
        tier="medium",
        duration_sec=120,
        applied_inr_paise=None,
        applied_usd_micros=None,
        current_rates={"fx_rate_inr": 100},
        tier_rate={"inrPaisePerMin": 900, "usdMicrosPerMin": 90000},
    )
    assert result["status"] == "ready"
    assert result["retail"]["source"] == "rate_snapshot"
    assert result["retail"]["totalBilledInr"] == pytest.approx(10.0)
    assert result["supplier"]["carrier"]["status"] == "actual"
    assert result["supplier"]["totalInr"] == pytest.approx(6.5)
    assert result["margin"]["inr"] == pytest.approx(3.5)
    assert result["margin"]["percent"] == pytest.approx(35.0)
    assert result["fxRateInr"] == pytest.approx(95.0)


def test_incomplete_pinned_rates_never_fall_back_to_current_defaults():
    rates = [rate for rate in costs.default_provider_rates() if rate["stage"] != "tts"]
    snapshot = costs.build_cost_snapshot(
        {"version": 1, "configured": True, "rates": rates},
        {
            "tier": "medium",
            "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
            "llm": {"provider": "sarvam", "model": "sarvam-105b-conversations"},
            "tts": {"provider": "sarvam", "model": "bulbul:v4-flash"},
        },
        fx_rate_inr=100,
        captured_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
    )
    meta = {
        "provider_cost_snapshot": snapshot,
        "provider_cost_result": _ready_supplier(),
        "stage_usage": {
            "stt": {"audio_seconds": 60},
            "llm": {"input_tokens": 1000, "output_tokens": 1000},
            "tts": {"input_characters": 500},
        },
        "usage": {"model_cost_usd": 9.99, "fx_rate_inr": 100},
    }
    result = build_call_costs(
        meta=meta,
        channel="pstn",
        tier="medium",
        duration_sec=60,
        applied_inr_paise=None,
        applied_usd_micros=None,
        current_rates={"fx_rate_inr": 100},
        tier_rate=None,
    )
    assert result["status"] == "incomplete"
    assert result["retail"]["source"] == "unavailable"
    assert result["retail"]["totalBilledInr"] is None
    assert result["supplier"]["totalInr"] is None
    assert "tts.characters_1000.rate" in result["missing"]
    assert "retail_rate" in result["missing"]
    assert result["margin"]["inr"] is None


def test_applied_rate_wins_and_zero_duration_bills_zero():
    meta = {"provider_cost_result": _ready_supplier(0, 0, 0), "usage": {}}
    result = build_call_costs(
        meta=meta,
        channel="browser",
        tier="medium",
        duration_sec=0,
        applied_inr_paise=900,
        applied_usd_micros=90000,
        current_rates={"fx_rate_inr": 100},
        tier_rate={"inrPaisePerMin": 500, "usdMicrosPerMin": 53191},
    )
    assert result["retail"]["source"] == "applied"
    assert result["retail"]["rateInrPerMin"] == pytest.approx(9.0)
    assert result["retail"]["totalBilledInr"] == 0.0
    assert result["supplier"]["carrier"]["status"] == "not_applicable"
    assert result["supplier"]["totalInr"] == 0.0
    assert result["margin"]["inr"] == 0.0
    assert result["margin"]["percent"] is None
    assert result["status"] == "ready"


def test_missing_carrier_cost_keeps_supplier_total_unknown():
    result = build_call_costs(
        meta={"provider_cost_result": _ready_supplier(), "usage": {}},
        channel="pstn",
        tier="medium",
        duration_sec=60,
        applied_inr_paise=500,
        applied_usd_micros=53191,
        current_rates={"fx_rate_inr": 100},
    )
    assert result["supplier"]["carrier"]["status"] == "unavailable"
    assert result["supplier"]["totalInr"] is None
    assert "carrier_cost" in result["missing"]
    assert result["margin"]["inr"] is None


def _insight_rows():
    now = datetime.now(timezone.utc)
    rows = [
        {
            "call_id": "priced",
            "tenant_id": "tenant-a",
            "channel": "pstn",
            "tier": "medium",
            "direction": "outbound",
            "duration_sec": 60,
            "session_id": "vobiz-session",
            "applied_rate_inr_paise_per_min": 500,
            "applied_rate_usd_micros_per_min": 53191,
            "applied_fx_rate_inr": 95,
        }
    ]
    metadata = {
        "priced": {
            "tenant_id": "tenant-a",
            "usage": {"cost_accounting_version": 2, "model_cost_usd": 0.01, "fx_rate_inr": 95, "llm_model": "gemini-3.8-live"},
            "carrier_billing": {"source": "vobiz_cdr", "amount": 1, "currency": "INR"},
        }
    }
    return rows, metadata, now


def test_cost_insights_margin_uses_each_call_applied_retail_rate():
    rows, metadata, now = _insight_rows()
    rates = {
        "version": 1,
        "fx_rate_inr": 95,
        "pstn_medium_rate_usd_micros_per_min": 53191,
        "pstn_medium_rate_inr_paise_per_min": 500,
    }
    result = build_insights(
        rows,
        rates,
        since=now - timedelta(days=1),
        now=now,
        ledger=SimpleNamespace(read_meta=lambda call_id: metadata[call_id]),
        overhead_rows=[],
    )
    pstn = next(channel for channel in result["channels"] if channel["channel"] == "pstn_medium")
    assert pstn["costInr"] == pytest.approx(1.95)
    assert pstn["retailInr"] == pytest.approx(5.0)
    assert pstn["marginInr"] == pytest.approx(3.05)
    assert pstn["marginPercent"] == pytest.approx(61.0)
    assert pstn["retailPricedCalls"] == 1
    assert pstn["retailCoveragePercent"] == 100.0
    assert pstn["currentPriceInrPerMin"] == pytest.approx(5.0)
    assert pstn["currentPriceUsdPerMin"] == pytest.approx(0.053191, abs=1e-6)


def test_cost_insights_reconstructs_composed_cost_from_pinned_snapshot():
    snapshot = costs.build_cost_snapshot(
        {"version": 3, "configured": True, "rates": costs.default_provider_rates()},
        {
            "tier": "medium",
            "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
            "llm": {"provider": "sarvam", "model": "sarvam-105b-conversations"},
            "tts": {"provider": "sarvam", "model": "bulbul:v4-flash"},
        },
        fx_rate_inr=100,
        captured_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
    )
    now = datetime.now(timezone.utc)
    rows = [{
        "call_id": "composed",
        "tenant_id": "tenant-a",
        "channel": "pstn",
        "tier": "medium",
        "direction": "outbound",
        "duration_sec": 60,
        "session_id": "vobiz-session",
        "applied_rate_inr_paise_per_min": 500,
        "applied_rate_usd_micros_per_min": 53191,
        "applied_fx_rate_inr": 100,
    }]
    metadata = {
        "composed": {
            "tenant_id": "tenant-a",
            "pipeline": "composed_voice",
            "provider_cost_snapshot": snapshot,
            "stage_usage": {
                "stt": {"audio_seconds": "60"},
                "llm": {"input_tokens": 1000000, "cached_tokens": 200000, "output_tokens": 1000000},
                "tts": {"input_characters": 1000},
            },
            # No stored usage totals: the pinned snapshot must still price the call.
            "usage": {"fx_rate_inr": 100},
            "carrier_billing": {"source": "vobiz_cdr", "amount": 10, "currency": "INR"},
        }
    }
    result = build_insights(
        rows,
        {"fx_rate_inr": 100},
        since=now - timedelta(days=1),
        now=now,
        ledger=SimpleNamespace(read_meta=lambda call_id: metadata[call_id]),
        overhead_rows=[],
    )
    pstn = next(channel for channel in result["channels"] if channel["channel"] == "pstn_medium")
    assert pstn["apiInr"] == pytest.approx(75.49)
    assert pstn["carrierInr"] == pytest.approx(10.0)
    assert pstn["costInr"] == pytest.approx(85.49)
    assert pstn["retailInr"] == pytest.approx(5.0)
    assert pstn["marginInr"] == pytest.approx(-80.49)


def test_cost_insights_includes_custom_composed_tiers():
    rows, metadata, now = _insight_rows()
    rows[0]["tier"] = "medium_copy_1"
    result = build_insights(
        rows,
        {"version": 1, "fx_rate_inr": 95, "pstn_rate_usd_micros_per_min": 150000, "pstn_rate_inr_paise_per_min": 1500},
        since=now - timedelta(days=1),
        now=now,
        ledger=SimpleNamespace(read_meta=lambda call_id: metadata[call_id]),
        overhead_rows=[],
        tier_records={"medium_copy_1": {"revision": 22, "profile": {"label": "Standard copy", "retailRateInr": 3.5}}},
    )
    custom = next(channel for channel in result["channels"] if channel["channel"] == "pstn_medium_copy_1")
    assert custom["label"] == "Standard copy"
    assert custom["currentPriceInrPerMin"] == pytest.approx(3.5)
    # The rate pinned to the call still wins over today's catalog price.
    assert custom["retailInr"] == pytest.approx(5.0)
    assert custom["marginInr"] == pytest.approx(3.05)


def test_cost_insights_has_no_invented_current_price_or_margin():
    rows, metadata, now = _insight_rows()
    result = build_insights(
        rows,
        {"fx_rate_inr": 95},
        since=now - timedelta(days=1),
        now=now,
        ledger=SimpleNamespace(read_meta=lambda call_id: metadata[call_id]),
        overhead_rows=[],
    )
    pstn = next(channel for channel in result["channels"] if channel["channel"] == "pstn_medium")
    # Applied retail exists on the call, so margin is still measured.
    assert pstn["retailInr"] == pytest.approx(5.0)
    assert pstn["currentPriceInrPerMin"] is None
    assert pstn["currentPriceUsdPerMin"] is None
