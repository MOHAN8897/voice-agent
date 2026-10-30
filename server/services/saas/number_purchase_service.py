"""Stripe checkout + number reservations (PRD-04)."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select
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


async def _assert_number_purchase_eligibility(
    session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    workspace_tenant_id: uuid.UUID,
    settings,
) -> None:
    """Apply the same verified-email and serialized number-cap checks to every buy path."""
    from server.db.models.saas_models import User

    user = await session.get(User, user_id)
    if settings.saas_require_email_verification_for_buy and (
        user is None or user.email_verified_at is None
    ):
        raise ValueError("verification_required")

    # Lock the tenant row while counting. Concurrent buys for different DIDs then
    # serialize here, so they cannot both pass the same last available slot.
    tenant = await session.get(Tenant, tenant_id, with_for_update=True)
    if tenant is None:
        raise ValueError("tenant_not_found")
    limits = tenant.limits if isinstance(tenant.limits, dict) else {}
    raw_limit = limits.get("max_numbers")
    try:
        max_numbers = int(raw_limit) if raw_limit is not None else 20
    except (TypeError, ValueError):
        max_numbers = 0
    max_numbers = max(0, max_numbers)
    active_count = await session.scalar(
        select(func.count(PhoneNumber.id)).where(
            PhoneNumber.tenant_id == workspace_tenant_id,
            PhoneNumber.released_at.is_(None),
        )
    )
    pending_count = await session.scalar(
        select(func.count(NumberPurchase.id)).where(
            NumberPurchase.tenant_id == tenant_id,
            NumberPurchase.status.in_(("paid", "provisioning", "needs_attention")),
            NumberPurchase.phone_number_id.is_(None),
        )
    )
    # A carrier purchase is charged and queued before a PhoneNumber row exists.
    # Count those durable pending purchases too, or a tenant can exceed its cap
    # by submitting requests while the carrier worker is still provisioning.
    if int(active_count or 0) + int(pending_count or 0) >= max_numbers:
        raise ValueError("number_limit")


#: Purchase states that have taken money and may still become a carrier order.
IN_FLIGHT_PURCHASE_STATUSES = ("paid", "provisioning", "needs_attention")


async def _active_reservation_conflict(e164: str) -> dict | None:
    """Who currently holds ``e164``: a live reservation or an in-flight purchase.

    Returns ``{"tenant_id", "purchase_id", "status"}`` or None. The purchase table
    is checked as well as the reservation table so a hold that was removed while
    its purchase was still in flight can never let a second tenant buy the DID.
    """
    factory = get_session_factory()
    if factory is None:
        return None
    async with factory() as session:
        row = (
            await session.execute(
                select(
                    NumberReservation.tenant_id,
                    NumberReservation.purchase_id,
                    NumberPurchase.status,
                )
                .join(NumberPurchase, NumberPurchase.id == NumberReservation.purchase_id, isouter=True)
                .where(
                    NumberReservation.e164 == e164,
                    or_(
                        NumberReservation.expires_at > _utcnow(),
                        NumberPurchase.status.in_(IN_FLIGHT_PURCHASE_STATUSES),
                    ),
                )
                .limit(1)
            )
        ).first()
        if row is None:
            row = (
                await session.execute(
                    select(NumberPurchase.tenant_id, NumberPurchase.id, NumberPurchase.status)
                    .where(
                        NumberPurchase.e164 == e164,
                        NumberPurchase.status.in_(IN_FLIGHT_PURCHASE_STATUSES),
                    )
                    .order_by(NumberPurchase.created_at.desc())
                    .limit(1)
                )
            ).first()
        if row is None:
            return None
        return {"tenant_id": row[0], "purchase_id": row[1], "status": row[2]}


def rent_terms(rates: dict, *, charge: dict | None = None, purchased_at: datetime | None = None) -> dict:
    """Monthly rent quoted back to the buyer.

    ``didMonthly*`` is the admin "Phone number monthly rent" now in force (what the
    next renewal costs unless the admin changes it before then). ``charged*`` is
    what this purchase actually debited for the first month, with its rate version.
    """
    out = {
        "didMonthlyUsd": round(int(rates["did_monthly_usd_cents"]) / 100.0, 2),
        "didMonthlyInr": round(int(rates["did_monthly_inr_paise"]) / 100.0, 2),
    }
    if charge is not None:
        out["chargedUsd"] = round(int(charge.get("amountCents") or 0) / 100.0, 2)
        out["chargedInr"] = round(int(charge.get("amountInrPaise") or 0) / 100.0, 2)
        out["rateVersion"] = charge.get("rateVersion")
    if purchased_at is not None:
        from server.services.saas.number_rental import next_renewal_at

        out["renewsOn"] = next_renewal_at(purchased_at, purchased_at).isoformat()
    return out


async def _replay_if_same_tenant(conflict, principal: SubscriberPrincipal, e164: str) -> dict | None:
    """Idempotent replay: a double-click or client retry gets the original purchase.

    Only the same tenant's in-flight purchase is replayed; nothing is debited again.
    Anyone else's hold is a conflict.
    """
    if not isinstance(conflict, dict):
        return None
    if conflict.get("tenant_id") != principal.tenant_id or not conflict.get("purchase_id"):
        return None
    if conflict.get("status") not in IN_FLIGHT_PURCHASE_STATUSES:
        return None
    from server.services.saas.billing_rates import load_current_rates

    rates = await load_current_rates()
    return {
        "purchaseId": str(conflict["purchase_id"]),
        "e164": e164,
        "status": conflict["status"],
        "provisioning": True,
        "payment": "wallet",
        "replayed": True,
        **rent_terms(rates),
    }


def _money_minor_units(value) -> int | None:
    """Carrier fee (major units, number or numeric string) in minor units."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(round(float(str(value).strip().replace(",", "")) * 100))
    except (TypeError, ValueError):
        return None


