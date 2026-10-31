"""Manual wallet credits by platform admins: booking rules and abuse cases.

The routes are called directly with the database layer stubbed, so these tests
pin the decisions the route makes (kind, reference, refusal) rather than SQL.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import server.routes.app_admin as app_admin
import server.routes.dev_admin as dev_admin
import server.services.saas.billing_rates as billing_rates
import server.services.saas.billing_wallet_service as wallet_service
from server.auth.session import SessionData
from server.services.saas.admin_wallet_adjust import admin_adjust_reference

TENANT = uuid.uuid4()
SESSION = SessionData(kind="dev", subject="billing@example.com", tenant_id=None, role="billing_admin", issued_at=0)


@pytest.fixture
def ledger(monkeypatch):
    """Stub the wallet service and record what the route asked it to book."""
    calls = SimpleNamespace(
        credit=AsyncMock(), debit=AsyncMock(return_value={"ok": True}), audit=AsyncMock(), posted=set()
    )
    monkeypatch.setattr(dev_admin, "_require_db", lambda: None)
    monkeypatch.setattr(billing_rates, "load_current_rates", AsyncMock(return_value={"fx_rate_inr": 100.0}))
    monkeypatch.setattr(wallet_service, "credit_wallet", calls.credit)
    monkeypatch.setattr(wallet_service, "debit_wallet", calls.debit)
    monkeypatch.setattr(wallet_service, "wallet_summary", AsyncMock(return_value={"balanceUsd": 1.0}))
    monkeypatch.setattr(
        wallet_service,
        "get_or_create_wallet",
        AsyncMock(return_value=SimpleNamespace(currency="usd", balance_inr_paise=0, balance_cents=0)),
    )
    monkeypatch.setattr(dev_admin, "record_admin_action", calls.audit)
    for module in (dev_admin, app_admin):
        monkeypatch.setattr(module, "tenant_exists", AsyncMock(return_value=True))
        monkeypatch.setattr(module, "adjustment_already_posted", AsyncMock(side_effect=lambda ref: ref in calls.posted))
    return calls


def _body(**overrides):
    data = {"tenantId": str(TENANT), "amountUsdCents": 1000, "note": "Goodwill credit for outage", **overrides}
    return dev_admin.WalletAdjustBody(**data)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["topup", "razorpay_topup", "deposit", "did_refund", "admin_credit"])
async def test_admin_reason_never_becomes_a_paid_topup(ledger, reason):
    """A reason like "topup" would count as revenue and look like money the tenant paid."""
    await dev_admin.adjust_wallet(_body(reason=reason), session=SESSION)
    assert ledger.credit.await_args.kwargs["kind"] == "admin_grant"
    assert ledger.audit.await_args.kwargs["payload"]["reason"] == reason


@pytest.mark.asyncio
async def test_debit_is_booked_as_admin_debit_and_never_partial(ledger):
    await dev_admin.adjust_wallet(_body(amountUsdCents=-500, reason="topup"), session=SESSION)
    kwargs = ledger.debit.await_args.kwargs
    assert kwargs["kind"] == "admin_debit"
    assert kwargs["allow_partial"] is False
    ledger.credit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_tenant_is_refused_before_any_wallet_is_created(ledger, monkeypatch):
    monkeypatch.setattr(dev_admin, "tenant_exists", AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as err:
        await dev_admin.adjust_wallet(_body(), session=SESSION)
    assert err.value.status_code == 404
    ledger.credit.assert_not_awaited()


@pytest.mark.asyncio
async def test_retried_adjustment_with_the_same_key_is_booked_once(ledger):
    body = _body(idempotencyKey="0f8c2c4e-retry-key")
    await dev_admin.adjust_wallet(body, session=SESSION)
    ledger.posted.add(ledger.credit.await_args.kwargs["reference_id"])

    again = await dev_admin.adjust_wallet(body, session=SESSION)
    assert again["duplicate"] is True
    assert ledger.credit.await_count == 1
    assert ledger.audit.await_count == 1


def test_reference_depends_on_key_tenant_and_amount():
    assert admin_adjust_reference(TENANT, 100, "k-12345678") == admin_adjust_reference(TENANT, 100, "k-12345678")
    assert admin_adjust_reference(TENANT, 100, "k-12345678") != admin_adjust_reference(TENANT, 200, "k-12345678")
    assert admin_adjust_reference(TENANT, 100, "k-12345678") != admin_adjust_reference(uuid.uuid4(), 100, "k-12345678")
    # Without a key every request is its own adjustment.
    assert admin_adjust_reference(TENANT, 100, None) != admin_adjust_reference(TENANT, 100, None)
    assert len(admin_adjust_reference(TENANT, -100, "k" * 80)) <= 64


def test_malformed_idempotency_key_is_rejected():
    with pytest.raises(ValueError):
        _body(idempotencyKey="x'; drop table")


@pytest.mark.asyncio
async def test_rupee_amount_into_inr_wallet_is_booked_exactly(ledger, monkeypatch):
    monkeypatch.setattr(
        wallet_service,
        "get_or_create_wallet",
        AsyncMock(return_value=SimpleNamespace(currency="inr", balance_inr_paise=0, balance_cents=0)),
    )
    # Round-tripping ₹1,234.57 through USD cents at 88.37 INR/USD lands on ₹1,234.53;
    # it must be booked as typed.
    monkeypatch.setattr(billing_rates, "load_current_rates", AsyncMock(return_value={"fx_rate_inr": 88.37}))
    await dev_admin.adjust_wallet(
        dev_admin.WalletAdjustBody(tenantId=str(TENANT), amountInrPaise=123457, note="Manual bank transfer"),
        session=SESSION,
    )
    kwargs = ledger.credit.await_args.kwargs
    assert kwargs["amount_inr_paise"] == 123457
    assert kwargs["amount_cents"] == 0


@pytest.mark.asyncio
async def test_console_credit_route_needs_a_statement_and_books_fixed_kind(ledger, monkeypatch):
    monkeypatch.setattr(app_admin, "_require_admin", lambda principal: None)
    monkeypatch.setattr(app_admin, "get_session_factory", lambda: object())
    monkeypatch.setattr(app_admin, "credit_wallet", ledger.credit)
    monkeypatch.setattr(app_admin, "wallet_summary", AsyncMock(return_value={}))
    import server.services.saas.admin_audit as admin_audit

    monkeypatch.setattr(admin_audit, "record_admin_action", ledger.audit)
    principal = SimpleNamespace(email="owner@example.com", user_id=uuid.uuid4(), tenant_id=uuid.uuid4())

    with pytest.raises(HTTPException) as err:
        await app_admin.admin_credits(
            app_admin.CreditBody(tenantId=str(TENANT), amountInrPaise=5000, reason="topup"), principal=principal
        )
    assert err.value.status_code == 400
    ledger.credit.assert_not_awaited()

    await app_admin.admin_credits(
        app_admin.CreditBody(tenantId=str(TENANT), amountInrPaise=5000, reason="topup", note="Goodwill credit"),
        principal=principal,
    )
    kwargs = ledger.credit.await_args.kwargs
    assert kwargs["kind"] == "admin_grant"
    # The admin's own user row is in another workspace; the ledger line names no user.
    assert "user_id" not in kwargs
