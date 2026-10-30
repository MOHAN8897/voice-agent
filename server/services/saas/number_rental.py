"""Monthly phone-number rental renewal.

The first month is charged at purchase (``did:{purchase_id}``). Each later month
is charged to the same wallet on the purchase anniversary with an idempotent
ledger reference ``did_rent:{phone_number_id}:{period}``, so concurrent workers
or restarts can never double-charge a period.

Insufficient balance does not release the number — the DID is only suspended
(no inbound or outbound calls) until the wallet can pay the period, at which
point the next run charges it and restores service. Releasing a suspended DID is
an operator decision: Vobiz charges a release fee and the number cannot be
recovered after the release cool-down.

Only the period that is due *now* is charged. Periods missed while the worker was
down are not back-billed, so turning this on never produces a surprise bulk debit.
"""
from __future__ import annotations

import calendar
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import BillingWalletTransaction, NumberPurchase

logger = logging.getLogger(__name__)

RENTAL_KIND = "did_rental"
SUSPENDED_STATUS = "suspended_unpaid"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def add_months(anchor: datetime, months: int) -> datetime:
    """Same day-of-month ``months`` later, clamped to the month's last day."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


def due_period(anchor: datetime, now: datetime) -> int:
    """Index of the rental period running at ``now`` (0 = the purchase month)."""
    anchor, now = _aware(anchor), _aware(now)
    if now < anchor:
        return 0
    months = (now.year - anchor.year) * 12 + (now.month - anchor.month)
    while months > 0 and add_months(anchor, months) > now:
        months -= 1
    return max(0, months)


def rental_reference(phone_number_id: uuid.UUID, period: int) -> str:
    return f"did_rent:{phone_number_id}:{period}"


def renewal_enabled() -> bool:
    return os.getenv("DID_RENTAL_RENEWAL_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


async def renew_due_numbers(*, now: datetime | None = None, limit: int = 200) -> dict:
    """Charge every wallet-billed DID whose next month has started."""
    summary = {"charged": 0, "suspended": 0, "restored": 0, "skipped": 0}
    if not renewal_enabled():
        return summary
    factory = get_session_factory()
    if factory is None:
        return summary
    now = now or _utcnow()
    from server.services.saas.billing_rates import load_current_rates

    rates = await load_current_rates()
    want_cents = int(rates["did_monthly_usd_cents"])
    want_paise = int(rates["did_monthly_inr_paise"])
    async with factory() as session:
        rows = (
            await session.execute(
                select(
                    PhoneNumber.id,
                    PhoneNumber.status,
                    NumberPurchase.tenant_id,
                    NumberPurchase.user_id,
                    NumberPurchase.created_at,
                )
                .join(NumberPurchase, NumberPurchase.id == PhoneNumber.purchase_id)
                .where(
                    PhoneNumber.released_at.is_(None),
                    PhoneNumber.billing_source == "wallet",
                    PhoneNumber.status.in_(("active", SUSPENDED_STATUS)),
                )
                .order_by(PhoneNumber.created_at)
                .limit(limit)
            )
        ).all()

    from server.services.saas.billing_wallet_service import debit_wallet

    for number_id, status, payer_tenant_id, user_id, purchased_at in rows:
        if purchased_at is None:
            summary["skipped"] += 1
            continue
        period = due_period(purchased_at, now)
        if period < 1:
            continue
        ref = rental_reference(number_id, period)
        async with factory() as session:
            already_paid = (
                await session.execute(
                    select(BillingWalletTransaction.id)
                    .where(BillingWalletTransaction.reference_id == ref)
                    .limit(1)
                )
            ).first() is not None
        if not already_paid:
            try:
                await debit_wallet(
                    payer_tenant_id,
                    kind=RENTAL_KIND,
                    reference_id=ref,
                    user_id=user_id,
                    amount_cents=want_cents,
                    amount_inr_paise=want_paise,
                    allow_partial=False,
                )
                summary["charged"] += 1
            except HTTPException as exc:
                if exc.status_code != 402:
                    raise
                if status != SUSPENDED_STATUS:
                    await _set_suspended(number_id, payer_tenant_id, period, suspended=True)
                    summary["suspended"] += 1
                continue
        if status == SUSPENDED_STATUS:
            await _set_suspended(number_id, payer_tenant_id, period, suspended=False)
            summary["restored"] += 1
    return summary


async def _set_suspended(number_id: uuid.UUID, tenant_id: uuid.UUID, period: int, *, suspended: bool) -> None:
    factory = get_session_factory()
    async with factory() as session:
        pn = await session.get(PhoneNumber, number_id, with_for_update=True)
        if pn is None or pn.released_at is not None:
            return
        if suspended:
            if pn.status != "active":
                return
            pn.status = SUSPENDED_STATUS
            pn.inbound_enabled = False
            pn.outbound_enabled = False
        else:
            if pn.status != SUSPENDED_STATUS:
                return
            pn.status = "active"
            pn.inbound_enabled = True
            pn.outbound_enabled = True
        await session.commit()
    from server.services.saas.activity_log import record_event

    await record_event(
        action="number.rental.suspended" if suspended else "number.rental.restored",
        resource_type="phone_number",
        resource_id=str(number_id),
        actor="system",
        tenant_id=tenant_id,
        payload={"period": period, "reason": "insufficient_balance" if suspended else "rental_paid"},
        source="system",
        outcome="warning" if suspended else "success",
        severity="warning" if suspended else "info",
    )
