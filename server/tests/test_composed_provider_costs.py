"""Supplier cost units, immutable snapshots, admin boundary and Premium isolation."""
from __future__ import annotations

import copy
import time
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.services.saas import composed_costing as costs


def stack(tts_provider="sarvam", tts_model="bulbul:v3"):
    return {"tier": "low" if tts_provider == "sarvam" else "medium",
            "stt": {"provider": "sarvam", "model": "saaras:v3-realtime"},
            "llm": {"provider": "sarvam", "model": "sarvam-105b-conversations"},
            "tts": {"provider": tts_provider, "model": tts_model}}


def snapshot(*, at=None, provider="sarvam", model="bulbul:v3"):
    return costs.build_cost_snapshot(
        {"version": 3, "configured": True, "rates": costs.default_provider_rates()},
        stack(provider, model), fx_rate_inr="100",
        captured_at=at or datetime(2026, 10, 22, tzinfo=timezone.utc),
    )


def usage():
    return {"stt": {"audio_seconds": "60"},
            "llm": {"input_tokens": 1000000, "cached_tokens": 200000, "output_tokens": 1000000},
            "tts": {"input_characters": 1000}}


def test_published_defaults_are_exact_and_validate():
    rates = costs.default_provider_rates()
    assert costs.validate_provider_rates(rates) == rates
    assert all(isinstance(rate["price"], str) and rate["sourceUrl"].startswith("https://") for rate in rates)


def test_low_cost_uses_inr_audio_minutes_characters_and_split_cached_tokens():
    result = costs.price_composed_usage(snapshot(), usage())
    assert result["status"] == "ready"
    # STT 0.49; TTS3; LLM0.8M*15+0.2M*5+1M*60=73 INR.
    assert Decimal(result["totalInr"]) == Decimal("76.49")
    assert Decimal(result["totalUsd"]) == Decimal("0.7649")
    assert Decimal(result["stages"]["llm"]["costInr"]) == Decimal("73")


@pytest.mark.parametrize("at,expected_usd", [
    (datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc), "7.2349"),
    (datetime(2027, 1, 1, tzinfo=timezone.utc), "13.7349"),
])
def test_standard_prices_native_text_audio_tokens_and_scheduled_tariff_boundary(at, expected_usd):
    measured = usage()
    measured["tts"] = {"input_characters": 999999999, "native_usage": {"input_tokens": 1000000, "output_audio_tokens": 1000000}}
    result = costs.price_composed_usage(snapshot(at=at, provider="gemini", model="gemini-3.8-flash-lite-tts"), measured)
    assert result["status"] == "ready"
    assert Decimal(result["totalUsd"]) == Decimal(expected_usd)


def test_snapshot_rates_are_immutable_after_admin_edits():
    config = {"version": 7, "configured": True, "rates": costs.default_provider_rates()}
    pinned = costs.build_cost_snapshot(config, stack(), fx_rate_inr=100, captured_at=datetime(2026, 10, 22, tzinfo=timezone.utc))
    config["rates"][0]["price"] = "1000"
    assert pinned["rates"][0]["price"] == "0.49"
    assert pinned["version"] == 7


@pytest.mark.parametrize("mutate,missing", [
    (lambda data: data.pop("llm"), "llm.measured_usage"),
    (lambda data: data["stt"].update(audio_seconds=-1), "stt.measured_usage"),
    (lambda data: data["llm"].update(cached_tokens=1000001), "llm.measured_usage"),
    (lambda data: data["tts"].update(input_characters=float("nan")), "tts.measured_usage"),
])
def test_invalid_or_missing_measured_usage_is_unknown_not_zero(mutate, missing):
    measured = usage()
    mutate(measured)
    result = costs.price_composed_usage(snapshot(), measured)
    assert result["status"] == "incomplete"
    assert missing in result["missing"]
    assert result["totalUsd"] is None


def test_unknown_model_has_no_generic_fallback_and_missing_gemini_tokens_stay_unknown():
    unknown = costs.price_composed_usage(snapshot(provider="gemini", model="future-tts"), usage())
    assert unknown["status"] == "incomplete"
    no_native = costs.price_composed_usage(snapshot(provider="gemini", model="gemini-3.8-flash-lite-tts"), usage())
    assert "tts.measured_usage" in no_native["missing"]
    assert costs.price_composed_usage({"configured": False}, usage())["totalUsd"] is None


