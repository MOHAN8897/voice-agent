"""Tenant wallet balance, ledger, PSTN usage debits, Stripe/Razorpay top-ups."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_or_create_wallet(tenant_id: uuid.UUID) -> BillingWallet:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, updated_at=_utcnow())
            session.add(wallet)
            await session.commit()
            await session.refresh(wallet)
        return wallet


async def wallet_summary(tenant_id: uuid.UUID) -> dict:
    settings = get_settings()
    wallet = await get_or_create_wallet(tenant_id)
    inr_paise = int(getattr(wallet, "balance_inr_paise", 0) or 0)
    primary = (wallet.currency or "usd").lower()
    return {
        "balanceUsd": round(wallet.balance_cents / 100.0, 2),
        "balanceCents": wallet.balance_cents,
        "balanceInr": round(inr_paise / 100.0, 2),
        "balanceInrPaise": inr_paise,
        "currency": wallet.currency.upper(),
        "primaryCurrency": primary,
        "tenantId": str(tenant_id),
        "minBalanceUsd": round(settings.pstn_min_balance_usd_cents / 100.0, 2),
        "minBalanceInr": round(settings.pstn_min_balance_inr_paise / 100.0, 2),
        "rateUsdPerMin": round(settings.pstn_rate_usd_cents_per_min / 100.0, 3),
        "rateInrPerMin": round(settings.pstn_rate_inr_paise_per_min / 100.0, 2),
    }


async def list_wallet_transactions(tenant_id: uuid.UUID, limit: int = 50) -> list[dict]:
    factory = get_session_factory()
    if factory is None:
        return []
    limit = max(1, min(limit, 200))
    async with factory() as session:
        result = await session.execute(
            select(BillingWalletTransaction)
            .where(BillingWalletTransaction.tenant_id == tenant_id)
            .order_by(BillingWalletTransaction.created_at.desc())
            .limit(limit)
        )
        rows = []
        for tx in result.scalars():
            rows.append(
                {
                    "id": str(tx.id),
                    "kind": tx.kind,
                    "amountCents": tx.amount_cents,
                    "amountInrPaise": int(tx.amount_inr_paise or 0),
                    "referenceId": tx.reference_id,
                    "createdAt": tx.created_at.isoformat() if tx.created_at else None,
                }
            )
        return rows


def _wallet_has_minimum(wallet: BillingWallet) -> bool:
    settings = get_settings()
    primary = (wallet.currency or "usd").lower()
    if primary == "inr":
        return int(wallet.balance_inr_paise or 0) >= settings.pstn_min_balance_inr_paise
    return wallet.balance_cents >= settings.pstn_min_balance_usd_cents


async def assert_wallet_allows_pstn(tenant_id: uuid.UUID) -> None:
    """Block PSTN when balance is below configured minimum."""
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return
    wallet = await get_or_create_wallet(tenant_id)
    if not _wallet_has_minimum(wallet):
        raise HTTPException(
            status_code=402,
            detail={
                "error": {
                    "code": "insufficient_balance",
                    "message": "Add funds to your wallet before placing PSTN calls.",
                }
            },
        )


async def bill_pstn_call_if_applicable(call_id: str) -> None:
    """Idempotent usage debit after a PSTN call ends."""
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return
    from server.call.call_store import call_store

    stored = await call_store.get(call_id)
    if not stored or stored.get("channel") != "pstn":
        return
    tenant_raw = stored.get("tenant_id")
    if not tenant_raw:
        return
    try:
        tenant_id = uuid.UUID(str(tenant_raw))
    except ValueError:
        return
    duration_sec = int(stored.get("duration_sec") or 0)
    if duration_sec <= 0:
        duration_sec = 60
    minutes = max(1, (duration_sec + 59) // 60)
    ref = f"call:{call_id}"
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        dup = await session.execute(
            select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id == ref)
        )
        if dup.scalar_one_or_none():
            return
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        primary = (wallet.currency or "usd").lower()
        if primary == "inr":
            debit_paise = minutes * settings.pstn_rate_inr_paise_per_min
            if int(wallet.balance_inr_paise or 0) < debit_paise:
                debit_paise = int(wallet.balance_inr_paise or 0)
            wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) - debit_paise
            session.add(
                BillingWalletTransaction(
                    tenant_id=tenant_id,
                    amount_cents=0,
                    amount_inr_paise=-debit_paise,
                    kind="usage_pstn",
                    reference_id=ref,
                    created_at=_utcnow(),
                )
            )
        else:
            debit_cents = minutes * settings.pstn_rate_usd_cents_per_min
            if wallet.balance_cents < debit_cents:
                debit_cents = wallet.balance_cents
            wallet.balance_cents -= debit_cents
            session.add(
                BillingWalletTransaction(
                    tenant_id=tenant_id,
                    amount_cents=-debit_cents,
                    amount_inr_paise=0,
                    kind="usage_pstn",
                    reference_id=ref,
                    created_at=_utcnow(),
                )
            )
        wallet.updated_at = _utcnow()
        await session.commit()
    logger.info("[WALLET] billed pstn call=%s tenant=%s minutes=%s", call_id, tenant_id, minutes)


async def create_topup_checkout(tenant_id: uuid.UUID, amount_usd: float, email: str) -> dict:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise ValueError("stripe_not_configured")
    if amount_usd < 5 or amount_usd > 500:
        raise ValueError("amount_out_of_range")
    cents = int(round(amount_usd * 100))
    import stripe

    stripe.api_key = settings.stripe_secret_key
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=settings.stripe_checkout_success_url.replace("numbers", "billing") + "&topup=1",
        cancel_url=settings.stripe_checkout_cancel_url,
        metadata={
            "type": "wallet_topup",
            "tenant_id": str(tenant_id),
            "amount_cents": str(cents),
        },
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Voxly wallet top-up"},
                    "unit_amount": cents,
                },
                "quantity": 1,
            }
        ],
        customer_email=email or None,
    )
    return {"checkoutUrl": session.url, "sessionId": session.id}


async def credit_topup_from_session(tenant_id: uuid.UUID, session_id: str, amount_cents: int) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        dup = await session.execute(
            select(BillingWalletTransaction).where(BillingWalletTransaction.stripe_session_id == session_id)
        )
        if dup.scalar_one_or_none():
            return
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        wallet.balance_cents += amount_cents
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                amount_cents=amount_cents,
                kind="topup",
                stripe_session_id=session_id,
                created_at=_utcnow(),
            )
        )
        await session.commit()
