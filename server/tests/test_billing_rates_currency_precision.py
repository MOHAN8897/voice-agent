from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_inr_rate_save_preserves_entered_paise(monkeypatch):
    from server.services.saas import billing_rates

    current = {
        "version": 1,
        "pstn_rate_usd_cents_per_min": 9,
        "pstn_rate_usd_micros_per_min": 90_000,
        "pstn_rate_inr_paise_per_min": 860,
        "web_agent_rate_usd_cents_per_min": 7,
        "web_agent_rate_usd_micros_per_min": 70_000,
        "web_agent_rate_inr_paise_per_min": 669,
        "did_monthly_usd_cents": 400,
        "did_monthly_usd_micros": 4_000_000,
        "did_monthly_inr_paise": 38_256,
        "fx_rate_inr": 95.64,
    }
    monkeypatch.setattr(billing_rates, "load_current_rates", AsyncMock(return_value=current))
    monkeypatch.setattr(billing_rates, "_save_disk_backup", lambda _data: None)

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class Session:
        def __init__(self):
            self.query_count = 0
            self.inserted = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _statement):
            self.query_count += 1
            return Result(1)

        def add(self, row):
            self.inserted = row

        async def commit(self):
            return None

    session = Session()
    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: lambda: session)

    await billing_rates.update_rates_versioned(
        actor="admin",
        reason="Fix native INR pricing precision",
        rate_currency="INR",
        pstn_inr_per_min=Decimal("5.00"),
    )

    assert session.inserted is not None
    assert session.inserted.pstn_rate_inr_paise_per_min == 500
    assert session.inserted.pstn_rate_usd_micros_per_min == 52_279
    assert session.inserted.pstn_rate_usd_cents_per_min == 5
    assert session.inserted.web_agent_rate_inr_paise_per_min == 669


@pytest.mark.asyncio
async def test_current_rate_read_prefers_database_over_stale_process_cache(monkeypatch):
    from server.services.saas import billing_rates

    row = SimpleNamespace(
        version=6,
        pstn_rate_usd_cents_per_min=5,
        web_agent_rate_usd_cents_per_min=7,
        did_monthly_usd_cents=400,
        pstn_rate_usd_micros_per_min=52_279,
        web_agent_rate_usd_micros_per_min=None,
        did_monthly_usd_micros=None,
        pstn_rate_inr_paise_per_min=500,
        web_agent_rate_inr_paise_per_min=None,
        did_monthly_inr_paise=None,
        fx_rate_inr=95.64,
        effective_from=None,
        created_by="admin",
        reason="Native INR rate",
    )

    class Result:
        def scalar_one_or_none(self):
            return row

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _statement):
            return Result()

    session = Session()
    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(billing_rates, "_cache", None)
    billing_rates.set_cached_rates(
        {
            "version": 5,
            "pstn_rate_usd_cents_per_min": 5,
            "pstn_rate_usd_micros_per_min": 52_279,
            "pstn_rate_inr_paise_per_min": 470,
            "web_agent_rate_usd_cents_per_min": 7,
            "did_monthly_usd_cents": 400,
            "fx_rate_inr": 95.64,
        }
    )

    current = await billing_rates.load_current_rates()

    assert current["version"] == 6
    assert current["pstn_rate_inr_paise_per_min"] == 500
    # Legacy NULL columns derive deterministically from the stored USD cents.
    assert current["web_agent_rate_inr_paise_per_min"] == 669
    assert billing_rates.effective_rates()["pstn_rate_inr_paise_per_min"] == 500


@pytest.mark.asyncio
async def test_database_rate_read_does_not_fall_back_to_stale_disk_copy(monkeypatch):
    from server.services.saas import billing_rates

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _statement):
            raise RuntimeError("schema unavailable")

    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: lambda: Session())
    monkeypatch.setattr(
        billing_rates,
        "_load_disk_fallback",
        lambda: {"pstn_rate_usd_cents_per_min": 5, "pstn_rate_inr_paise_per_min": 470},
    )

    with pytest.raises(billing_rates.BillingConfigurationError, match="cannot be resolved"):
        await billing_rates.load_current_rates()


def test_short_call_debit_uses_native_inr_rate_without_fx_round_trip():
    from server.services.saas.billing_wallet_service import _resolve_call_wallet_debit

    class Ledger:
        @staticmethod
        def read_meta(_call_id):
            return {}

    with patch("server.call.call_ledger.call_ledger", Ledger()):
        cents, paise, mode = _resolve_call_wallet_debit(
            call_id="browser-22s",
            channel="browser",
            duration_sec=22,
            settings=SimpleNamespace(),
            stored_rate_cents=5,
            stored_rate_micros=52_279,
            stored_rate_inr_paise=500,
            stored_fx=95.64,
        )

    assert mode == "catalog_prorated"
    assert paise == 183  # ₹5.00/min * 22s, rounded once to the paise.
    assert cents == 2
