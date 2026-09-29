"""Usage ledger: tenant wallet, per-user attribution, PSTN / web / DID debits."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_user_id(raw: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


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


async def wallet_summary(tenant_id: uuid.UUID, user_id: uuid.UUID | None = None) -> dict:
    settings = get_settings()
    wallet = await get_or_create_wallet(tenant_id)
    inr_paise = int(getattr(wallet, "balance_inr_paise", 0) or 0)
    primary = (wallet.currency or "usd").lower()
    rate_inr = settings.pstn_rate_inr_paise_per_min or 900
    remaining_min = int(inr_paise // rate_inr) if primary == "inr" and rate_inr else int(
        (wallet.balance_cents or 0) // max(1, settings.pstn_rate_usd_cents_per_min)
    )
    summary = {
        "balanceUsd": round(wallet.balance_cents / 100.0, 2),
        "balanceCents": wallet.balance_cents,
        "balanceInr": round(inr_paise / 100.0, 2),
        "balanceInrPaise": inr_paise,
        "currency": (wallet.currency or "usd").upper(),
        "primaryCurrency": primary,
        "tenantId": str(tenant_id),
        "minBalanceUsd": round(settings.pstn_min_balance_usd_cents / 100.0, 2),
        "minBalanceInr": round(settings.pstn_min_balance_inr_paise / 100.0, 2),
        "rateUsdPerMin": round(settings.pstn_rate_usd_cents_per_min / 100.0, 3),
        "rateInrPerMin": round(settings.pstn_rate_inr_paise_per_min / 100.0, 2),
        "webRateInrPerMin": round(settings.web_agent_rate_inr_paise_per_min / 100.0, 2),
        "didMonthlyInr": round(settings.did_monthly_inr_paise / 100.0, 2),
        "remainingMinutes": remaining_min,
        "myUsageInr": 0.0,
        "myUsagePaise": 0,
    }
    if user_id is not None:
        factory = get_session_factory()
        if factory is not None:
            async with factory() as session:
                spent = (
                    await session.execute(
                        select(func.coalesce(func.sum(BillingWalletTransaction.amount_inr_paise), 0)).where(
                            BillingWalletTransaction.tenant_id == tenant_id,
                            BillingWalletTransaction.user_id == user_id,
                            BillingWalletTransaction.amount_inr_paise < 0,
                        )
                    )
                ).scalar_one()
                paise = abs(int(spent or 0))
                summary["myUsagePaise"] = paise
                summary["myUsageInr"] = round(paise / 100.0, 2)
    return summary


async def list_wallet_transactions(tenant_id: uuid.UUID, limit: int = 50, user_id: uuid.UUID | None = None) -> list[dict]:
    factory = get_session_factory()
    if factory is None:
        return []
    limit = max(1, min(limit, 200))
    async with factory() as session:
        stmt = select(BillingWalletTransaction).where(BillingWalletTransaction.tenant_id == tenant_id)
        if user_id is not None:
            stmt = stmt.where(BillingWalletTransaction.user_id == user_id)
        result = await session.execute(stmt.order_by(BillingWalletTransaction.created_at.desc()).limit(limit))
        rows = []
        for tx in result.scalars():
            rows.append(
                {
                    "id": str(tx.id),
                    "kind": tx.kind,
                    "amountCents": tx.amount_cents,
                    "amountInrPaise": int(tx.amount_inr_paise or 0),
                    "referenceId": tx.reference_id,
                    "userId": str(tx.user_id) if tx.user_id else None,
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
    """Block billed voice when balance is below configured minimum."""
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
                    "message": "Add funds to your wallet before using voice minutes.",
                }
            },
        )


assert_wallet_allows_usage = assert_wallet_allows_pstn


async def wallet_allows_inbound(tenant_id: uuid.UUID | None) -> bool:
    """Whether inbound calls should be answered for this tenant.

    Returns a decision, never raises: the caller is on the live PSTN answer path,
    where an exception or a slow query must not drop a customer's call. On any
    internal error this returns True, which matches the pre-wallet behaviour of
    answering everything.
    """
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return True
    if not settings.pstn_enforce_wallet_on_inbound:
        return True
    if tenant_id is None:
        return True
    try:
        wallet = await get_or_create_wallet(tenant_id)
    except Exception:
        logger.warning("[WALLET] inbound balance check failed; answering (fail open)")
        return True
    allowed = _wallet_has_minimum(wallet)
    if not allowed:
        logger.info(
            "[WALLET] inbound blocked tenant=%s below minimum usd_cents=%s inr_paise=%s",
            tenant_id,
            settings.pstn_min_balance_usd_cents,
            settings.pstn_min_balance_inr_paise,
        )
    return allowed


async def maybe_seed_admin_credits(tenant_id: uuid.UUID, user_id: uuid.UUID, email: str) -> None:
    from server.services.saas.platform_admins import is_platform_admin_email, is_dev_tester_email

    settings = get_settings()
    if not (is_platform_admin_email(email) or is_dev_tester_email(email)):
        return
    seed = int(settings.saas_admin_seed_inr_paise or 0)
    if seed <= 0:
        return
    ref = f"admin_seed:{tenant_id}"
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
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, currency="inr", updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        wallet.currency = "inr"
        wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) + seed
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                user_id=user_id,
                amount_cents=0,
                amount_inr_paise=seed,
                kind="admin_seed",
                reference_id=ref,
                created_at=_utcnow(),
            )
        )
        await session.commit()
    logger.info("[WALLET] seeded admin credits tenant=%s paise=%s", tenant_id, seed)


async def credit_wallet(
    tenant_id: uuid.UUID,
    *,
    amount_cents: int = 0,
    amount_inr_paise: int = 0,
    kind: str,
    reference_id: str | None = None,
    user_id: uuid.UUID | None = None,
    stripe_session_id: str | None = None,
) -> None:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        if reference_id:
            dup = await session.execute(
                select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id == reference_id)
            )
            if dup.scalar_one_or_none():
                return
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        if amount_inr_paise:
            wallet.currency = wallet.currency or "inr"
            wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) + int(amount_inr_paise)
        if amount_cents:
            wallet.balance_cents = int(wallet.balance_cents or 0) + int(amount_cents)
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                user_id=user_id,
                amount_cents=int(amount_cents),
                amount_inr_paise=int(amount_inr_paise),
                kind=kind,
                reference_id=reference_id,
                stripe_session_id=stripe_session_id,
                created_at=_utcnow(),
            )
        )
        await session.commit()


async def debit_wallet(
    tenant_id: uuid.UUID,
    *,
    kind: str,
    reference_id: str,
    user_id: uuid.UUID | None = None,
    amount_cents: int = 0,
    amount_inr_paise: int = 0,
    allow_partial: bool = True,
) -> dict:
    """Atomic debit. Raises 402 if empty and not allow_partial."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    async with factory() as session:
        dup = await session.execute(
            select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id == reference_id)
        )
        if dup.scalar_one_or_none():
            return {"ok": True, "duplicate": True, "amountCents": 0, "amountInrPaise": 0}
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow())
            session.add(wallet)
            await session.flush()
        primary = (wallet.currency or "usd").lower()
        debit_cents = 0
        debit_paise = 0
        if primary == "inr" or amount_inr_paise:
            want = abs(int(amount_inr_paise))
            have = int(wallet.balance_inr_paise or 0)
            if have < want and not allow_partial:
                raise HTTPException(
                    status_code=402,
                    detail={"error": {"code": "insufficient_balance", "message": "Not enough wallet credits."}},
                )
            debit_paise = min(have, want) if allow_partial else want
            wallet.balance_inr_paise = have - debit_paise
            wallet.currency = "inr"
        else:
            want = abs(int(amount_cents))
            have = int(wallet.balance_cents or 0)
            if have < want and not allow_partial:
                raise HTTPException(
                    status_code=402,
                    detail={"error": {"code": "insufficient_balance", "message": "Not enough wallet credits."}},
                )
            debit_cents = min(have, want) if allow_partial else want
            wallet.balance_cents = have - debit_cents
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                user_id=user_id,
                amount_cents=-debit_cents,
                amount_inr_paise=-debit_paise,
                kind=kind,
                reference_id=reference_id,
                created_at=_utcnow(),
            )
        )
        await session.commit()
        return {"ok": True, "amountCents": debit_cents, "amountInrPaise": debit_paise}


