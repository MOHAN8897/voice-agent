"""Admin call costing reads pinned snapshots and never invents missing prices."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from server.services.saas import composed_costing as costs
from server.services.saas.admin_call_costs import build_call_costs
from server.services.saas.cost_insights import build_insights
from server.services.saas.hosting_costs import hosting_assumptions, price_call_hosting

# Default Railway estimate per call-minute, by hand: 0.1 vCPU * $0.000463
# + 0.1 GB * $0.000231 + 2.4 MB / 1024 * $0.05 per GB egress.
SERVER_USD_PER_MIN = 0.1 * 0.000463 + 0.1 * 0.000231 + 2.4 / 1024 * 0.05


def _server_inr(seconds, fx, places=4):
    # Per-call admin rows round like other INR lines; insights keep full precision.
    value = SERVER_USD_PER_MIN * seconds / 60 * fx
    return round(value, places) if places is not None else value


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
    server_inr = _server_inr(120, 95)
    assert result["supplier"]["server"]["costInr"] == pytest.approx(server_inr)
    assert result["supplier"]["totalInr"] == pytest.approx(6.5 + server_inr)
    assert result["margin"]["inr"] == pytest.approx(round(3.5 - server_inr, 2))
    assert result["margin"]["percent"] == pytest.approx((3.5 - server_inr) * 10, abs=0.05)
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
    assert result["supplier"]["server"]["costInr"] == 0.0
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
    server_inr = _server_inr(60, 95, places=None)
    assert pstn["serverInr"] == pytest.approx(server_inr)
    assert pstn["serverPerMinInr"] == pytest.approx(server_inr)
    assert pstn["costInr"] == pytest.approx(1.95 + server_inr)
    assert pstn["retailInr"] == pytest.approx(5.0)
    assert pstn["marginInr"] == pytest.approx(3.05 - server_inr)
    assert pstn["marginPercent"] == pytest.approx(round((3.05 - server_inr) * 20, 1))
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
    server_inr = _server_inr(60, 100, places=None)
    assert pstn["costInr"] == pytest.approx(85.49 + server_inr)
    assert pstn["retailInr"] == pytest.approx(5.0)
    assert pstn["marginInr"] == pytest.approx(-80.49 - server_inr)


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
    assert custom["marginInr"] == pytest.approx(3.05 - _server_inr(60, 95, places=None))


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


def test_server_cost_prices_railway_usage_per_call_minute():
    result = price_call_hosting(180, fx=100, assumptions=hosting_assumptions())
    assert result["status"] == "estimate"
    assert result["label"] == "Server (Railway, estimated)"
    assert result["perMinuteUsd"] == pytest.approx(SERVER_USD_PER_MIN)
    assert result["costUsd"] == pytest.approx(round(SERVER_USD_PER_MIN * 3, 6))
    assert result["costInr"] == pytest.approx(round(SERVER_USD_PER_MIN * 3 * 100, 4))
    parts = result["components"]
    assert parts["cpuUsd"] == pytest.approx(0.1 * 0.000463 * 3, abs=1e-6)
    assert parts["memoryUsd"] == pytest.approx(0.1 * 0.000231 * 3, abs=1e-6)
    assert parts["egressUsd"] == pytest.approx(2.4 / 1024 * 0.05 * 3, abs=1e-6)


def test_server_cost_assumptions_cite_railway_and_accept_overrides(monkeypatch):
    defaults = hosting_assumptions()
    assert defaults["sourceUrl"] == "https://railway.com/pricing"
    assert defaults["checkedOn"] == "2026-11-02"
    assert defaults["overridden"] == []

    monkeypatch.setenv("RAILWAY_VCPU_PER_CALL", "0.25")
    monkeypatch.setenv("RAILWAY_EGRESS_MB_PER_CALL_MINUTE", "not-a-number")
    tuned = hosting_assumptions({"memoryGbPerCall": "0.5"})
    assert tuned["vcpuPerCall"] == "0.25"
    assert tuned["memoryGbPerCall"] == "0.5"
    # An unusable override keeps the default instead of zeroing the cost.
    assert tuned["egressMbPerCallMinute"] == "2.4"
    assert sorted(tuned["overridden"]) == ["memoryGbPerCall", "vcpuPerCall"]
    expected = 0.25 * 0.000463 + 0.5 * 0.000231 + 2.4 / 1024 * 0.05
    assert price_call_hosting(60, fx=None, assumptions=tuned)["perMinuteUsd"] == pytest.approx(expected)


def test_server_cost_without_fx_leaves_inr_supplier_total_unknown():
    result = build_call_costs(
        meta={"provider_cost_result": _ready_supplier(), "usage": {}},
        channel="browser",
        tier="medium",
        duration_sec=60,
        applied_inr_paise=500,
        applied_usd_micros=53191,
        current_rates={},
    )
    server = result["supplier"]["server"]
    assert server["costUsd"] == pytest.approx(round(SERVER_USD_PER_MIN, 6))
    assert server["costInr"] is None
    assert "server_cost" in result["missing"]
    assert result["supplier"]["totalInr"] is None
    assert result["supplier"]["totalUsd"] == pytest.approx(0.05 + round(SERVER_USD_PER_MIN, 6))