def test_prepared_greeting_and_generated_tts_are_counted_once():
    measured = usage()
    measured["tts"]["prewarm_input_characters"] = 1000
    low = costs.price_composed_usage(snapshot(), measured)
    assert low["stages"]["tts"]["costInr"] == "6"
    measured["tts"] = {"native_usage": {"input_tokens": 20, "output_audio_tokens": 50},
                       "prewarm_native_usage": {"input_tokens": 10, "output_audio_tokens": 25}}
    standard = costs.price_composed_usage(snapshot(provider="gemini", model="gemini-3.8-flash-lite-tts"), measured)
    assert Decimal(standard["stages"]["tts"]["costUsd"]) == Decimal("0.000465")


@pytest.mark.parametrize("field,value", [("price", -1), ("price", "NaN"), ("price", True),
                                         ("price", "0.0000000001"), ("currency", "EUR"),
                                         ("unit", "characters_1000"), ("model", "gemini-3.8-live"),
                                         ("sourceUrl", "https://secret:token@example.com")])
def test_tariff_input_rejects_negative_nonfinite_wrong_units_and_premium(field, value):
    rates = costs.default_provider_rates()
    rates[0][field] = value
    with pytest.raises(costs.ProviderCostError):
        costs.validate_provider_rates(rates)


def test_duplicate_id_overlapping_dates_and_secret_fields_are_rejected():
    rates = costs.default_provider_rates()
    duplicate = copy.deepcopy(rates[0])
    duplicate["id"] = "another-id"
    with pytest.raises(costs.ProviderCostError, match="overlap"):
        costs.validate_provider_rates(rates + [duplicate])
    with pytest.raises(costs.ProviderCostError, match="unique"):
        costs.validate_provider_rates(rates + [rates[0]])
    rates[0]["api_key"] = "synthetic"
    with pytest.raises(costs.ProviderCostError, match="schema"):
        costs.validate_provider_rates(rates)


class FakeDb:
    def __init__(self, previous):
        self.previous, self.rows, self.statements = previous, [], []
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def execute(self, statement):
        self.statements.append(str(statement))
        return SimpleNamespace(scalar_one_or_none=lambda: self.previous)

    def add(self, row):
        self.rows.append(row)


@pytest.mark.asyncio
async def test_save_locks_version_and_does_not_touch_retail_or_tier_rows(monkeypatch):
    db = FakeDb(SimpleNamespace(version=4))
    monkeypatch.setattr(costs, "get_session_factory", lambda: lambda: db)
    loader = AsyncMock(return_value={"version": 5})
    monkeypatch.setattr(costs, "load_provider_costs", loader)
    saved = await costs.save_provider_costs(expected_version=4, rates=costs.default_provider_rates(), actor="synthetic-admin", reason="Verified official supplier tariffs")
    assert saved == {"version": 5}
    assert "pg_advisory_xact_lock" in db.statements[0]
    assert "FOR UPDATE" in db.statements[1]
    assert len(db.rows) == 1 and db.rows[0].resource_type == costs.RESOURCE_TYPE
    assert db.rows[0].version == 5
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_admin_save_is_rejected_without_commit(monkeypatch):
    db = FakeDb(SimpleNamespace(version=5))
    monkeypatch.setattr(costs, "get_session_factory", lambda: lambda: db)
    with pytest.raises(costs.ProviderCostError) as failure:
        await costs.save_provider_costs(expected_version=4, rates=costs.default_provider_rates(), actor="synthetic", reason="Verified source tariffs")
    assert failure.value.status_code == 409
    assert not db.rows
    db.commit.assert_not_awaited()


