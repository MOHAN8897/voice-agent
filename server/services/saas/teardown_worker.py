"""Process tenant_teardown_jobs (PRD-03)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import TenantTeardownJob

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def process_one_teardown() -> bool:
    factory = get_session_factory()
    if factory is None:
        return False
    async with factory() as session:
        result = await session.execute(
            select(TenantTeardownJob).where(TenantTeardownJob.status == "queued").limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return False
        job.status = "running"
        job.updated_at = _utcnow()
        tenant_id = job.tenant_id
        job_id = job.job_id
        await session.commit()

    try:
        async with factory() as session:
            tenant = await session.get(Tenant, tenant_id)
            if tenant:
                tenant.status = "deleted"
                await session.execute(
                    update(Agent).where(Agent.tenant_id == tenant_id).values(status="archived")
                )
                await session.execute(
                    update(PhoneNumber)
                    .where(PhoneNumber.tenant_id == tenant_id)
                    .values(status="released", released_at=_utcnow(), inbound_enabled=False, outbound_enabled=False)
                )
            job_row = await session.get(TenantTeardownJob, job_id)
            if job_row:
                job_row.status = "done"
                job_row.updated_at = _utcnow()
            await session.commit()
    except Exception as e:
        logger.exception("teardown failed tenant=%s", tenant_id)
        async with factory() as session:
            job = await session.get(TenantTeardownJob, job_id)
            if job:
                job.status = "failed"
                job.last_error = {"message": str(e)}
                job.updated_at = _utcnow()
            await session.commit()
    return True
