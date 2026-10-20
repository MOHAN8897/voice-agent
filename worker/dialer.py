"""Campaign recovery worker. Database leases are the authoritative queue.

API instances also recover jobs, so a lost Redis wake-up cannot lose a campaign.
The normal application lifespan hydrates the persisted voice stack and shared
carrier context before any campaign can dial.
"""
from __future__ import annotations

import asyncio


def enqueue_campaign_run(campaign_id: str, run_id: str) -> bool:
    # Compatibility hook: the committed campaign_run row is already durable.
    return True


async def process_job(job: dict) -> None:
    import uuid
    from sqlalchemy import select
    from server.db.connection import get_session_factory
    from server.db.models.phase5_models import Campaign, CampaignRun
    from server.services.saas.campaign_runner import run_campaign
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Campaign database is unavailable")
    cid, rid = uuid.UUID(str(job["campaign_id"])), uuid.UUID(str(job["run_id"]))
    async with factory() as db:
        tenant_id = (await db.execute(select(Campaign.tenant_id).join(CampaignRun).where(
            Campaign.campaign_id == cid, CampaignRun.run_id == rid,
            Campaign.status == "running", CampaignRun.status == "running"))).scalar_one_or_none()
    if tenant_id:
        await run_campaign(str(cid), str(rid), workspace_tenant_id=tenant_id)


async def _serve():
    from server.app import app
    async with app.router.lifespan_context(app):
        await asyncio.Event().wait()


def run_loop() -> None:
    asyncio.run(_serve())