def test_provider_cost_routes_enforce_platform_billing_permission(monkeypatch):
    from server.auth.dependencies import require_dev_session
    from server.auth.rbac import ROLE_CUSTOMER_VIEWER, ROLE_PLATFORM_ADMIN
    from server.auth.session import SessionData
    from server.routes.dev_admin import router

    app = FastAPI()
    app.include_router(router)
    current = SessionData(kind="dev", subject="synthetic", tenant_id="tenant", role=ROLE_CUSTOMER_VIEWER, issued_at=int(time.time()))
    app.dependency_overrides[require_dev_session] = lambda: current
    monkeypatch.setattr(costs, "load_provider_costs", AsyncMock(return_value={"version": 0, "configured": False}))
    monkeypatch.setattr(costs, "save_provider_costs", AsyncMock(side_effect=costs.ProviderCostError("version_conflict", "Reload supplier tariffs", 409)))
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/dev/admin/billing/provider-costs").status_code == 403
        assert client.put("/api/dev/admin/billing/provider-costs", json={"expectedVersion": 0, "reason": "Synthetic reason", "rates": costs.default_provider_rates()}).status_code == 403
        current = SessionData(kind="dev", subject="synthetic-admin", tenant_id="tenant", role=ROLE_PLATFORM_ADMIN, issued_at=int(time.time()))
        assert client.get("/api/dev/admin/billing/provider-costs").json() == {"version": 0, "configured": False}
        response = client.put("/api/dev/admin/billing/provider-costs", json={"expectedVersion": 0, "reason": "Synthetic reason", "rates": costs.default_provider_rates()})
        assert response.status_code == 409
        assert response.json()["detail"]["error"]["code"] == "version_conflict"


def test_ledger_composed_override_missing_data_and_premium_unchanged(monkeypatch, tmp_path):
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.services.saas.cost_insights import model_cost

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    for call_id, pipeline, stage_data in (("low", "composed_voice", usage()), ("missing", "composed_voice", {}), ("premium", "realtime_voice", usage())):
        call_ledger.meta_path(call_id).parent.mkdir(parents=True, exist_ok=True)
        call_ledger.write_meta(call_id, {"pipeline": pipeline, "channel": "browser", "provider_cost_snapshot": snapshot(), "stage_usage": stage_data,
                                       "usage": {"llm_model": "gemini-3.8-live" if call_id == "premium" else "sarvam-105b-conversations", "model_cost_usd": 999, "fx_rate_inr": 100}})
        call_ledger.stamp_ended_usage(call_id, reason="user_stop", duration_sec=60)
    low = call_ledger.read_meta("low")["usage"]
    assert low["model_cost_usd"] == pytest.approx(0.7649)
    assert low["cost_accounting_version"] == 3
    assert model_cost(low) == (Decimal("0.7649"), "measured_stages")
    missing = call_ledger.read_meta("missing")["usage"]
    assert missing["cost_usd"] is None and missing["model_cost_usd"] is None
    assert model_cost(missing)[0] is None
    premium = call_ledger.read_meta("premium")["usage"]
    assert premium["model_cost_usd"] == 999
    assert "supplier_cost_status" not in premium
    assert "provider_cost_snapshot" not in call_ledger.review_fields("low")
    get_settings.cache_clear()


def test_measured_usage_helper_accumulates_and_preserves_premium(monkeypatch):
    from server.call.call_ledger import call_ledger

    meta = {"pipeline": "composed_voice"}
    monkeypatch.setattr(call_ledger, "read_meta", lambda _: copy.deepcopy(meta))
    monkeypatch.setattr(call_ledger, "write_meta", lambda _, value: meta.update(copy.deepcopy(value)))
    costs.record_composed_stage_usage("synthetic", "llm", {"input_tokens": 10, "output_tokens": 4})
    costs.record_composed_stage_usage("synthetic", "llm", {"input_tokens": 7, "output_tokens": 2})
    costs.record_composed_stage_usage("synthetic", "stt", {"audio_seconds": 3.5}, accumulate=False)
    assert meta["stage_usage"]["llm"] == {"input_tokens": 17, "output_tokens": 6}
    assert meta["stage_usage"]["stt"] == {"audio_seconds": 3.5}
    meta["pipeline"] = "realtime_voice"
    before = copy.deepcopy(meta)
    costs.record_composed_stage_usage("synthetic", "llm", {"input_tokens": 100})
    assert meta == before