async def bill_pstn_call_if_applicable(call_id: str) -> None:
    await bill_call_usage_if_applicable(call_id)


def _resolve_call_wallet_debit(
    *,
    call_id: str,
    channel: str,
    duration_sec: int,
    settings: Any,
) -> tuple[int, int, str]:
    """Return (usd_cents, inr_paise, billing_mode) for wallet debit."""
    from server.call.call_ledger import call_ledger

    meta = call_ledger.read_meta(call_id) or {}
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    cost_inr = usage.get("cost_inr")
    cost_usd = usage.get("cost_usd")
    if cost_inr is not None and float(cost_inr) > 0:
        paise = max(1, int(round(float(cost_inr) * 100)))
        usd = float(cost_usd or 0)
        if usd > 0:
            cents = max(1, int(round(usd * 100)))
        else:
            fx = float(usage.get("fx_rate_inr") or getattr(settings, "fx_rate_inr", 0) or 95.64)
            cents = max(1, int(round(paise / fx))) if fx > 0 else 1
        return cents, paise, "ledger_usage"
    minutes = max(0.0, float(duration_sec)) / 60.0
    if minutes <= 0:
        minutes = 1.0 / 60.0
    if channel == "pstn":
        cents = int(round(minutes * settings.pstn_rate_usd_cents_per_min))
        paise = int(round(minutes * settings.pstn_rate_inr_paise_per_min))
    else:
        cents = int(round(minutes * settings.web_agent_rate_usd_cents_per_min))
        paise = int(round(minutes * settings.web_agent_rate_inr_paise_per_min))
    return max(1, cents), max(1, paise), "catalog_prorated"


