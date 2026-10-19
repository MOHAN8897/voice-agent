"""Customer charges use the channel selling rate independently of supplier spend."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
import uuid
import pytest

from server.services.saas.billing_wallet_service import _resolve_call_wallet_debit


def test_wallet_debit_uses_selling_rate_even_when_supplier_cost_is_present():
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

    assert mode == "catalog_prorated"
    assert cents == 25  # 124 seconds at 12 cents/minute, rounded at the wallet boundary.
    assert paise == int(round(cents * settings.fx_rate_inr))


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


def test_wallet_debit_browser_call_uses_web_rate_not_pstn():
    """Browser test calls must use web_agent_rate and ignore telephony carrier ledger stamps."""
    settings = SimpleNamespace(
        pstn_rate_usd_cents_per_min=15,
        web_agent_rate_usd_cents_per_min=7,
        fx_rate_inr=95.64,
    )
    fx = settings.fx_rate_inr

    class _Ledger:
        @staticmethod
        def read_meta(call_id: str):
            return {
                "usage": {
                    "cost_inr": 0.50,
                    "cost_usd": 0.005,
                    "fx_rate_inr": 95.64,
                }
            }

    with patch("server.call.call_ledger.call_ledger", _Ledger()):
        cents, paise, mode = _resolve_call_wallet_debit(
            call_id="c_web_1",
            channel="browser",
            duration_sec=30,  # 0.5 min * 7 cents = 3.5 cents -> 4 cents
            settings=settings,
        )

    assert mode == "catalog_prorated"
    assert cents == int(round(0.5 * 7))  # 4 cents
    assert paise == int(round(cents * fx))


@pytest.mark.asyncio
async def test_bill_call_usage_skips_zero_duration():
    """Zero second calls must never debit wallet credits (every penny counts)."""
    from server.services.saas.billing_wallet_service import bill_call_usage_if_applicable

    called = False

    class _FakeStore:
        @staticmethod
        async def get(call_id: str):
            return {
                "channel": "browser",
                "tenant_id": str(uuid.uuid4()),
                "billed_user_id": str(uuid.uuid4()),
                "duration_sec": 0,
                "is_test": True,
            }

    async def _fail_debit(*_a, **_kw):
        nonlocal called
        called = True

    with patch("server.call.call_store.call_store", _FakeStore()), \
         patch("server.services.saas.billing_wallet_service.debit_wallet", _fail_debit), \
         patch("server.services.saas.billing_wallet_service.get_settings") as gs:
        gs.return_value = SimpleNamespace(saas_auth_enabled=True)
        await bill_call_usage_if_applicable("zero_dur_call")

    assert called is False, "debit_wallet should not be called for duration_sec <= 0"


@pytest.mark.asyncio
async def test_bill_call_usage_browser_session_bills_tenant_even_without_billed_user():
    """Browser test calls must debit tenant wallet even when billed_user is missing from Call model."""
    from server.services.saas.billing_wallet_service import bill_call_usage_if_applicable

    called_kw = {}

    class _FakeStore:
        @staticmethod
        async def get(call_id: str):
            return {
                "channel": "browser",
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "session_id": "web-agent-11111111-1111-1111-1111-111111111111-agent1-abc",
                "duration_sec": 45,
                "is_test": True,
            }

    async def _mock_debit(tenant_id, **kw):
        called_kw.update(kw)
        called_kw["tenant_id"] = tenant_id
        return {"ok": True, "amountCents": kw.get("amount_cents", 0), "amountInrPaise": kw.get("amount_inr_paise", 0)}

    class _EmptyLedger:
        @staticmethod
        def review_fields(call_id: str):
            return {}

        @staticmethod
        def read_meta(call_id: str):
            return {}

    with patch("server.call.call_store.call_store", _FakeStore()), \
         patch("server.call.call_ledger.call_ledger", _EmptyLedger()), \
         patch("server.services.saas.billing_wallet_service.debit_wallet", _mock_debit), \
         patch("server.services.saas.billing_wallet_service.get_settings") as gs:
        gs.return_value = SimpleNamespace(
            saas_auth_enabled=True,
            pstn_rate_usd_cents_per_min=9,
            web_agent_rate_usd_cents_per_min=7,
            fx_rate_inr=95.64,
        )
        await bill_call_usage_if_applicable("web_test_call_id")

    assert called_kw.get("tenant_id") == uuid.UUID("00000000-0000-0000-0000-000000000001")
    assert called_kw.get("kind") == "usage_web_test"
    assert called_kw.get("amount_cents") == 5  # 45/60 * 7 = 5.25 -> 5
    assert called_kw.get("user_id") == uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.asyncio
async def test_debit_wallet_usd_tenant_deducts_cents_and_preserves_currency(monkeypatch):
    """USD-funded wallet must debit amount_cents, leave paise intact, and keep currency='usd'."""
    from server.services.saas.billing_wallet_service import debit_wallet
    from server.db.models.saas_models import BillingWallet

    tenant_id = uuid.uuid4()
    wallet = BillingWallet(
        tenant_id=tenant_id,
        currency="usd",
        balance_cents=1000,
        balance_inr_paise=0,
    )

    added = []

    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, _model, _pk, **_kw):
            return wallet

        async def execute(self, _stmt):
            return _Result()

        def add(self, obj):
            added.append(obj)

        async def commit(self):
            pass

    monkeypatch.setattr(
        "server.services.saas.billing_wallet_service.get_session_factory",
        lambda: lambda: _Session(),
    )

    res = await debit_wallet(
        tenant_id=tenant_id,
        kind="usage_web_test",
        reference_id="call:usd_web_test_1",
        amount_cents=5,
        amount_inr_paise=478,
        allow_partial=True,
    )

    assert res["amountCents"] == 5
    assert res["amountInrPaise"] == 0
    assert wallet.balance_cents == 995
    assert wallet.balance_inr_paise == 0
    assert wallet.currency == "usd", "Wallet currency must not be overwritten to inr!"
    tx = added[0]
    assert tx.amount_cents == -5
    assert tx.amount_inr_paise == 0


@pytest.mark.asyncio
async def test_debit_wallet_inr_tenant_deducts_paise(monkeypatch):
    """INR-funded wallet must debit amount_inr_paise, leave cents intact, and keep currency='inr'."""
    from server.services.saas.billing_wallet_service import debit_wallet
    from server.db.models.saas_models import BillingWallet

    tenant_id = uuid.uuid4()
    wallet = BillingWallet(
        tenant_id=tenant_id,
        currency="inr",
        balance_cents=0,
        balance_inr_paise=50000,
    )

    added = []

    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, _model, _pk, **_kw):
            return wallet

        async def execute(self, _stmt):
            return _Result()

        def add(self, obj):
            added.append(obj)

        async def commit(self):
            pass

    monkeypatch.setattr(
        "server.services.saas.billing_wallet_service.get_session_factory",
        lambda: lambda: _Session(),
    )

    res = await debit_wallet(
        tenant_id=tenant_id,
        kind="usage_web_test",
        reference_id="call:inr_web_test_1",
        amount_cents=5,
        amount_inr_paise=478,
        allow_partial=True,
    )

    assert res["amountCents"] == 0
    assert res["amountInrPaise"] == 478
    assert wallet.balance_cents == 0
    assert wallet.balance_inr_paise == 49522
    assert wallet.currency == "inr"
    tx = added[0]
    assert tx.amount_cents == 0
    assert tx.amount_inr_paise == -478


@pytest.mark.asyncio
async def test_list_wallet_transactions_enriches_duration_from_call_ledger(monkeypatch):
    """Transaction rows without SQL Call row must fallback to call_ledger for duration and agent name."""
    from server.services.saas.billing_wallet_service import list_wallet_transactions
    from server.db.models.saas_models import BillingWalletTransaction

    tenant_id = uuid.uuid4()
    call_id = uuid.uuid4()
    tx = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=None,
        amount_cents=-5,
        amount_inr_paise=0,
        kind="usage_web_test",
        reference_id=f"call:{call_id}",
        created_at=None,
    )

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return iter(self._rows)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, stmt):
            entity = stmt.column_descriptions[0]["entity"]
            if entity == BillingWalletTransaction:
                return _Rows([tx])
            return _Rows([])

    monkeypatch.setattr(
        "server.services.saas.billing_wallet_service.get_session_factory",
        lambda: lambda: _Session(),
    )

    class _Ledger:
        @staticmethod
        def read_meta(cid: str):
            if cid == str(call_id):
                return {
                    "duration_sec": 52,
                    "channel": "browser",
                    "usage": {"duration_sec": 52},
                }
            return {}

    monkeypatch.setattr("server.call.call_ledger.call_ledger", _Ledger())

    rows = await list_wallet_transactions(tenant_id)
    assert len(rows) == 1
    assert rows[0]["durationSec"] == 52
    assert "52s" in rows[0]["description"]
    assert "Browser Voice Test" in rows[0]["description"]


@pytest.mark.asyncio
async def test_wallet_summary_unifies_dual_currency(monkeypatch):
    """wallet_summary must unify both USD cents and INR paise into net balance and remainingMinutes."""
    from server.services.saas.billing_wallet_service import wallet_summary
    from server.db.models.saas_models import BillingWallet

    tenant_id = uuid.uuid4()
    wallet = BillingWallet(
        tenant_id=tenant_id,
        currency="usd",
        balance_cents=1000,       # $10.00
        balance_inr_paise=95640,  # ₹956.40 (worth $10.00 at fx=95.64)
    )

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, _model, _pk):
            return wallet

    monkeypatch.setattr(
        "server.services.saas.billing_wallet_service.get_session_factory",
        lambda: lambda: _Session(),
    )
    monkeypatch.setattr(
        "server.services.saas.billing_rates.rates_with_derived_inr",
        lambda: {
            "version": 1,
            "pstn_rate_usd_cents_per_min": 10,
                "pstn_rate_usd_micros_per_min": 100_000,
            "pstn_rate_inr_paise_per_min": 956,
            "web_agent_rate_usd_cents_per_min": 10,
                "web_agent_rate_usd_micros_per_min": 100_000,
            "web_agent_rate_inr_paise_per_min": 956,
            "did_monthly_usd_cents": 400,
                "did_monthly_usd_micros": 4_000_000,
            "did_monthly_inr_paise": 38256,
            "fx_rate_inr": 95.64,
        },
    )
    monkeypatch.setattr(
        "server.services.saas.billing_wallet_service.get_settings",
        lambda: SimpleNamespace(
            fx_rate_inr=95.64,
            pstn_rate_usd_cents_per_min=10,  # 10 cents/min
            web_agent_rate_usd_cents_per_min=10,
            pstn_min_balance_usd_cents=100,
            pstn_min_balance_inr_paise=5000,
        ),
    )

    summary = await wallet_summary(tenant_id)
    # Total effective USD = $10.00 + ($956.40 / 95.64) = $20.00
    assert summary["balance_usd"] == 20.0
    assert summary["balanceUsd"] == 20.0
    # Total effective INR = 956.40 + (10.00 * 95.64) = 1912.80
    assert summary["balance_inr"] == 1912.80
    assert summary["balanceInr"] == 1912.80
    # Remaining minutes at 10 cents/min = 1000//10 + 95640//956 = 100 + 100 = 200 minutes
    assert summary["remainingMinutes"] == 200


