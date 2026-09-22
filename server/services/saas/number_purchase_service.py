"""Stripe checkout + number reservations (PRD-04)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import NumberPurchase, NumberReservation, ProvisionJob
from server.services.saas.tenant_guard import SubscriberPrincipal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
) -> dict:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise ValueError("stripe_not_configured")
    from server.db.models.saas_models import User

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("database_required")
    e164 = e164.strip()
    if await _active_reservation_conflict(e164):
        raise ValueError("number_reserved")
    async with factory() as session:
        owned = await session.execute(select(PhoneNumber).where(PhoneNumber.e164 == e164))
        if owned.scalar_one_or_none():
            raise ValueError("number_unavailable")
        user = await session.get(User, principal.user_id)
        if user and user.email_verified_at is None and settings.saas_require_email_verification_for_buy:
            raise ValueError("verification_required")
        purchase = NumberPurchase(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            e164=e164,
            country_code=country_code,
            status="checkout_created",
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
            "line_items": [{"price_data": {"currency": "usd", "product_data": {"name": f"Phone {e164}"}, "unit_amount": 500}, "quantity": 1}],
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
        return {
            "purchaseId": str(row.id),
            "e164": row.e164,
            "status": row.status,
            "phoneNumberId": str(row.phone_number_id) if row.phone_number_id else None,
        }
