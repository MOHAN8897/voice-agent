"""Razorpay wallet order + signature verification (mocked)."""
from __future__ import annotations

import hashlib
import hmac
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.services.saas import razorpay_service as razorpay_service_module
from server.services.saas.razorpay_service import (
    _run_provider_call,
    _validate_payment_details,
    verify_payment_signature,
)


def test_verify_payment_signature_valid():
    order_id = "order_test123"
    payment_id = "pay_test456"
    secret = "test_secret"
    body = f"{order_id}|{payment_id}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    with patch("server.services.saas.razorpay_service.get_settings") as gs:
        gs.return_value = MagicMock(razorpay_api_secret=secret)
        assert verify_payment_signature(order_id, payment_id, sig) is True


def test_verify_payment_signature_rejects_tamper():
    with patch("server.services.saas.razorpay_service.get_settings") as gs:
        gs.return_value = MagicMock(razorpay_api_secret="secret")
        assert verify_payment_signature("o", "p", "bad") is False


def test_provider_payment_must_match_order_amount_currency_and_capture_state():
    _validate_payment_details(
        {
            "id": "pay_1",
            "order_id": "order_1",
            "status": "captured",
            "amount": 12500,
            "currency": "INR",
        },
        payment_id="pay_1",
        order_id="order_1",
        currency="INR",
        amount_minor=12500,
    )

    valid = {
        "id": "pay_1",
        "order_id": "order_1",
        "status": "captured",
        "amount": 12500,
        "currency": "INR",
    }
    for details, error in (
        ({**valid, "order_id": "order_other"}, "payment_order_mismatch"),
        ({**valid, "status": "authorized"}, "payment_not_captured"),
        ({**valid, "amount": 12499}, "payment_amount_mismatch"),
        ({**valid, "currency": "USD"}, "payment_currency_mismatch"),
    ):
        with pytest.raises(ValueError, match=error):
            _validate_payment_details(
                details,
                payment_id="pay_1",
                order_id="order_1",
                currency="INR",
                amount_minor=12500,
            )


def test_provider_payment_requires_all_identity_and_settlement_fields():
    valid = {
        "id": "pay_1",
        "order_id": "order_1",
        "status": "captured",
        "amount": 12500,
        "currency": "INR",
    }
    for field, error in (
        ("id", "payment_id_mismatch"),
        ("order_id", "payment_order_mismatch"),
        ("status", "payment_not_captured"),
        ("amount", "payment_amount_mismatch"),
        ("currency", "payment_currency_mismatch"),
    ):
        details = dict(valid)
        del details[field]
        with pytest.raises(ValueError, match=error):
            _validate_payment_details(
                details,
                payment_id="pay_1",
                order_id="order_1",
                currency="INR",
                amount_minor=12500,
            )

    with pytest.raises(ValueError, match="payment_id_mismatch"):
        _validate_payment_details(
            {**valid, "id": "pay_other"},
            payment_id="pay_1",
            order_id="order_1",
            currency="INR",
            amount_minor=12500,
        )


@pytest.mark.asyncio
async def test_blocking_provider_call_runs_off_the_event_loop_thread():
    event_loop_thread = threading.get_ident()

    result = await _run_provider_call(threading.get_ident)

    assert result != event_loop_thread


def test_razorpay_verify_body_bounds():
    from pydantic import ValidationError

    from server.routes.app_billing import RazorpayVerifyBody

    # Valid payload
    body = RazorpayVerifyBody(
        razorpay_order_id="order_123456",
        razorpay_payment_id="pay_123456",
        razorpay_signature="a" * 64,
    )
    assert body.razorpay_order_id == "order_123456"

    # Too short order id
    with pytest.raises(ValidationError):
        RazorpayVerifyBody(
            razorpay_order_id="o",
            razorpay_payment_id="pay_123456",
            razorpay_signature="a" * 64,
        )

    # Too short signature
    with pytest.raises(ValidationError):
        RazorpayVerifyBody(
            razorpay_order_id="order_123456",
            razorpay_payment_id="pay_123456",
            razorpay_signature="short",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_outcome", ["timeout", "empty"])
async def test_unconfirmed_payment_does_not_credit_wallet(monkeypatch, provider_outcome):
    tenant_id = uuid.uuid4()
    order = SimpleNamespace(
        tenant_id=tenant_id,
        status="created",
        currency="INR",
        amount_minor=10000,
        amount_inr_paise=10000,
    )

    class FakeSession:
        def __init__(self):
            self.get_calls = []
            self.commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, model, ident, **kwargs):
            self.get_calls.append((model, ident, kwargs))
            if model is razorpay_service_module.RazorpayOrder:
                return order
            return None

        async def commit(self):
            self.commits += 1

    sessions = []

    def factory():
        session = FakeSession()
        sessions.append(session)
        return session

    async def provider_call(*_args, **_kwargs):
        if provider_outcome == "timeout":
            raise TimeoutError

    monkeypatch.setattr(razorpay_service_module, "get_session_factory", lambda: factory)
    monkeypatch.setattr(razorpay_service_module, "verify_payment_signature", lambda *_args: True)
    monkeypatch.setattr(razorpay_service_module, "_run_provider_call", provider_call)

    with pytest.raises(ValueError, match="payment_verification_unavailable"):
        await razorpay_service_module.confirm_wallet_payment(
            tenant_id,
            "order_test123",
            "pay_test456",
            "a" * 64,
        )

    assert len(sessions) == 1
    assert all(
        model is not razorpay_service_module.BillingWallet
        for model, _ident, _kwargs in sessions[0].get_calls
    )
    assert sessions[0].commits == 0


