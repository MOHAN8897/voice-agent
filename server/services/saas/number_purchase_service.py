"""Stripe checkout + number reservations (PRD-04)."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import NumberPurchase, NumberReservation, ProvisionJob
from server.services.saas.tenant_guard import SubscriberPrincipal, subscriber_workspace_tenant_id

logger = logging.getLogger(__name__)

#: Strict E.164: '+', then 8-15 digits, first digit 1-9 (never 0).
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_assign_agent_id(raw: str | None) -> uuid.UUID | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ValueError("invalid_agent")


async def _tenant_agent_id(session, tenant_id: uuid.UUID, agent_id: uuid.UUID | None) -> uuid.UUID | None:
    if agent_id is None:
        return None
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.tenant_id != tenant_id:
        raise ValueError("invalid_agent")
    return agent.agent_id


async def _active_reservation_conflict(e164: str) -> bool:
    factory = get_session_factory()
    if factory is None:
        return False
    async with factory() as session:
        result = await session.execute(
            select(NumberReservation).where(
                NumberReservation.e164 == e164,
                NumberReservation.expires_at > _utcnow(),
            )
        )
        return result.scalar_one_or_none() is not None


async def create_purchase_checkout(
    principal: SubscriberPrincipal,
    *,
    e164: str,
    country_code: str = "IN",
    assign_agent_id: str | None = None,
) -> dict:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise ValueError("stripe_not_configured")
    from server.db.models.saas_models import User

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    e164 = normalize_e164(e164)
    if await _active_reservation_conflict(e164):
        raise ValueError("number_reserved")
    async with factory() as session:
        owned = await session.execute(select(PhoneNumber).where(PhoneNumber.e164 == e164))
        if owned.scalar_one_or_none():
            raise ValueError("number_unavailable")
        user = await session.get(User, principal.user_id)
        if user and user.email_verified_at is None and settings.saas_require_email_verification_for_buy:
            raise ValueError("verification_required")
        workspace_tid = subscriber_workspace_tenant_id(principal)
        bind_agent = await _tenant_agent_id(session, workspace_tid, parse_assign_agent_id(assign_agent_id))
        purchase = NumberPurchase(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            e164=e164,
            country_code=country_code,
            status="checkout_created",
            assign_agent_id=bind_agent,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(purchase)
        await session.flush()
        ttl = settings.number_reservation_ttl_minutes
        session.add(
            NumberReservation(
                e164=e164,
                tenant_id=principal.tenant_id,
                purchase_id=purchase.id,
                expires_at=_utcnow() + timedelta(minutes=ttl),
                created_at=_utcnow(),
            )
        )
        tenant = await session.get(Tenant, principal.tenant_id)
        import stripe

        stripe.api_key = settings.stripe_secret_key
        customer_id = tenant.stripe_customer_id if tenant else None
        if not customer_id:
            cust = stripe.Customer.create(
                email=principal.email,
                metadata={"tenant_id": str(principal.tenant_id)},
            )
            customer_id = cust.id
            if tenant:
                tenant.stripe_customer_id = customer_id
        session_params: dict = {
            "mode": "payment",
            "customer": customer_id,
            "success_url": settings.stripe_checkout_success_url,
            "cancel_url": settings.stripe_checkout_cancel_url,
            "metadata": {
                "purchase_id": str(purchase.id),
                "tenant_id": str(principal.tenant_id),
                "e164": e164,
                "user_id": str(principal.user_id),
            },
            "line_items": [
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Phone {e164} (monthly)"},
                    # Same price the wallet path charges, from one place.
                    "unit_amount": int(settings.did_monthly_usd_cents),
                },
                "quantity": 1,
            }
        ],
        }
        checkout = stripe.checkout.Session.create(**session_params)
        purchase.stripe_checkout_session_id = checkout.id
        purchase.status = "payment_pending"
        await session.commit()
        return {
            "purchaseId": str(purchase.id),
            "checkoutUrl": checkout.url,
            "status": purchase.status,
        }


async def get_purchase(purchase_id: uuid.UUID, tenant_id: uuid.UUID) -> dict | None:
    factory = get_session_factory()
    if factory is None:
        return None
    async with factory() as session:
        row = await session.get(NumberPurchase, purchase_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        # The provision job's error is the only explanation a user gets for a
        # failed purchase — surface it rather than a bare "failed".
        job = (
            await session.execute(
                select(ProvisionJob).where(ProvisionJob.purchase_id == row.id)
            )
        ).scalar_one_or_none()
        last_error = job.last_error if job is not None and job.last_error else None
        return {
            "purchaseId": str(row.id),
            "e164": row.e164,
            "status": row.status,
            "phoneNumberId": str(row.phone_number_id) if row.phone_number_id else None,
            "assignAgentId": str(row.assign_agent_id) if row.assign_agent_id else None,
            "lastError": last_error,
        }


def normalize_e164(raw: str) -> str:
    """Validate and normalise a phone number to strict E.164.

    A number is charged for and handed to the carrier, so the shape must be right
    before any money moves. Accepts the loose forms a human types ("+1 415 555 2671",
    "0044 …", bare 10-digit) and returns strict E.164, or raises ``invalid_e164``.
    """
    value = (raw or "").strip()
    if not value:
        raise ValueError("invalid_e164")
    if value.startswith("00"):
        value = f"+{value[2:]}"
    if value.startswith("+"):
        candidate = "+" + re.sub(r"\D", "", value[1:])
    else:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 10:
            candidate = f"+91{digits}"
        else:
            candidate = f"+{digits}"
    # E.164: a leading '+', a country code that does not start with 0, and 8-15
    # digits in total. "+0123…" and "+1234567" are both rejected.
    if not E164_RE.match(candidate):
        raise ValueError("invalid_e164")
    return candidate


async def assert_carrier_can_buy(e164: str) -> None:
    """The account DID must be ordered from Telnyx in the same breath.

    Without this, a workspace whose Telnyx balance is empty has its wallet debited,
    sees a "paid" purchase, and only discovers the carrier refused when the
    provision job fails — then gets an async refund. Checking first turns that
    into an honest, synchronous failure before any money moves.
    """
    from server.services.telnyx_client import TelnyxClient

    try:
        balance = await TelnyxClient().get_balance()
    except Exception as exc:
        # Carrier unreachable is not proof of no balance — let the purchase through
        # and let provisioning decide, rather than blocking every buyer on a
        # transient API error.
        logger.warning("telnyx balance check failed, allowing purchase: %s", exc)
        return
    remaining = _carrier_remaining(balance)
    # Telnyx returns balance as a string ("0.56"); treat low prepaid credit as
    # exhausted before we debit a customer and place an order that will 402.
    if remaining is not None and remaining < CARRIER_MIN_BALANCE_USD:
        logger.warning(
            "telnyx balance too low for DID order e164=%s remaining=%s",
            e164,
            remaining,
        )
        raise ValueError("carrier_balance_exhausted")


#: Typical local DID order needs ~$1 prepaid; $0.56 still 402s at Telnyx.
CARRIER_MIN_BALANCE_USD = 1.0


def _carrier_remaining(balance: dict) -> float | None:
    """Remaining prepaid balance, or None when the carrier did not report one."""
    if not isinstance(balance, dict):
        return None
    data = balance.get("data")
    record = data if isinstance(data, dict) else balance
    for key in ("available_credit", "balance", "available_balance", "amount"):
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip().replace(",", ""))
            except ValueError:
                continue
    return None


async def _purchase_from_inventory(
    principal: SubscriberPrincipal,
    *,
    e164: str,
    country_code: str,
    assign_agent_id: str | None,
) -> dict | None:
    """Transfer an admin-pool DID to the buyer. Returns None if not in inventory."""
    from server.services.saas.billing_wallet_service import debit_did_purchase
    from server.services.saas.billing_rates import rates_with_derived_inr
    from server.services.saas.number_inventory import (
        ensure_platform_inventory_tenant,
        get_inventory_number,
    )

    inv = await get_inventory_number(e164)
    if inv is None:
        return None
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    inventory_tid = await ensure_platform_inventory_tenant()

    async with factory() as session:
        pn = await session.get(PhoneNumber, inv.id)
        if pn is None or pn.tenant_id != inventory_tid or pn.released_at is not None:
            return None
        bind_agent = await _tenant_agent_id(
            session, workspace_tid, parse_assign_agent_id(assign_agent_id)
        )
        purchase = NumberPurchase(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            e164=e164,
            country_code=country_code,
            status="paid",
            assign_agent_id=bind_agent,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(purchase)
        await session.flush()
        purchase_id = purchase.id
        # Hold the inventory row so a concurrent buyer cannot take it.
        pn.tenant_id = workspace_tid
        pn.status = "active"
        pn.billing_source = "wallet"
        pn.agent_id = bind_agent
        pn.purchase_id = purchase_id
        pn.inbound_enabled = True
        pn.outbound_enabled = True
        await session.commit()
        phone_number_id = pn.id
        telnyx_number_id = pn.telnyx_number_id

    try:
        await debit_did_purchase(
            principal.tenant_id,
            user_id=principal.user_id,
            e164=e164,
            purchase_id=purchase_id,
        )
    except Exception:
        # Roll ownership back to inventory if the wallet debit fails.
        async with factory() as session:
            pn = await session.get(PhoneNumber, phone_number_id)
            row = await session.get(NumberPurchase, purchase_id)
            if pn is not None:
                pn.tenant_id = inventory_tid
                pn.status = "available"
                pn.billing_source = "inventory"
                pn.agent_id = None
                pn.purchase_id = None
                pn.inbound_enabled = False
                pn.outbound_enabled = False
            if row is not None:
                row.status = "failed"
                row.updated_at = _utcnow()
            await session.commit()
        raise

    async with factory() as session:
        row = await session.get(NumberPurchase, purchase_id)
        if row is not None:
            row.status = "provisioned"
            row.updated_at = _utcnow()
            await session.commit()

    rates = rates_with_derived_inr()
    return {
        "purchaseId": str(purchase_id),
        "e164": e164,
        "status": "provisioned",
        "provisioning": False,
        "payment": "wallet",
        "phoneNumberId": str(phone_number_id),
        "id": str(phone_number_id),
        "telnyxNumberId": telnyx_number_id,
        "source": "inventory",
        "didMonthlyUsd": round(rates["did_monthly_usd_cents"] / 100.0, 2),
        "didMonthlyInr": round(rates["did_monthly_inr_paise"] / 100.0, 2),
    }


async def purchase_with_wallet(
    principal: SubscriberPrincipal,
    *,
    e164: str,
    country_code: str = "IN",
    assign_agent_id: str | None = None,
) -> dict:
    """Reserve → debit wallet → enqueue Telnyx provision (prepaid DID).

    Prefer admin inventory transfer (no carrier order) when the DID already sits
    in the Platform inventory pool.
    """
    from server.db.models.saas_models import User
    from server.services.saas.billing_wallet_service import (
        assert_wallet_can_afford_did,
        debit_did_purchase,
    )
    from server.services.saas.number_inventory import ensure_platform_inventory_tenant
    from server.services.saas.provision_worker import enqueue_provision

    settings = get_settings()
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    e164 = normalize_e164(e164)
    if await _active_reservation_conflict(e164):
        raise ValueError("number_reserved")

    # Customer wallet first — same gate for inventory transfer and Telnyx order.
    await assert_wallet_can_afford_did(principal.tenant_id)

    transferred = await _purchase_from_inventory(
        principal,
        e164=e164,
        country_code=country_code,
        assign_agent_id=assign_agent_id,
    )
    if transferred is not None:
        return transferred

    # Platform Telnyx prepaid next: never debit a buyer for a DID we cannot order.
    await assert_carrier_can_buy(e164)
    inventory_tid = await ensure_platform_inventory_tenant()
    async with factory() as session:
        owned = (
            await session.execute(
                select(PhoneNumber).where(PhoneNumber.e164 == e164, PhoneNumber.released_at.is_(None))
            )
        ).scalar_one_or_none()
        # Already on another tenant (not inventory) → unavailable.
        if owned is not None and owned.tenant_id != inventory_tid:
            raise ValueError("number_unavailable")
        user = await session.get(User, principal.user_id)
        if user and user.email_verified_at is None and settings.saas_require_email_verification_for_buy:
            raise ValueError("verification_required")
        tenant = await session.get(Tenant, principal.tenant_id)
        limits = (tenant.limits or {}) if tenant else {}
        max_numbers = int(limits.get("max_numbers") or 20)
        workspace_tid = subscriber_workspace_tenant_id(principal)
        active = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == workspace_tid,
                PhoneNumber.released_at.is_(None),
            )
        )
        if len(list(active.scalars())) >= max_numbers:
            raise ValueError("number_limit")
        bind_agent = await _tenant_agent_id(session, workspace_tid, parse_assign_agent_id(assign_agent_id))
        purchase = NumberPurchase(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            e164=e164,
            country_code=country_code,
            status="paid",
            assign_agent_id=bind_agent,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(purchase)
        await session.flush()
        ttl = settings.number_reservation_ttl_minutes
        # Expiry is enforced by a partial-free unique index on e164, so stale rows
        # have to go or they would block this number permanently.
        await session.execute(
            delete(NumberReservation).where(
                NumberReservation.e164 == e164,
                NumberReservation.expires_at <= _utcnow(),
            )
        )
        session.add(
            NumberReservation(
                e164=e164,
                tenant_id=principal.tenant_id,
                purchase_id=purchase.id,
                expires_at=_utcnow() + timedelta(minutes=ttl),
                created_at=_utcnow(),
            )
        )
        purchase_id = purchase.id
        try:
            await session.commit()
        except IntegrityError:
            # Lost the race to a concurrent buyer of the same number.
            await session.rollback()
            raise ValueError("number_reserved") from None

    # The DID is bound to the agent only once the carrier actually provisions it —
    # process_one_job owns that write, so a failed purchase never leaves an
    # agent pointing at a number nobody owns.
    try:
        await debit_did_purchase(
            principal.tenant_id,
            user_id=principal.user_id,
            e164=e164,
            purchase_id=purchase_id,
        )
    except Exception:
        async with factory() as session:
            row = await session.get(NumberPurchase, purchase_id)
            if row:
                row.status = "failed"
                row.updated_at = _utcnow()
            await session.execute(
                delete(NumberReservation).where(NumberReservation.purchase_id == purchase_id)
            )
            await session.commit()
        raise
    await enqueue_provision(purchase_id)
    # The admin-configured rate, not the env default, so the quoted price and the
    # charged price are the same number.
    from server.services.saas.billing_rates import rates_with_derived_inr

    rates = rates_with_derived_inr()
    return {
        "purchaseId": str(purchase_id),
        "e164": e164,
        # Provisioning is async — the carrier order can still fail. Saying "paid"
        # here is accurate; the console polls /telephony/purchases/{id} for the
        # terminal status rather than claiming the number already exists.
        "status": "paid",
        "provisioning": True,
        "payment": "wallet",
        "didMonthlyUsd": round(rates["did_monthly_usd_cents"] / 100.0, 2),
        "didMonthlyInr": round(rates["did_monthly_inr_paise"] / 100.0, 2),
    }