def carrier_charge_exceeds_retail(row: dict, rates: dict) -> bool:
    """True when the carrier's first charge for this DID exceeds what we collect.

    Vobiz debits ``setup_fee + monthly_fee`` from the parent account at purchase,
    while the tenant pays one month of the platform's flat retail rate. A premium
    or vanity number whose carrier price is above that rate would be sold at a
    loss, so it is neither listed nor sold. Unknown currency or fees are allowed
    (the configured carrier-balance gate still applies).
    """
    if not isinstance(row, dict):
        return False
    setup = _money_minor_units(row.get("setup_fee")) or 0
    monthly = _money_minor_units(row.get("monthly_fee"))
    if monthly is None and not setup:
        return False
    carrier_minor = setup + (monthly or 0)
    currency = str(row.get("currency") or "").strip().upper()
    if currency == "INR":
        return carrier_minor > int(rates.get("did_monthly_inr_paise") or 0)
    if currency == "USD":
        return carrier_minor > int(rates.get("did_monthly_usd_cents") or 0)
    return False


async def create_purchase_checkout(
    principal: SubscriberPrincipal,
    *,
    e164: str,
    country_code: str = "IN",
    assign_agent_id: str | None = None,
) -> dict:
    """Card checkout via Stripe has been permanently removed. Use purchase_with_wallet instead."""
    raise ValueError("stripe_removed")


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
        raw_error = job.last_error if job is not None and isinstance(job.last_error, dict) else None
        # Only the stable code reaches the browser; exception class names and
        # provider details stay in the operator log.
        last_error = (
            {"code": str(raw_error.get("code") or raw_error.get("message") or "provision_failed")}
            if raw_error
            else None
        )
        refunded = None
        if row.status == "failed":
            from server.db.models.saas_models import BillingWalletTransaction

            refunded = (
                await session.execute(
                    select(BillingWalletTransaction.id).where(
                        BillingWalletTransaction.tenant_id == row.tenant_id,
                        BillingWalletTransaction.reference_id == f"did_refund:{row.id}",
                    ).limit(1)
                )
            ).first() is not None
        return {
            "purchaseId": str(row.id),
            "e164": row.e164,
            "status": row.status,
            "phoneNumberId": str(row.phone_number_id) if row.phone_number_id else None,
            "assignAgentId": str(row.assign_agent_id) if row.assign_agent_id else None,
            "lastError": last_error,
            "refunded": refunded,
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
    from server.services.telephony import active_telephony_provider, provider_configured

    provider = active_telephony_provider()
    if provider == "vobiz":
        if not provider_configured("vobiz"):
            raise ValueError("carrier_not_configured")
        from server.services.vobiz_client import VobizClient
        try:
            balance = await VobizClient().get_balance()
        except Exception as exc:
            logger.warning(
                "vobiz balance check failed, allowing purchase error_type=%s",
                type(exc).__name__,
            )
            return
        remaining = _carrier_remaining(balance)
        curr = str(balance.get("currency") or "INR").upper()
        if remaining is not None:
            if curr == "INR":
                from server.services.usage_pricing import resolve_fx_rate_inr
                fx = float(resolve_fx_rate_inr().get("rate") or 96.78)
                min_bal = CARRIER_MIN_BALANCE_USD * fx
            else:
                min_bal = CARRIER_MIN_BALANCE_USD
            if remaining < min_bal:
                logger.warning(
                    "vobiz balance too low for DID order remaining=%s %s",
                    remaining,
                    curr,
                )
                raise ValueError("carrier_balance_exhausted")
        return

    from server.services.telnyx_client import TelnyxClient

    try:
        balance = await TelnyxClient().get_balance()
    except Exception as exc:
        # Carrier unreachable is not proof of no balance — let the purchase through
        # and let provisioning decide, rather than blocking every buyer on a
        # transient API error.
        logger.warning(
            "telnyx balance check failed, allowing purchase error_type=%s",
            type(exc).__name__,
        )
        return
    remaining = _carrier_remaining(balance)
    # Telnyx returns balance as a string ("0.56"); treat low prepaid credit as
    # exhausted before we debit a customer and place an order that will 402.
    if remaining is not None and remaining < CARRIER_MIN_BALANCE_USD:
        logger.warning(
            "telnyx balance too low for DID order remaining=%s",
            remaining,
        )
        raise ValueError("carrier_balance_exhausted")


async def _assert_vobiz_inventory_number_available(e164: str, country_code: str) -> None:
    """Require a fresh match from Vobiz's unassigned inventory before wallet debit."""
    from server.services.vobiz_client import VobizClient, VobizConfigError

    try:
        rows = await VobizClient().search_available_numbers(country=country_code, limit=100)
    except VobizConfigError as exc:
        raise ValueError("carrier_not_configured") from exc
    except Exception as exc:
        logger.warning(
            "vobiz number availability check failed error_type=%s",
            type(exc).__name__,
        )
        raise ValueError("carrier_inventory_unavailable") from exc
    match = next((row for row in rows if str(row.get("e164") or "") == e164), None)
    if match is None:
        raise ValueError("number_unavailable")
    from server.services.saas.billing_rates import load_current_rates

    if carrier_charge_exceeds_retail(match, await load_current_rates()):
        logger.warning("vobiz inventory number priced above retail; refusing sale")
        raise ValueError("number_unavailable")


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
    from server.services.saas.billing_wallet_service import debit_did_purchase_in_session
    from server.services.saas.billing_rates import load_current_rates
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
        await _assert_number_purchase_eligibility(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            workspace_tenant_id=workspace_tid,
            settings=get_settings(),
        )
        pn = await session.get(PhoneNumber, inv.id, with_for_update=True)
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
            status="provisioned",
            provider="telnyx",
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
        charge = await debit_did_purchase_in_session(
            session,
            principal.tenant_id,
            user_id=principal.user_id,
            purchase_id=purchase_id,
        )
        purchased_at = purchase.created_at
        phone_number_id = pn.id
        telnyx_number_id = pn.telnyx_number_id
        await session.commit()

    rates = await load_current_rates()
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
        **rent_terms(rates, charge=charge, purchased_at=purchased_at),
    }


