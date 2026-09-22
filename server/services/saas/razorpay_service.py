"""Razorpay wallet top-up + invoices."""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone

import razorpay
from sqlalchemy import select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.saas_models import (
    BillingInvoice,
    BillingWallet,
    BillingWalletTransaction,
    RazorpayOrder,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _client() -> razorpay.Client:
    settings = get_settings()
    if not settings.razorpay_api_key or not settings.razorpay_api_secret:
        raise ValueError("razorpay_not_configured")
    return razorpay.Client(auth=(settings.razorpay_api_key, settings.razorpay_api_secret))


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    settings = get_settings()
    secret = settings.razorpay_api_secret or ""
    payload = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def create_wallet_order(tenant_id: uuid.UUID, amount_inr: float) -> dict:
    if amount_inr < 100:
        raise ValueError("minimum_amount_inr")
    paise = int(round(amount_inr * 100))
    client = _client()
    order = client.order.create({"amount": paise, "currency": "INR", "payment_capture": 1})
    order_id = order["id"]
    factory = get_session_factory()
    if factory:
        async with factory() as session:
            session.add(
                RazorpayOrder(
                    order_id=order_id,
                    tenant_id=tenant_id,
                    amount_inr_paise=paise,
                    status="created",
                    purpose="wallet_topup",
                    created_at=_utcnow(),
                )
            )
            await session.commit()
    settings = get_settings()
    return {
        "orderId": order_id,
        "amountInr": amount_inr,
        "amountPaise": paise,
        "currency": "INR",
        "keyId": settings.razorpay_api_key,
    }


async def confirm_wallet_payment(
    tenant_id: uuid.UUID,
    order_id: str,
    payment_id: str,
    signature: str,
) -> dict:
    if not verify_payment_signature(order_id, payment_id, signature):
        raise ValueError("invalid_signature")
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        row = await session.get(RazorpayOrder, order_id)
        if row is None or row.tenant_id != tenant_id:
            raise ValueError("order_not_found")
        if row.status == "paid":
            inv = (
                await session.execute(
                    select(BillingInvoice).where(BillingInvoice.razorpay_order_id == order_id)
                )
            ).scalar_one_or_none()
            return {"ok": True, "invoiceId": str(inv.invoice_id) if inv else None, "duplicate": True}
        paise = row.amount_inr_paise
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        wallet.balance_inr_paise += paise
        wallet.updated_at = _utcnow()
        row.status = "paid"
        inv_num = f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        invoice = BillingInvoice(
            tenant_id=tenant_id,
            invoice_number=inv_num,
            amount_inr_paise=paise,
            status="paid",
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
            line_items=[{"description": "Wallet top-up", "amountInr": paise / 100}],
            created_at=_utcnow(),
        )
        session.add(invoice)
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                amount_cents=0,
                kind="razorpay_topup_inr",
                stripe_session_id=payment_id,
                created_at=_utcnow(),
            )
        )
        await session.commit()
        return {
            "ok": True,
            "invoiceId": str(invoice.invoice_id),
            "invoiceNumber": inv_num,
            "balanceInr": wallet.balance_inr_paise / 100,
        }


async def list_invoices(tenant_id: uuid.UUID, limit: int = 50) -> list[dict]:
    factory = get_session_factory()
    if factory is None:
        return []
    async with factory() as session:
        result = await session.execute(
            select(BillingInvoice)
            .where(BillingInvoice.tenant_id == tenant_id)
            .order_by(BillingInvoice.created_at.desc())
            .limit(limit)
        )
        return [
            {
                "invoiceId": str(r.invoice_id),
                "invoiceNumber": r.invoice_number,
                "amountInr": r.amount_inr_paise / 100,
                "status": r.status,
                "createdAt": r.created_at.isoformat(),
                "paymentId": r.razorpay_payment_id,
            }
            for r in result.scalars()
        ]
