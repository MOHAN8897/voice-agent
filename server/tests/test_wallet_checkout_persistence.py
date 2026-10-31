from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from server.db.models.entities import Base
from server.db.models.saas_models import (
    BillingInvoice,
    BillingWallet,
    BillingWalletTransaction,
    CreditNote,
    InvoiceSequence,
    PlatformTaxSettings,
    RazorpayOrder,
    RazorpayRefund,
)
from server.services.saas import razorpay_service, tax_service
from server.tests.test_billing_gst_invoices import _config
from server.tests.test_integration_security_hardening import TID
from server.tests.test_integration_security_hardening import db as shared_db

db = shared_db


async def test_stale_tax_editor_cannot_overwrite_newer_saved_rules(db, monkeypatch):
    async with db.kw["bind"].begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[PlatformTaxSettings.__table__]))
    monkeypatch.setattr(tax_service, "get_session_factory", lambda: db)
    await tax_service.save_config({"enabled": False, "defaultRateBps": 1800}, actor="fixture")
    initial = await tax_service.load_config(strict=True)
    await tax_service.save_config({**initial, "defaultRateBps": 2000, "expectedUpdatedAt": initial["updatedAt"]}, actor="fixture")
    with pytest.raises(ValueError, match="tax_settings_conflict"):
        await tax_service.save_config({**initial, "defaultRateBps": 500, "expectedUpdatedAt": initial["updatedAt"]}, actor="stale-fixture")
    assert (await tax_service.load_config(strict=True))["defaultRateBps"] == 2000


@pytest.fixture
async def payment_store(db, monkeypatch):
    models = [BillingWallet, BillingWalletTransaction, RazorpayOrder, InvoiceSequence, BillingInvoice, RazorpayRefund, CreditNote]
    async with db.kw["bind"].begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[model.__table__ for model in models]))
    async with db() as session:
        session.add(BillingWallet(tenant_id=TID, balance_cents=0, balance_inr_paise=0))
        session.add(RazorpayOrder(order_id="order-persist", tenant_id=TID, currency="INR", status="created",
            amount_minor=118000, gross_minor=118000, taxable_minor=100000, tax_minor=18000,
            tax_rate_bps=1800, tax_kind="igst", amount_inr_paise=100000, created_at=datetime.now(timezone.utc)))
        await session.commit()
    monkeypatch.setattr(razorpay_service, "get_session_factory", lambda: db)
    monkeypatch.setattr(tax_service, "load_config", AsyncMock(return_value=_config()))
    monkeypatch.setattr("server.services.saas.activity_log.record_event", AsyncMock())
    return db


async def test_capture_replay_keeps_one_invoice_one_credit_and_excludes_tax(payment_store):
    payment = {"id": "payment-persist", "order_id": "order-persist", "status": "captured",
        "currency": "INR", "amount": 118000, "international": True, "base_amount": 118000}
    first = await razorpay_service._credit_order_payment("order-persist", "payment-persist", payment, source="webhook")
    second = await razorpay_service._credit_order_payment("order-persist", "payment-persist", payment, source="checkout")
    assert first["creditedInr"] == second["creditedInr"] == 1000 and second["duplicate"]
    async with payment_store() as session:
        wallet = await session.get(BillingWallet, TID)
        assert wallet.balance_inr_paise == 100000
        assert await session.scalar(select(func.count()).select_from(BillingInvoice)) == 1
        assert await session.scalar(select(func.count()).select_from(BillingWalletTransaction)) == 1
        invoice = await session.scalar(select(BillingInvoice))
        assert invoice.tax_inr_paise == 18000 and invoice.igst_inr_paise == 18000


async def test_wrong_order_replay_cannot_use_existing_payment_credit(payment_store):
    payment = {"id": "payment-persist", "order_id": "order-persist", "status": "captured", "currency": "INR", "amount": 118000}
    await razorpay_service._credit_order_payment("order-persist", "payment-persist", payment, source="webhook")
    async with payment_store() as session:
        session.add(RazorpayOrder(order_id="another-order", tenant_id=TID, currency="INR", status="created",
            amount_minor=118000, gross_minor=118000, amount_inr_paise=100000))
        await session.commit()
    with pytest.raises(ValueError, match="payment_order_mismatch"):
        await razorpay_service._credit_order_payment("another-order", "payment-persist", payment, source="checkout")
    async with payment_store() as session:
        assert (await session.get(BillingWallet, TID)).balance_inr_paise == 100000


async def test_small_partial_refunds_never_reverse_more_credit_or_tax_than_paid(payment_store):
    async with payment_store() as session:
        session.add(BillingInvoice(tenant_id=TID, invoice_number="INV-SMALL", amount_minor=3, currency="INR",
            amount_inr_paise=2, taxable_inr_paise=2, tax_inr_paise=1, igst_inr_paise=1, tax_kind="igst",
            razorpay_payment_id="payment-small", status="paid"))
        wallet = await session.get(BillingWallet, TID)
        wallet.balance_inr_paise = 2
        await session.commit()
    for index in range(3):
        await razorpay_service.apply_refund(refund_id=f"refund-{index}", payment_id="payment-small",
            amount_minor=1, currency="INR", reason="Fixture refund", created_by="fixture")
    async with payment_store() as session:
        assert (await session.get(BillingWallet, TID)).balance_inr_paise == 0
        assert await session.scalar(select(func.sum(CreditNote.taxable_inr_paise))) == 2
        assert await session.scalar(select(func.sum(CreditNote.tax_inr_paise))) == 1
