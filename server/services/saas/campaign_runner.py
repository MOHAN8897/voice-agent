"""In-process campaign dialer — concurrent PSTN outbound with tenant caps.

Redis queue remains optional; when Redis is down we still dial from the API
process so bulk campaigns work in single-node SaaS deploys.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, DialAttempt

logger = logging.getLogger(__name__)

# campaign_id -> running asyncio.Task (best-effort cancel on pause)
_active_runners: dict[str, asyncio.Task] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def count_active_pstn(tenant_id: uuid.UUID) -> int:
    from server.db.models.entities import Call

    factory = get_session_factory()
    if factory is None:
        return 0
    async with factory() as session:
        from sqlalchemy import func

        result = await session.execute(
            select(func.count())
            .select_from(Call)
            .where(
                Call.tenant_id == tenant_id,
                Call.channel == "pstn",
                Call.ended_at.is_(None),
            )
        )
        return int(result.scalar_one() or 0)


async def _dial_one(
    *,
    principal: Any,
    agent_id: str,
    from_e164: str | None,
    to_e164: str,
    campaign_id: str,
    contact_id: uuid.UUID,
    contact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from server.services.saas.telephony_orchestrator import subscriber_outbound

    result = await subscriber_outbound(
        principal,
        agent_id=agent_id,
        from_e164=from_e164,
        to_e164=to_e164,
        dial_request_id=f"camp:{campaign_id}:{contact_id}:{uuid.uuid4().hex[:8]}",
        contact=contact,
    )
    return result if isinstance(result, dict) else {"ok": False, "error": "bad_response"}


async def run_campaign(
    campaign_id: str,
    run_id: str,
    *,
    principal: Any,
    workspace_tenant_id: uuid.UUID,
) -> None:
    """Dial pending contacts up to campaign.concurrency, respecting tenant PSTN cap."""
    settings = get_settings()
    hard_cap = max(1, min(20, int(settings.campaign_max_concurrency or 20)))
    factory = get_session_factory()
    if factory is None:
        logger.warning("campaign_runner.no_db campaign=%s", campaign_id)
        return

    async with factory() as session:
        camp = await session.get(Campaign, uuid.UUID(campaign_id))
        if camp is None:
            return
        concurrency = max(1, min(hard_cap, int(camp.concurrency or 1)))
        retry = camp.retry_rules or {}
        max_attempts = max(1, min(5, int(retry.get("max_attempts") or settings.campaign_default_retry_attempts or 3)))
        agent_id = str(camp.agent_id)
        from_e164 = (camp.schedule or {}).get("from_e164")
        run = await session.get(CampaignRun, uuid.UUID(run_id))

    sem = asyncio.Semaphore(concurrency)
    stats = {"dialed": 0, "connected": 0, "failed": 0, "skipped": 0}

    async def one(contact: CampaignContact) -> None:
        async with sem:
            # Wait until under tenant concurrent PSTN ceiling.
            from server.db.models.entities import Tenant

            limits: dict = {}
            async with factory() as session:
                tenant = await session.get(Tenant, principal.tenant_id)
                limits = (tenant.limits or {}) if tenant else {}
            max_pstn = max(1, min(20, int(limits.get("max_concurrent_pstn") or hard_cap)))
            for _ in range(60):
                active = await count_active_pstn(principal.tenant_id)
                if active < max_pstn:
                    break
                await asyncio.sleep(2)
            else:
                stats["skipped"] += 1
                return

            async with factory() as session:
                row = await session.get(CampaignContact, contact.id)
                if row is None or row.status in ("connected", "completed", "dnc"):
                    return
                if int(row.attempts or 0) >= max_attempts:
                    row.status = "exhausted"
                    await session.commit()
                    stats["skipped"] += 1
                    return
                row.attempts = int(row.attempts or 0) + 1
                row.last_attempt_at = _utcnow()
                row.status = "dialing"
                attempt = DialAttempt(
                    id=uuid.uuid4(),
                    campaign_id=uuid.UUID(campaign_id),
                    contact_id=row.id,
                    status="queued",
                )
                session.add(attempt)
                await session.commit()
                phone = row.phone_e164
                attempt_id = attempt.id
                contact_payload = {
                    "campaign_id": campaign_id,
                    "contact_id": str(contact.id),
                    **(row.metadata_ or {}),
                    "resolved_variables": row.resolved_variables or {},
                }

            try:
                result = await _dial_one(
                    principal=principal,
                    agent_id=agent_id,
                    from_e164=from_e164,
                    to_e164=phone,
                    campaign_id=campaign_id,
                    contact_id=contact.id,
                    contact=contact_payload,
                )
                ok = bool(result.get("ok") or result.get("call_id") or result.get("callId"))
                call_id = result.get("call_id") or result.get("callId")
                async with factory() as session:
                    row = await session.get(CampaignContact, contact.id)
                    att = await session.get(DialAttempt, attempt_id)
                    if att:
                        att.status = "placed" if ok else "failed"
                        att.error = None if ok else str(result.get("error") or result)[:400]
                        if call_id:
                            try:
                                att.call_id = uuid.UUID(str(call_id))
                            except (ValueError, TypeError):
                                pass
                    if row:
                        row.status = "connected" if ok else "failed"
                    await session.commit()
                if ok:
                    stats["dialed"] += 1
                    stats["connected"] += 1
                else:
                    stats["failed"] += 1
            except Exception as exc:
                logger.exception("campaign_runner.dial_failed campaign=%s phone=%s", campaign_id, phone)
                async with factory() as session:
                    row = await session.get(CampaignContact, contact.id)
                    att = await session.get(DialAttempt, attempt_id)
                    if att:
                        att.status = "failed"
                        att.error = str(exc)[:400]
                    if row:
                        row.status = "failed"
                    await session.commit()
                stats["failed"] += 1

    async with factory() as session:
        result = await session.execute(
            select(CampaignContact).where(
                CampaignContact.campaign_id == uuid.UUID(campaign_id),
                CampaignContact.status.in_(("pending", "failed", "queued")),
            )
        )
        contacts = list(result.scalars().all())

    if not contacts:
        async with factory() as session:
            camp = await session.get(Campaign, uuid.UUID(campaign_id))
            run = await session.get(CampaignRun, uuid.UUID(run_id))
            if camp:
                camp.status = "completed"
            if run:
                run.status = "completed"
                run.ended_at = _utcnow()
                run.stats = stats
            await session.commit()
        return

    await asyncio.gather(*(one(c) for c in contacts), return_exceptions=True)

    async with factory() as session:
        camp = await session.get(Campaign, uuid.UUID(campaign_id))
        run = await session.get(CampaignRun, uuid.UUID(run_id))
        # Leave running if retries remain; otherwise complete.
        pending = (
            await session.execute(
                select(CampaignContact).where(
                    CampaignContact.campaign_id == uuid.UUID(campaign_id),
                    CampaignContact.status.in_(("pending", "failed")),
                    CampaignContact.attempts < max_attempts,
                )
            )
        ).scalars().first()
        if camp and camp.status == "running" and not pending:
            camp.status = "completed"
        if run:
            run.status = "completed" if not pending else "running"
            run.ended_at = _utcnow() if not pending else None
            run.stats = stats
        await session.commit()
    logger.info("campaign_runner.done campaign=%s stats=%s", campaign_id, stats)


def spawn_campaign_runner(
    campaign_id: str,
    run_id: str,
    *,
    principal: Any,
    workspace_tenant_id: uuid.UUID,
) -> None:
    """Fire-and-forget from a FastAPI request."""
    prev = _active_runners.get(campaign_id)
    if prev and not prev.done():
        prev.cancel()

    async def _wrap() -> None:
        try:
            await run_campaign(
                campaign_id,
                run_id,
                principal=principal,
                workspace_tenant_id=workspace_tenant_id,
            )
        except asyncio.CancelledError:
            logger.info("campaign_runner.cancelled campaign=%s", campaign_id)
        except Exception:
            logger.exception("campaign_runner.crash campaign=%s", campaign_id)
        finally:
            _active_runners.pop(campaign_id, None)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("campaign_runner.no_loop campaign=%s", campaign_id)
        return
    _active_runners[campaign_id] = loop.create_task(_wrap(), name=f"campaign-{campaign_id[:8]}")
