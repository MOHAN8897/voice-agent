"""Async Telnyx provision after Stripe payment."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from server.db.connection import get_session_factory
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import (
    NumberPurchase,
    NumberReservation,
    ProvisionJob,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue_provision(purchase_id: uuid.UUID) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        existing = await session.execute(
            select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id)
        )
        if existing.scalar_one_or_none():
            return
        session.add(
            ProvisionJob(
                purchase_id=purchase_id,
                status="queued",
                attempts=0,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        )
        await session.commit()


async def process_one_job() -> bool:
    """Returns True if a job was processed."""
    factory = get_session_factory()
    if factory is None:
        return False
    async with factory() as session:
        result = await session.execute(
            select(ProvisionJob).where(ProvisionJob.status == "queued").limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return False
        job.status = "running"
        job.attempts += 1
        job.updated_at = _utcnow()
        await session.commit()
        purchase_id = job.purchase_id

    async with factory() as session:
        purchase = await session.get(NumberPurchase, purchase_id)
        job = await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id))
        job_row = job.scalar_one()
        if purchase is None:
            job_row.status = "failed"
            job_row.last_error = {"message": "purchase_missing"}
            await session.commit()
            return True
        purchase.status = "provisioning"
        await session.commit()

    async with factory() as session:
        purchase = await session.get(NumberPurchase, purchase_id)
    if purchase is None:
        return True
    try:
        from server.services.telephony import active_telephony_provider
        provider = active_telephony_provider()
        if provider == "vobiz":
            from server.services.vobiz_client import VobizClient
            await VobizClient().provision_ordered_number(purchase.e164)
        else:
            from server.services.telnyx_client import TelnyxClient
            from server.services.telnyx_provisioning import provision_ordered_number

            client = TelnyxClient()
            await provision_ordered_number(client, purchase.e164)
    except Exception as e:
        logger.exception("provision failed purchase=%s", purchase_id)
        refund_tenant = None
        refund_user = None
        refund_wallet = False
        async with factory() as session:
            purchase = await session.get(NumberPurchase, purchase_id)
            job = (
                await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id))
            ).scalar_one()
            job.status = "failed"
            job.last_error = {"message": str(e)}
            if purchase:
                purchase.status = "failed"
                refund_tenant = purchase.tenant_id
                refund_user = purchase.user_id
                refund_wallet = not purchase.stripe_checkout_session_id
                # Release the hold. The number was never bought, so leaving a
                # reservation would make it look reserved by "another checkout"
                # for the rest of the TTL — and the unique index would block the
                # retry outright.
                await session.execute(
                    delete(NumberReservation).where(
                        NumberReservation.purchase_id == purchase_id
                    )
                )
            await session.commit()
        if refund_wallet and refund_tenant is not None:
            try:
                from server.services.saas.billing_wallet_service import refund_did_purchase

                await refund_did_purchase(
                    refund_tenant,
                    user_id=refund_user,
                    purchase_id=purchase_id,
                )
                refunded = True
            except Exception:
                logger.exception("did refund failed purchase=%s", purchase_id)
        # The single most important row in the log: money was taken and then
        # returned, or was taken and could not be returned. Either way the
        # operator has to be able to find it without reconstructing the job.
        from server.services.saas.activity_log import record_event

        await record_event(
            action="number.provision.failed",
            resource_type="number_purchase",
            resource_id=str(purchase_id),
            actor="system",
            tenant_id=refund_tenant,
            payload={
                "error": str(e)[:400],
                "refunded": refunded if refund_wallet else False,
                "refundAttempted": refund_wallet,
            },
            source="system",
            outcome="error",
            severity="error",
        )
        return True

    async with factory() as session:
        purchase = await session.get(NumberPurchase, purchase_id)
        job = (
            await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id))
        ).scalar_one()
        if purchase is None:
            return True
        phone_tenant_id = purchase.tenant_id
        if purchase.user_id:
            from server.db.models.saas_models import User
            from server.services.saas.dev_tester_workspace import workspace_tenant_id_for_subscriber

            user = await session.get(User, purchase.user_id)
            if user:
                phone_tenant_id = workspace_tenant_id_for_subscriber(purchase.tenant_id, user.email)
        pn = PhoneNumber(
            tenant_id=phone_tenant_id,
            e164=purchase.e164,
            status="active",
            purchase_id=purchase.id,
            billing_source="wallet" if not purchase.stripe_checkout_session_id else "stripe",
            inbound_enabled=True,
            outbound_enabled=True,
            agent_id=purchase.assign_agent_id,
            plivo_number_id=f"vobiz_{purchase.e164}" if provider == "vobiz" else None,
            telnyx_number_id=f"telnyx_{purchase.e164}" if provider == "telnyx" else None,
            created_at=_utcnow(),
        )
        session.add(pn)
        await session.flush()
        purchase.phone_number_id = pn.id
        purchase.status = "active"
        job.status = "done"
        job.updated_at = _utcnow()
        # The number is now owned, so the in-flight hold has done its job. Leaving
        # it would collide with the unique index on the next purchase of any
        # number, and read as a false "reserved by another checkout".
        await session.execute(
            delete(NumberReservation).where(
                NumberReservation.purchase_id == purchase_id
            )
        )
        await session.commit()

    from server.services.saas.activity_log import record_event

    await record_event(
        action="number.provision.done",
        resource_type="phone_number",
        resource_id=str(pn.id),
        actor="system",
        tenant_id=phone_tenant_id,
        payload={
            "purchaseId": str(purchase_id),
            "e164": purchase.e164,
            "assignedAgentId": purchase.assign_agent_id,
        },
        source="system",
    )
    return True