def test_provider_fetch_error_does_not_return_unverified_fallback(monkeypatch):
    import requests

    def fail_fetch(_payment_id):
        raise requests.exceptions.Timeout

    client = SimpleNamespace(payment=SimpleNamespace(fetch=fail_fetch))
    monkeypatch.setattr(razorpay_service_module, "_client", lambda: client)

    with pytest.raises(ValueError, match="payment_verification_unavailable"):
        razorpay_service_module._fetch_payment("pay_test456")


@pytest.mark.asyncio
async def test_payment_fetch_timeout_returns_retryable_status(monkeypatch):
    from fastapi import HTTPException

    from server.routes import app_billing

    async def unavailable(*_args, **_kwargs):
        raise ValueError("payment_verification_unavailable")

    monkeypatch.setattr(app_billing._billing_limiter, "allow", lambda *_args: (True, 0))
    monkeypatch.setattr(app_billing, "require_subscriber_permission", lambda *_args: None)
    monkeypatch.setattr(app_billing, "confirm_wallet_payment", unavailable)
    body = app_billing.RazorpayVerifyBody(
        razorpay_order_id="order_test123",
        razorpay_payment_id="pay_test456",
        razorpay_signature="a" * 64,
    )

    with pytest.raises(HTTPException) as caught:
        await app_billing.razorpay_verify(
            body,
            SimpleNamespace(tenant_id=uuid.uuid4(), user_id=uuid.uuid4()),
        )

    assert caught.value.status_code == 503
    assert caught.value.detail["error"]["code"] == "payment_verification_unavailable"


@pytest.mark.asyncio
async def test_confirm_wallet_payment_domestic_inr_success(monkeypatch):
    tenant_id = uuid.uuid4()
    order = SimpleNamespace(
        tenant_id=tenant_id,
        status="created",
        currency="INR",
        amount_minor=50000,
        amount_inr_paise=50000,
    )
    wallet = SimpleNamespace(
        tenant_id=tenant_id,
        balance_cents=0,
        balance_inr_paise=10000,
        currency="inr",
        updated_at=None,
    )

    class FakeSession:
        def __init__(self):
            self.added = []
            self.commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, model, ident, **kwargs):
            if model is razorpay_service_module.RazorpayOrder:
                return order
            if model is razorpay_service_module.BillingWallet:
                return wallet
            if getattr(model, "__name__", "") == "InvoiceSequence":
                from server.db.models.saas_models import InvoiceSequence

                return InvoiceSequence(kind=ident[0], fy=ident[1], last_number=0)
            return None

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            pass

        async def commit(self):
            self.commits += 1

        async def execute(self, stmt):
            class ScalarResult:
                def scalar_one_or_none(self):
                    return None
            return ScalarResult()

    fake_session = FakeSession()
    monkeypatch.setattr(razorpay_service_module, "get_session_factory", lambda: lambda: fake_session)
    monkeypatch.setattr(razorpay_service_module, "verify_payment_signature", lambda *_args: True)

    payment_record = {
        "id": "pay_test456",
        "order_id": "order_test123",
        "status": "captured",
        "amount": 50000,
        "currency": "INR",
        "base_amount": None,  # Domestic INR has no base_amount
        "international": False,
    }
    async def mock_run_provider_call(fn, *args):
        return payment_record

    monkeypatch.setattr(razorpay_service_module, "_run_provider_call", mock_run_provider_call)

    async def noop_record_event(*args, **kwargs):
        pass

    monkeypatch.setattr("server.services.saas.activity_log.record_event", noop_record_event)

    result = await razorpay_service_module.confirm_wallet_payment(
        tenant_id,
        "order_test123",
        "pay_test456",
        "a" * 64,
    )

    assert result["ok"] is True
    assert order.status == "paid"
    assert wallet.balance_inr_paise == 60000  # 10000 + 50000
    assert fake_session.commits == 1
    # Check that BillingInvoice and BillingWalletTransaction were added
    types = [type(item) for item in fake_session.added]
    assert razorpay_service_module.BillingInvoice in types
    assert razorpay_service_module.BillingWalletTransaction in types
    invoice = next(
        item for item in fake_session.added if isinstance(item, razorpay_service_module.BillingInvoice)
    )
    transaction = next(
        item
        for item in fake_session.added
        if isinstance(item, razorpay_service_module.BillingWalletTransaction)
    )
    assert invoice.tenant_id == tenant_id
    assert invoice.razorpay_order_id == "order_test123"
    assert invoice.razorpay_payment_id == "pay_test456"
    assert invoice.status == "paid"
    assert transaction.tenant_id == tenant_id
    assert transaction.reference_id == "razorpay:pay_test456"
    assert transaction.amount_inr_paise == 50000
    invoice = next(
        item for item in fake_session.added if isinstance(item, razorpay_service_module.BillingInvoice)
    )
    transaction = next(
        item
        for item in fake_session.added
        if isinstance(item, razorpay_service_module.BillingWalletTransaction)
    )
    assert invoice.tenant_id == tenant_id
    assert invoice.razorpay_order_id == "order_test123"
    assert invoice.razorpay_payment_id == "pay_test456"
    assert invoice.status == "paid"
    assert transaction.tenant_id == tenant_id
    assert transaction.reference_id == "razorpay:pay_test456"
    assert transaction.amount_inr_paise == 50000


