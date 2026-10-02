"""Wallet debit aligns with stamped call ledger usage when available."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from server.services.saas.billing_wallet_service import _resolve_call_wallet_debit


def test_wallet_debit_uses_stamped_ledger_cost():
    settings = SimpleNamespace(
        pstn_rate_usd_cents_per_min=12,
        pstn_rate_inr_paise_per_min=900,
        web_agent_rate_usd_cents_per_min=10,
        web_agent_rate_inr_paise_per_min=700,
        fx_rate_inr=95.64,
    )

    class _Ledger:
        @staticmethod
        def read_meta(call_id: str):
            return {
                "usage": {
                    "cost_inr": 3.48,
                    "cost_usd": 0.0364,
                    "fx_rate_inr": 95.64,
                }
            }

    with patch("server.call.call_ledger.call_ledger", _Ledger()):
        cents, paise, mode = _resolve_call_wallet_debit(
            call_id="c1",
            channel="pstn",
            duration_sec=124,
            settings=settings,
        )

    assert mode == "ledger_usage"
    assert paise == 348
    assert cents == 4


def test_wallet_debit_prorates_catalog_when_no_ledger():
    """INR is the mirror of the USD price at the chargeable FX, not its own rate.

    Prices are authored in dollars now, so an independently stored rupee rate
    could disagree with the dollar price it mirrors and quietly overcharge.
    """
    settings = SimpleNamespace(
        pstn_rate_usd_cents_per_min=12,
        web_agent_rate_usd_cents_per_min=10,
        did_monthly_usd_cents=400,
        fx_rate_inr=95.64,
    )
    fx = settings.fx_rate_inr

    class _Ledger:
        @staticmethod
        def read_meta(call_id: str):
            return {}

    with patch("server.call.call_ledger.call_ledger", _Ledger()):
        cents, paise, mode = _resolve_call_wallet_debit(
            call_id="c2",
            channel="pstn",
            duration_sec=90,
            settings=settings,
        )

    assert mode == "catalog_prorated"
    assert cents == int(round(1.5 * 12))
    assert paise == int(round(cents * fx))
