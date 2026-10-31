"""Razorpay wallet payment hardening: reconciliation, refunds, disputes, capture.

Everything runs against SQLite and a fake Razorpay client. No network, no keys.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from server.db.models.entities import Base
from server.db.models.saas_models import (
    BillingInvoice,
    BillingWallet,
    BillingWalletTransaction,
    CreditNote,
    InvoiceSequence,
    RazorpayOrder,
    RazorpayRefund,
    RazorpayWebhookEvent,
)
from server.services.saas import razorpay_service as rzp
from server.services.saas import tax_service
from server.tests.test_billing_gst_invoices import _buyer, _config

TID = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000001")


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type, _compiler, **_kw):
    return "JSON"


class FakeRazorpay:
    """Synchronous stand-in for `razorpay.Client` (the SDK is called in a thread)."""

    def __init__(self):
        self.order_payments: dict[str, list[dict]] = {}
        self.payments: dict[str, dict] = {}
        self.refunds: dict[str, list[dict]] = {}
        self.payment_queries: list[str] = []
        self.capture_calls: list[tuple] = []
        self.refund_calls: list[tuple] = []
        self.refund_status = "processed"
        self.order = SimpleNamespace(payments=self._order_payments)
        self.payment = SimpleNamespace(
            fetch=self._fetch,
            capture=self._capture,
            refund=self._refund,
            fetch_multiple_refund=self._list_refunds,
        )
        self.refund = SimpleNamespace(fetch=lambda refund_id: {"id": refund_id, "status": "pending"})

    def _order_payments(self, order_id):
        self.payment_queries.append(order_id)
        return {"items": [dict(p) for p in self.order_payments.get(order_id, [])]}

    def _fetch(self, payment_id):
        return dict(self.payments[payment_id])

    def _capture(self, payment_id, amount, data=None):
        self.capture_calls.append((payment_id, amount, dict(data or {})))
        self.payments[payment_id]["status"] = "captured"
        return dict(self.payments[payment_id])

    def _refund(self, payment_id, data=None):
        data = dict(data or {})
        self.refund_calls.append((payment_id, data))
        entity = {
            "id": f"rfnd_{len(self.refund_calls)}",
            "payment_id": payment_id,
            "amount": data["amount"],
            "currency": "INR",
            "status": self.refund_status,
        }
        self.refunds.setdefault(payment_id, []).append(entity)
        return dict(entity)

    def _list_refunds(self, payment_id, data=None):
        return {"items": [dict(r) for r in self.refunds.get(payment_id, [])]}


@pytest.fixture
async def store(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'payments.db'}")
    models = [
        BillingWallet,
        BillingWalletTransaction,
        RazorpayOrder,
        InvoiceSequence,
        BillingInvoice,
        RazorpayRefund,
        CreditNote,
        RazorpayWebhookEvent,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in models])
        )
        # Migration 048: read and written through Core, not the ORM model.
        await connection.execute(
            text("ALTER TABLE razorpay_orders ADD COLUMN last_reconciled_at DATETIME")
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(BillingWallet(tenant_id=TID, balance_cents=0, balance_inr_paise=0))
        await session.commit()

    fake = FakeRazorpay()
    events = AsyncMock()
    monkeypatch.setattr(rzp, "get_session_factory", lambda: factory)
    monkeypatch.setattr(rzp, "_client", lambda: fake)
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=_config()))
    monkeypatch.setattr("server.services.saas.activity_log.record_event", events)
    yield SimpleNamespace(factory=factory, fake=fake, events=events)
    await engine.dispose()


def _ago(**delta) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**delta)


async def _order(store, order_id: str, *, created_at: datetime, status: str = "created", gross: int = 118000):
    async with store.factory() as session:
        session.add(
            RazorpayOrder(
                order_id=order_id,
                tenant_id=TID,
                currency="INR",
                status=status,
                amount_minor=gross,
                gross_minor=gross,
                taxable_minor=100000,
                tax_minor=18000,
                tax_rate_bps=1800,
                tax_kind="cgst_sgst",
                amount_inr_paise=100000,
                created_at=created_at,
                expires_at=created_at + rzp.ORDER_EXPIRY,
            )
        )
        await session.commit()


def _captured(payment_id: str, order_id: str, amount: int = 118000) -> dict:
    return {
        "id": payment_id,
        "order_id": order_id,
        "status": "captured",
        "currency": "INR",
        "amount": amount,
        "method": "upi",
    }


async def _paid_order(store, order_id="order_paid", payment_id="pay_paid"):
    await _order(store, order_id, created_at=_ago(hours=1))
    await rzp._credit_order_payment(order_id, payment_id, _captured(payment_id, order_id), source="webhook")
    return order_id, payment_id


async def _balance(store) -> int:
    async with store.factory() as session:
        return int((await session.get(BillingWallet, TID, populate_existing=True)).balance_inr_paise)


async def _status(store, order_id) -> str:
    async with store.factory() as session:
        return (await session.get(RazorpayOrder, order_id, populate_existing=True)).status


def _actions(store) -> list[str]:
    return [call.kwargs.get("action") for call in store.events.await_args_list]


# ---------------------------------------------------------------------------
# Finding 1: reconciliation round robin, expiry and late captures
# ---------------------------------------------------------------------------


async def test_fast_lane_is_round_robin_so_abandoned_orders_do_not_starve_new_ones(store):
    await _order(store, "order_old", created_at=_ago(hours=3))
    await _order(store, "order_mid", created_at=_ago(hours=2))
    await _order(store, "order_new", created_at=_ago(hours=1))

    first = await rzp.reconcile_pending_orders(limit=2, include_slow_lane=False)
    assert first["checked"] == 2
    assert store.fake.payment_queries == ["order_old", "order_mid"]

    store.fake.payment_queries.clear()
    await rzp.reconcile_pending_orders(limit=2, include_slow_lane=False)
    # The never-checked order goes first; the oldest-checked fills the batch.
    assert store.fake.payment_queries == ["order_new", "order_old"]


async def test_too_young_orders_are_not_polled(store):
    await _order(store, "order_inflight", created_at=_ago(minutes=2))
    result = await rzp.reconcile_pending_orders(limit=10)
    assert result["checked"] == 0 and store.fake.payment_queries == []


async def test_expiry_pass_fires_and_slow_lane_credits_a_late_capture_once(store):
    await _order(store, "order_late", created_at=_ago(hours=30))
    await _order(store, "order_ancient", created_at=_ago(days=8))
    store.fake.order_payments["order_late"] = [_captured("pay_late", "order_late")]

    result = await rzp.reconcile_pending_orders(limit=10)

    assert result["expired"] == 2
    assert result["lateChecked"] == 1
    assert result["credited"] == 1
    assert store.fake.payment_queries == ["order_late"]  # 8 days old is past the window
    assert await _status(store, "order_late") == "paid"
    assert await _status(store, "order_ancient") == "expired"
    assert await _balance(store) == 100000
    assert "wallet.topup.late_capture" in _actions(store)
    late = next(c for c in store.events.await_args_list if c.kwargs["action"] == "wallet.topup.late_capture")
    assert late.kwargs["severity"] == "error"


async def test_slow_lane_checks_an_expired_order_at_most_once_per_interval(store):
    await _order(store, "order_quiet", created_at=_ago(hours=30))
    await rzp.reconcile_pending_orders(limit=10)
    await rzp.reconcile_pending_orders(limit=10)
    assert store.fake.payment_queries == ["order_quiet"]
    assert await _status(store, "order_quiet") == "expired"


async def test_failed_attempt_never_moves_an_expired_order_out_of_the_slow_lane(store):
    await _order(store, "order_x", created_at=_ago(hours=30), status="expired")
    await rzp.mark_order_failed({"id": "pay_x", "order_id": "order_x", "status": "failed"})
    assert await _status(store, "order_x") == "expired"


# ---------------------------------------------------------------------------
# Finding 9: admin/loop reconcile only fails on a real failure
# ---------------------------------------------------------------------------


async def test_reconcile_does_not_fail_an_order_whose_latest_payment_is_still_created(store):
    await _order(store, "order_wait", created_at=_ago(hours=1))
    store.fake.order_payments["order_wait"] = [
        {"id": "pay_new", "order_id": "order_wait", "status": "created"},
        {"id": "pay_old", "order_id": "order_wait", "status": "failed"},
    ]
    outcome = await rzp.reconcile_order("order_wait", source="admin")
    assert outcome["outcome"] == "pending"
    assert await _status(store, "order_wait") == "created"

    store.fake.order_payments["order_wait"][0]["status"] = "failed"
    outcome = await rzp.reconcile_order("order_wait", source="admin")
    assert outcome["outcome"] == "failed"
    assert await _status(store, "order_wait") == "failed"


# ---------------------------------------------------------------------------
# Finding 8: authorized-but-not-captured payments are captured, then credited
# ---------------------------------------------------------------------------


async def test_authorized_payment_is_captured_for_the_stored_amount_then_credited(store):
    await _order(store, "order_auth", created_at=_ago(hours=1))
    authorized = {**_captured("pay_auth", "order_auth"), "status": "authorized"}
    store.fake.payments["pay_auth"] = dict(authorized)
    store.fake.order_payments["order_auth"] = [authorized]

    outcome = await rzp.reconcile_order("order_auth", source="reconciliation")

    assert store.fake.capture_calls == [("pay_auth", 118000, {"currency": "INR"})]
    assert outcome["outcome"] == "credited"
    assert await _status(store, "order_auth") == "paid"
    assert await _balance(store) == 100000

    # Redelivery (e.g. payment.authorized webhook retried) never captures again.
    again = await rzp.capture_authorized_payment(authorized, source="webhook")
    assert again["duplicate"] is True
    assert len(store.fake.capture_calls) == 1
    assert await _balance(store) == 100000


async def test_authorization_on_an_already_paid_order_is_not_captured(store):
    await _paid_order(store, "order_dup", "pay_first")
    second = {**_captured("pay_second", "order_dup"), "status": "authorized"}
    store.fake.payments["pay_second"] = dict(second)

    result = await rzp.capture_authorized_payment(second, source="webhook")

    assert result == {"ok": True, "captured": False, "skipped": "order_already_settled"}
    assert store.fake.capture_calls == []
    assert await _balance(store) == 100000


async def test_authorized_amount_mismatch_is_never_captured(store):
    await _order(store, "order_bad", created_at=_ago(hours=1))
    store.fake.payments["pay_bad"] = {**_captured("pay_bad", "order_bad", amount=100), "status": "authorized"}
    with pytest.raises(ValueError, match="payment_amount_mismatch"):
        await rzp.capture_authorized_payment(store.fake.payments["pay_bad"], source="webhook")
    assert store.fake.capture_calls == []


# ---------------------------------------------------------------------------
# Finding 10: a second capture on a refunded order is not credited
# ---------------------------------------------------------------------------


async def test_second_capture_on_refunded_order_is_flagged_not_credited(store):
    order_id, _ = await _paid_order(store)
    async with store.factory() as session:
        (await session.get(RazorpayOrder, order_id)).status = "refunded"
        await session.commit()
    before = await _balance(store)
    result = await rzp.credit_provider_payment(_captured("pay_extra", order_id), source="webhook")
    assert result["requiresRefund"] is True
    assert await _balance(store) == before


# ---------------------------------------------------------------------------
# Finding 14: invoice CGST/SGST split uses the shared helper
# ---------------------------------------------------------------------------


async def test_invoice_cgst_sgst_split_matches_the_quote_helper(store):
    await _order(store, "order_odd", created_at=_ago(hours=1), gross=118001)
    async with store.factory() as session:
        row = await session.get(RazorpayOrder, "order_odd")
        row.tax_minor = 18001
        await session.commit()
    await rzp._credit_order_payment("order_odd", "pay_odd", _captured("pay_odd", "order_odd", 118001), source="webhook")
    async with store.factory() as session:
        invoice = await session.scalar(select(BillingInvoice))
    assert (invoice.cgst_inr_paise, invoice.sgst_inr_paise) == tax_service._split_cgst_sgst(18001, 1800)


# ---------------------------------------------------------------------------
# Finding 2: refund idempotency and remaining amount
# ---------------------------------------------------------------------------


async def test_full_refund_after_partial_refunds_only_the_remainder(store):
    order_id, payment_id = await _paid_order(store)

    partial = await rzp.refund_order(order_id, amount_minor=29500, reason="Partial goodwill", actor="ops")
    assert partial["duplicate"] is False
    full = await rzp.refund_order(order_id, amount_minor=None, reason="Close the account", actor="ops")

    assert [call[1]["amount"] for call in store.fake.refund_calls] == [29500, 88500]
    assert full["invoiceStatus"] == "refunded"
    assert await _status(store, order_id) == "refunded"
    assert await _balance(store) == 0
    with pytest.raises(ValueError, match="order_not_refundable"):
        await rzp.refund_order(order_id, amount_minor=None, reason="Again by mistake", actor="ops")
    assert len(store.fake.refund_calls) == 2


async def test_refund_amount_is_capped_at_what_is_left(store):
    order_id, _ = await _paid_order(store)
    await rzp.refund_order(order_id, amount_minor=100000, reason="Partial goodwill", actor="ops")
    with pytest.raises(ValueError, match="invalid_refund_amount"):
        await rzp.refund_order(order_id, amount_minor=20000, reason="Too much now", actor="ops")
    assert len(store.fake.refund_calls) == 1


async def test_pending_refund_blocks_a_second_refund(store):
    order_id, _ = await _paid_order(store)
    store.fake.refund_status = "pending"
    first = await rzp.refund_order(order_id, amount_minor=None, reason="Customer asked", actor="ops")
    assert first["pending"] is True
    assert await _balance(store) == 100000  # pending moves no money

    with pytest.raises(ValueError, match="refund_in_progress"):
        await rzp.refund_order(order_id, amount_minor=None, reason="Double click", actor="ops")
    assert len(store.fake.refund_calls) == 1


async def test_refund_unknown_locally_but_present_at_razorpay_is_recorded_not_repeated(store):
    order_id, payment_id = await _paid_order(store)
    # An earlier refund call timed out after Razorpay accepted it.
    store.fake.refunds[payment_id] = [
        {"id": "rfnd_lost", "payment_id": payment_id, "amount": 118000, "currency": "INR", "status": "processed"}
    ]

    with pytest.raises(ValueError, match="refund_already_exists"):
        await rzp.refund_order(order_id, amount_minor=None, reason="Retry after timeout", actor="ops")

    assert store.fake.refund_calls == []
    assert await _balance(store) == 0  # reversed exactly once, for the real refund
    async with store.factory() as session:
        assert (await session.get(RazorpayRefund, "rfnd_lost")).status == "processed"


# ---------------------------------------------------------------------------
# Findings 3 and 13: processed is terminal; missing wallet is created
# ---------------------------------------------------------------------------


async def test_processed_refund_is_never_downgraded_or_reapplied(store):
    _, payment_id = await _paid_order(store)
    kwargs = dict(refund_id="rfnd_1", payment_id=payment_id, amount_minor=118000, currency="INR",
                  reason="Refund", created_by=None)

    await rzp.apply_refund(**kwargs, status="processed")
    late_failed = await rzp.apply_refund(**kwargs, status="failed")
    late_pending = await rzp.apply_refund(**kwargs, status="pending")
    replay = await rzp.apply_refund(**kwargs, status="processed")

    assert late_failed["duplicate"] and late_pending["duplicate"] and replay["duplicate"]
    async with store.factory() as session:
        assert (await session.get(RazorpayRefund, "rfnd_1")).status == "processed"
        assert await session.scalar(select(func.count()).select_from(CreditNote)) == 1
    assert await _balance(store) == 0


async def test_refund_creates_the_wallet_row_when_missing(store):
    _, payment_id = await _paid_order(store)
    async with store.factory() as session:
        await session.delete(await session.get(BillingWallet, TID))
        await session.commit()
    await rzp.apply_refund(refund_id="rfnd_w", payment_id=payment_id, amount_minor=118000,
                           currency="INR", reason="Refund", created_by=None)
    assert await _balance(store) == -100000


# ---------------------------------------------------------------------------
# Finding 4: disputes are recorded; a lost one reverses the credit once
# ---------------------------------------------------------------------------


async def test_dispute_created_is_alerted_without_moving_money(store):
    _, payment_id = await _paid_order(store)
    status = await rzp.handle_dispute_event(
        "payment.dispute.created",
        {"id": "disp_1", "payment_id": payment_id, "amount": 118000, "currency": "INR", "reason_code": "fraud"},
        {"id": payment_id},
    )
    assert status == "handled"
    call = next(c for c in store.events.await_args_list if c.kwargs["action"] == "payment.dispute.created")
    assert call.kwargs["severity"] == "error" and call.kwargs["resource_id"] == "disp_1"
    assert call.kwargs["tenant_id"] == TID
    assert await _balance(store) == 100000


async def test_lost_dispute_reverses_the_wallet_once_with_a_credit_note(store):
    _, payment_id = await _paid_order(store)
    dispute = {"id": "disp_2", "payment_id": payment_id, "amount": 118000, "currency": "INR", "reason_code": "fraud"}

    first = await rzp.handle_dispute_event("payment.dispute.lost", dispute, {"id": payment_id})
    second = await rzp.handle_dispute_event("payment.dispute.lost", dispute, {"id": payment_id})

    assert first == second == "handled"
    assert await _balance(store) == 0
    async with store.factory() as session:
        ledger = list((await session.execute(
            select(BillingWalletTransaction).where(BillingWalletTransaction.kind == "razorpay_chargeback")
        )).scalars())
        assert len(ledger) == 1 and ledger[0].amount_inr_paise == -100000
        assert await session.scalar(select(func.count()).select_from(CreditNote)) == 1


async def test_lost_dispute_after_partial_refund_reverses_only_the_rest(store):
    order_id, payment_id = await _paid_order(store)
    await rzp.refund_order(order_id, amount_minor=59000, reason="Half refunded", actor="ops")
    await rzp.handle_dispute_event(
        "payment.dispute.lost",
        {"id": "disp_3", "payment_id": payment_id, "amount": 118000, "currency": "INR"},
        {"id": payment_id},
    )
    assert await _balance(store) == 0
    assert await _status(store, order_id) == "refunded"


# ---------------------------------------------------------------------------
# Finding 6: permanent webhook errors are acknowledged; transient ones retried
# ---------------------------------------------------------------------------

SECRET = "whsec_unit_only"


class _Request:
    def __init__(self, raw: bytes, headers: dict[str, str]):
        self._raw = raw
        self.headers = headers

    async def body(self):
        return self._raw


def _signed(payload: dict, event_id: str):
    raw = json.dumps(payload).encode()
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": event_id}


@pytest.fixture
def webhook(store, monkeypatch):
    from server.routes import razorpay_webhook

    settings = SimpleNamespace(
        razorpay_webhook_secret=SECRET, razorpay_api_secret="api_secret_unit", razorpay_api_key="rzp_test_unit",
        app_environment="development",
    )
    monkeypatch.setattr(razorpay_webhook, "get_settings", lambda: settings)
    monkeypatch.setattr(rzp, "get_settings", lambda: settings)
    monkeypatch.setattr(razorpay_webhook, "get_session_factory", lambda: store.factory)
    return razorpay_webhook


async def _event_status(store, event_id):
    async with store.factory() as session:
        return (await session.get(RazorpayWebhookEvent, event_id, populate_existing=True)).status


async def test_amount_mismatch_webhook_is_acknowledged_as_rejected_and_alerted(store, webhook):
    await _order(store, "order_mm", created_at=_ago(hours=1))
    payload = {"event": "payment.captured", "payload": {"payment": {"entity": _captured("pay_mm", "order_mm", amount=1)}}}
    raw, headers = _signed(payload, "evt_mm")

    result = await webhook.razorpay_webhook(_Request(raw, headers))
    replay = await webhook.razorpay_webhook(_Request(raw, headers))

    assert result == {"ok": True, "status": "rejected", "error": "payment_amount_mismatch"}
    assert replay == {"ok": True, "duplicate": True, "status": "rejected"}
    assert await _event_status(store, "evt_mm") == "rejected"
    assert "wallet.webhook.rejected" in _actions(store)
    assert await _balance(store) == 0


async def test_transient_webhook_failure_still_asks_razorpay_to_retry(store, webhook, monkeypatch):
    async def unavailable(*_args, **_kwargs):
        raise ValueError("payment_verification_unavailable")

    monkeypatch.setattr(webhook, "capture_authorized_payment", unavailable)
    payload = {"event": "payment.authorized", "payload": {"payment": {"entity": {"id": "pay_t", "order_id": "o"}}}}
    raw, headers = _signed(payload, "evt_t")
    with pytest.raises(HTTPException) as caught:
        await webhook.razorpay_webhook(_Request(raw, headers))
    assert caught.value.status_code == 503
    assert await _event_status(store, "evt_t") == "failed"


async def test_payment_authorized_webhook_captures_and_credits(store, webhook):
    await _order(store, "order_wh", created_at=_ago(minutes=1))
    authorized = {**_captured("pay_wh", "order_wh"), "status": "authorized"}
    store.fake.payments["pay_wh"] = dict(authorized)
    raw, headers = _signed({"event": "payment.authorized", "payload": {"payment": {"entity": authorized}}}, "evt_wh")

    result = await webhook.razorpay_webhook(_Request(raw, headers))

    assert result == {"ok": True, "status": "handled"}
    assert store.fake.capture_calls == [("pay_wh", 118000, {"currency": "INR"})]
    assert await _balance(store) == 100000


async def test_dispute_lost_webhook_reverses_once_across_redeliveries(store, webhook):
    _, payment_id = await _paid_order(store)
    dispute = {"id": "disp_wh", "payment_id": payment_id, "amount": 118000, "currency": "INR"}
    payload = {"event": "payment.dispute.lost",
               "payload": {"payment": {"entity": {"id": payment_id}}, "dispute": {"entity": dispute}}}
    raw_a, headers_a = _signed(payload, "evt_d1")
    raw_b, headers_b = _signed(payload, "evt_d2")  # a distinct delivery of the same dispute

    assert (await webhook.razorpay_webhook(_Request(raw_a, headers_a)))["status"] == "handled"
    assert (await webhook.razorpay_webhook(_Request(raw_b, headers_b)))["status"] == "handled"
    assert await _balance(store) == 0


# ---------------------------------------------------------------------------
# Finding 5: the per-IP limiter does not apply to provider webhooks
# ---------------------------------------------------------------------------


def test_rate_limit_middleware_exempts_webhooks(monkeypatch):
    import server.app as app_module
    from server.utils.rate_limiter import RateLimiter

    monkeypatch.setattr(app_module, "rate_limiter", RateLimiter(max_requests=1, window_s=60))
    app = FastAPI()

    @app.post("/api/webhooks/razorpay")
    async def hook():
        return {"ok": True}

    @app.post("/api/anything")
    async def other():
        return {"ok": True}

    app.add_middleware(app_module.RateLimitMiddleware)
    client = TestClient(app)
    assert [client.post("/api/webhooks/razorpay").status_code for _ in range(5)] == [200] * 5
    assert [client.post("/api/anything").status_code for _ in range(2)] == [200, 429]


# ---------------------------------------------------------------------------
# Finding 7: zero-rating needs a foreign-currency order
# ---------------------------------------------------------------------------


def test_inr_payment_from_a_foreign_address_is_taxed_not_zero_rated():
    quote = tax_service.compute_tax(1000.0, "INR", fx_rate_inr=95.64, config=_config(),
                                    buyer=_buyer(state_code="", country="US"))
    assert quote["export"] is False
    assert quote["taxKind"] == "igst"
    assert quote["taxInrPaise"] == 18_000
    assert quote["placeOfSupplyCode"] == "US"


def test_foreign_currency_from_a_foreign_buyer_stays_a_zero_rated_export():
    quote = tax_service.compute_tax(10.0, "USD", fx_rate_inr=100.0, config=_config(),
                                    buyer=_buyer(state_code="", country="US"))
    assert quote["export"] is True and quote["taxKind"] == "export" and quote["taxMinor"] == 0


def test_indian_buyer_paying_inr_is_unchanged():
    quote = tax_service.compute_tax(1000.0, "INR", fx_rate_inr=95.64, config=_config(), buyer=_buyer())
    assert quote["taxKind"] == "cgst_sgst" and quote["taxInrPaise"] == 18_000


# ---------------------------------------------------------------------------
# Finding 15: unsafe Razorpay configuration
# ---------------------------------------------------------------------------


def test_reused_webhook_secret_and_test_key_in_production_are_refused():
    from server.config.env import razorpay_config_issues, razorpay_refused

    prod = SimpleNamespace(razorpay_api_key="rzp_test_x", razorpay_api_secret="same",
                           razorpay_webhook_secret="same", app_environment="production")
    assert razorpay_config_issues(prod) == ["webhook_secret_reuses_api_secret", "test_key_in_production"]
    assert razorpay_refused(prod) is True

    dev = SimpleNamespace(**{**vars(prod), "app_environment": "development"})
    assert razorpay_config_issues(dev) == ["webhook_secret_reuses_api_secret"]
    assert razorpay_refused(dev) is False

    clean = SimpleNamespace(razorpay_api_key="rzp_live_x", razorpay_api_secret="a",
                            razorpay_webhook_secret="b", app_environment="production")
    assert razorpay_config_issues(clean) == [] and razorpay_refused(clean) is False