async def bill_call_usage_if_applicable(call_id: str) -> None:
    """Idempotent usage debit after any billed voice session ends."""
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return
    from server.call.call_store import call_store

    stored = await call_store.get(call_id)
    if not stored:
        return
    channel = str(stored.get("channel") or "")
    if channel not in {"pstn", "browser"}:
        return
    tenant_raw = stored.get("tenant_id")
    if not tenant_raw:
        return
    try:
        tenant_id = uuid.UUID(str(tenant_raw))
    except ValueError:
        return
    billed_user = None
    try:
        from server.call.call_ledger import call_ledger

        meta = call_ledger.review_fields(call_id) or {}
        billed_user = _parse_user_id(meta.get("billed_user_id") or stored.get("billed_user_id"))
    except Exception:
        billed_user = _parse_user_id(stored.get("billed_user_id"))
    if channel == "browser" and billed_user is None:
        return
    duration_sec = int(stored.get("duration_sec") or 0)
    if duration_sec <= 0:
        duration_sec = 60
    kind = "usage_pstn" if channel == "pstn" else "usage_web"
    ref = f"call:{call_id}"
    cents, paise, billing_mode = _resolve_call_wallet_debit(
        call_id=call_id,
        channel=channel,
        duration_sec=duration_sec,
        settings=settings,
    )
    try:
        await debit_wallet(
            tenant_id,
            kind=kind,
            reference_id=ref,
            user_id=billed_user,
            amount_cents=cents,
            amount_inr_paise=paise,
            allow_partial=True,
        )
    except Exception as exc:
        logger.warning("[WALLET] bill failed call=%s err=%s", call_id, str(exc)[:160])
        return
    logger.info(
        "[WALLET] billed %s call=%s tenant=%s mode=%s paise=%s",
        kind,
        call_id,
        tenant_id,
        billing_mode,
        paise,
    )