async def purchase_with_wallet(
    principal: SubscriberPrincipal,
    *,
    e164: str,
    country_code: str = "IN",
    assign_agent_id: str | None = None,
) -> dict:
    """Validate provider inventory → reserve/debit → enqueue provider purchase.

    Telnyx may transfer an already-owned platform inventory DID. Vobiz numbers
    must be present in the provider's live, unassigned inventory and are purchased
    through its inventory API.
    """
    from server.services.saas.billing_wallet_service import (
        assert_wallet_can_afford_did,
        debit_did_purchase_in_session,
    )
    from server.services.saas.number_inventory import ensure_platform_inventory_tenant

    settings = get_settings()
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    e164 = normalize_e164(e164)
    conflict = await _active_reservation_conflict(e164)
    if conflict:
        replay = await _replay_if_same_tenant(conflict, principal, e164)
        if replay is not None:
            return replay
        raise ValueError("number_reserved")

    # Customer wallet first — same gate for inventory transfer and Telnyx order.
    await assert_wallet_can_afford_did(principal.tenant_id)

    from server.services.telephony import active_telephony_provider

    active_provider = active_telephony_provider()
    if active_provider == "vobiz":
        from server.services.saas.voice_kyc_service import assert_voice_kyc_approved

        await assert_voice_kyc_approved(principal.tenant_id, action="buy a phone number")
        # The account-owned-number endpoint is not an availability check. Only
        # an exact match in unassigned provider inventory can proceed to debit.
        await _assert_vobiz_inventory_number_available(e164, country_code)
    else:
        transferred = await _purchase_from_inventory(
            principal,
            e164=e164,
            country_code=country_code,
            assign_agent_id=assign_agent_id,
        )
        if transferred is not None:
            return transferred

    # Never debit a buyer for a DID the active provider cannot order.
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
        workspace_tid = subscriber_workspace_tenant_id(principal)
        await _assert_number_purchase_eligibility(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            workspace_tenant_id=workspace_tid,
            settings=settings,
        )
        bind_agent = await _tenant_agent_id(session, workspace_tid, parse_assign_agent_id(assign_agent_id))
        purchase = NumberPurchase(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            e164=e164,
            country_code=country_code,
            status="paid",
            provider=active_provider,
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
                NumberReservation.purchase_id.in_(select(NumberPurchase.id).where(
                    NumberPurchase.status.in_(["failed", "expired", "cancelled"]),
                )),
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
        session.add(
            ProvisionJob(
                purchase_id=purchase_id,
                status="queued",
                attempts=0,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        charge = await debit_did_purchase_in_session(
            session,
            principal.tenant_id,
            user_id=principal.user_id,
            purchase_id=purchase_id,
        )
        purchased_at = purchase.created_at
        lost_race = False
        try:
            await session.commit()
        except IntegrityError:
            # Lost the race to a concurrent buyer of the same number. Nothing was
            # committed, so the debit rolled back with the reservation.
            await session.rollback()
            lost_race = True
    if lost_race:
        # A concurrent double-submit by this same tenant won the race: return
        # that purchase rather than an error for a number the user now owns.
        replay = await _replay_if_same_tenant(
            await _active_reservation_conflict(e164), principal, e164
        )
        if replay is not None:
            return replay
        raise ValueError("number_reserved")

    # The reservation, purchase, wallet debit, transaction and durable provision
    # job were committed together. The worker can now claim the queued row.
    # The admin-configured rate, not the env default, so the quoted price and the
    # charged price are the same number.
    from server.services.saas.billing_rates import load_current_rates

    rates = await load_current_rates()
    return {
        "purchaseId": str(purchase_id),
        "e164": e164,
        # Provisioning is async — the carrier order can still fail. Saying "paid"
        # here is accurate; the console polls /telephony/purchases/{id} for the
        # terminal status rather than claiming the number already exists.
        "status": "paid",
        "provisioning": True,
        "payment": "wallet",
        **rent_terms(rates, charge=charge, purchased_at=purchased_at),
    }
