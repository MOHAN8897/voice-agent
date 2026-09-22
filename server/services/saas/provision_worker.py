"""Async Telnyx provision after Stripe payment."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import NumberPurchase, ProvisionJob

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
        from server.services.telnyx_client import TelnyxClient
        from server.services.telnyx_provisioning import provision_ordered_number

        client = TelnyxClient()
        await provision_ordered_number(client, purchase.e164)
    except Exception as e:
        logger.exception("provision failed purchase=%s", purchase_id)
        async with factory() as session:
            purchase = await session.get(NumberPurchase, purchase_id)
            job = (
                await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id))
            ).scalar_one()
            job.status = "failed"
            job.last_error = {"message": str(e)}
            if purchase:
                purchase.status = "failed"
            await session.commit()
        return True

    async with factory() as session:
        purchase = await session.get(NumberPurchase, purchase_id)
        job = (
            await session.execute(select(ProvisionJob).where(ProvisionJob.purchase_id == purchase_id))
        ).scalar_one()
        if purchase is None:
            return True
        pn = PhoneNumber(
            tenant_id=purchase.tenant_id,
            e164=purchase.e164,
            status="active",
            purchase_id=purchase.id,
            billing_source="stripe",
            inbound_enabled=True,
            outbound_enabled=True,
            created_at=_utcnow(),
        )
        session.add(pn)
        await session.flush()
        purchase.phone_number_id = pn.id
        purchase.status = "active"
        job.status = "done"
        job.updated_at = _utcnow()
        await session.commit()
    return True