async def debit_did_purchase(
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    e164: str,
    purchase_id: uuid.UUID,
) -> dict:
    """Charge the monthly number rental.

    A number is bought either from the USD credit or the INR credit, whichever the
    workspace actually holds — the price is the same in both, so a tenant funded in
    one currency is never locked out by the other's empty balance.
    """
    settings = get_settings()
    want_cents = int(settings.did_monthly_usd_cents)
    want_paise = int(settings.did_monthly_inr_paise)
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")

    async with factory() as session:
        ref = f"did:{purchase_id}"
        dup = await session.execute(
            select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id == ref)
        )
        if dup.scalar_one_or_none():
            return {"ok": True, "duplicate": True, "amountCents": 0, "amountInrPaise": 0}
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow())
            session.add(wallet)
            await session.flush()

        have_cents = int(wallet.balance_cents or 0)
        have_paise = int(wallet.balance_inr_paise or 0)
        # Prefer the wallet's own primary currency, then whichever leg can cover it.
        primary = (wallet.currency or "usd").lower()
        if primary == "inr" and have_paise >= want_paise:
            take_cents, take_paise = 0, want_paise
        elif have_cents >= want_cents:
            take_cents, take_paise = want_cents, 0
        elif have_paise >= want_paise:
            take_cents, take_paise = 0, want_paise
        else:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": {
                        "code": "insufficient_balance",
                        "message": (
                            "Add funds to your wallet before buying a phone number. "
                            f"A number costs ${want_cents / 100:.2f} or ₹{want_paise / 100:.2f}."
                        ),
                    }
                },
            )

        wallet.balance_cents = have_cents - take_cents
        wallet.balance_inr_paise = have_paise - take_paise
        if take_paise and not take_cents:
            wallet.currency = "inr"
        elif take_cents and not take_paise:
            wallet.currency = "usd"
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                user_id=user_id,
                amount_cents=-take_cents,
                amount_inr_paise=-take_paise,
                kind="did_purchase",
                reference_id=ref,
                created_at=_utcnow(),
            )
        )
        await session.commit()
        return {"ok": True, "amountCents": take_cents, "amountInrPaise": take_paise}


async def refund_did_purchase(
    tenant_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None,
    purchase_id: uuid.UUID,
) -> dict[str, Any]:
    """Reverse exactly what a number purchase took.

    The purchase debits a single currency leg (whichever the workspace was funded
    in), so the refund must credit that same leg. Crediting both would mint money
    that was never collected. The original ledger row is therefore the source of
    truth, not the current price — a price change between purchase and refund must
    not alter what is returned.
    """
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    ref = f"did:{purchase_id}"
    async with factory() as session:
        original = (
            await session.execute(
                select(BillingWalletTransaction).where(BillingWalletTransaction.reference_id == ref)
            )
        ).scalar_one_or_none()
        if original is None:
            logger.warning("[WALLET] refund skipped: no debit found for %s", ref)
            return {"ok": False, "reason": "no_original_debit"}

        refund_ref = f"did_refund:{purchase_id}"
        dup = (
            await session.execute(
                select(BillingWalletTransaction).where(
                    BillingWalletTransaction.reference_id == refund_ref
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            return {"ok": True, "duplicate": True}

        # Reverse the signs of whatever was actually debited.
        back_cents = abs(int(original.amount_cents or 0))
        back_paise = abs(int(original.amount_inr_paise or 0))
        wallet = await session.get(BillingWallet, tenant_id)
        if wallet is None:
            wallet = BillingWallet(
                tenant_id=tenant_id, balance_cents=0, balance_inr_paise=0, updated_at=_utcnow()
            )
            session.add(wallet)
            await session.flush()
        wallet.balance_cents = int(wallet.balance_cents or 0) + back_cents
        wallet.balance_inr_paise = int(wallet.balance_inr_paise or 0) + back_paise
        wallet.updated_at = _utcnow()
        session.add(
            BillingWalletTransaction(
                tenant_id=tenant_id,
                user_id=user_id or original.user_id,
                amount_cents=back_cents,
                amount_inr_paise=back_paise,
                kind="did_refund",
                reference_id=refund_ref,
                created_at=_utcnow(),
            )
        )
        await session.commit()
    logger.info(
        "[WALLET] refunded did purchase=%s cents=%s paise=%s",
        purchase_id,
        back_cents,
        back_paise,
    )
    return {"ok": True, "amountCents": back_cents, "amountInrPaise": back_paise}


async def create_topup_checkout(tenant_id: uuid.UUID, amount_usd: float, email: str) -> dict:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise ValueError("stripe_not_configured")
    if amount_usd < settings.topup_min_usd or amount_usd > settings.topup_max_usd:
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
    await credit_wallet(
        tenant_id,
        amount_cents=amount_cents,
        kind="topup",
        reference_id=f"stripe:{session_id}",
        stripe_session_id=session_id,
    )