def test_validate_payment_details_missing_fields():
    # Must fail closed if any field is missing or None
    with pytest.raises(ValueError, match="payment_order_mismatch"):
        razorpay_service_module._validate_payment_details(
            {"id": "pay_1", "status": "captured", "currency": "INR", "amount": 100},
            payment_id="pay_1",
            order_id="order_1",
            currency="INR",
            amount_minor=100,
        )

    with pytest.raises(ValueError, match="payment_not_captured"):
        razorpay_service_module._validate_payment_details(
            {"id": "pay_1", "order_id": "order_1", "status": "authorized", "currency": "INR", "amount": 100},
            payment_id="pay_1",
            order_id="order_1",
            currency="INR",
            amount_minor=100,
        )

    with pytest.raises(ValueError, match="payment_currency_mismatch"):
        razorpay_service_module._validate_payment_details(
            {"id": "pay_1", "order_id": "order_1", "status": "captured", "currency": "USD", "amount": 100},
            payment_id="pay_1",
            order_id="order_1",
            currency="INR",
            amount_minor=100,
        )

    with pytest.raises(ValueError, match="payment_amount_mismatch"):
        razorpay_service_module._validate_payment_details(
            {"id": "pay_1", "order_id": "order_1", "status": "captured", "currency": "INR", "amount": 50},
            payment_id="pay_1",
            order_id="order_1",
            currency="INR",
            amount_minor=100,
        )


@pytest.mark.asyncio
async def test_confirm_wallet_payment_duplicate_reference_id(monkeypatch):
    tenant_id = uuid.uuid4()
    order = razorpay_service_module.RazorpayOrder(
        order_id="order_test999",
        tenant_id=tenant_id,
        amount_inr_paise=50000,
        currency="INR",
        amount_minor=50000,
        status="created",
    )
    existing_tx = razorpay_service_module.BillingWalletTransaction(
        tenant_id=tenant_id,
        amount_cents=0,
        amount_inr_paise=50000,
        kind="razorpay_topup_inr",
        reference_id="razorpay:pay_test999",
    )
    existing_invoice = razorpay_service_module.BillingInvoice(
        tenant_id=tenant_id,
        invoice_id=uuid.uuid4(),
        invoice_number="INV-20261014-TEST",
        amount_inr_paise=50000,
        currency="INR",
        amount_minor=50000,
        status="paid",
        razorpay_order_id="order_test999",
        razorpay_payment_id="pay_test999",
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, model, ident, **kwargs):
            if model is razorpay_service_module.RazorpayOrder:
                return order
            return None

        async def execute(self, stmt):
            class ScalarResult:
                def scalar_one_or_none(self_inner):
                    entity = stmt.column_descriptions[0]["entity"]
                    if entity is razorpay_service_module.BillingInvoice:
                        return existing_invoice
                    return existing_tx
            return ScalarResult()

    fake_session = FakeSession()
    monkeypatch.setattr(razorpay_service_module, "get_session_factory", lambda: lambda: fake_session)
    monkeypatch.setattr(razorpay_service_module, "verify_payment_signature", lambda *_args: True)
    monkeypatch.setattr(
        razorpay_service_module,
        "_run_provider_call",
        AsyncMock(return_value={
            "id": "pay_test999",
            "order_id": "order_test999",
            "status": "captured",
            "currency": "INR",
            "amount": 50000,
        }),
    )

    result = await razorpay_service_module.confirm_wallet_payment(
        tenant_id, "order_test999", "pay_test999", "sig"
    )
    assert result["ok"] is True
    assert result["duplicate"] is True
