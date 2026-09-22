"""Stripe webhooks — enqueue provision jobs (PRD-04)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from server.config.env import get_settings
from server.db.connection import get_session_factory
from sqlalchemy import update

from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import NumberPurchase, StripeWebhookEvent
from server.services.saas.provision_worker import enqueue_provision

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    settings = get_settings()
    if not settings.stripe_webhook_secret or not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    import stripe

    stripe.api_key = settings.stripe_secret_key
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except Exception as e:
        logger.warning("stripe webhook verify failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")

    async with factory() as session:
        existing = await session.get(StripeWebhookEvent, event["id"])
        if existing:
            return {"ok": True, "duplicate": True}
        session.add(
            StripeWebhookEvent(
                event_id=event["id"],
                type=event["type"],
                processed_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    if event["type"] == "customer.subscription.deleted":
        sub_id = event["data"]["object"].get("id")
        if sub_id:
            async with factory() as session:
                await session.execute(
                    update(PhoneNumber)
                    .where(PhoneNumber.stripe_subscription_id == sub_id)
                    .values(inbound_enabled=False, outbound_enabled=False, status="suspended")
                )
                await session.commit()

    if event["type"] == "invoice.payment_failed":
        sub_id = event["data"]["object"].get("subscription")
        if sub_id:
            async with factory() as session:
                await session.execute(
                    update(PhoneNumber)
                    .where(PhoneNumber.stripe_subscription_id == sub_id)
                    .values(inbound_enabled=False, outbound_enabled=False, status="payment_failed")
                )
                await session.commit()

    if event["type"] == "checkout.session.completed":
        import uuid

        from server.services.saas.billing_wallet_service import credit_topup_from_session

        session_obj = event["data"]["object"]
        meta = session_obj.get("metadata") or {}
        if meta.get("type") == "wallet_topup":
            tid = uuid.UUID(meta["tenant_id"])
            cents = int(meta.get("amount_cents") or 0)
            if cents > 0:
                await credit_topup_from_session(tid, session_obj["id"], cents)
        purchase_id = meta.get("purchase_id")
        if purchase_id:
            async with factory() as session:
                purchase = await session.get(NumberPurchase, uuid.UUID(purchase_id))
                if purchase:
                    purchase.status = "paid"
                    purchase.stripe_payment_intent_id = session_obj.get("payment_intent")
                    await session.commit()
            await enqueue_provision(uuid.UUID(purchase_id))

    return {"ok": True}
