"""Campaign audiences that reference durable follow-ups instead of copying dials.

The follow-up worker remains the only dispatcher for these jobs. Campaigns add
review, grouping and pacing; they cannot advance a caller's requested time or
bypass the agent's saved permissions.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select

from server.db.models.entities import Agent
from server.db.models.followup_models import AgentFollowUpPolicy, FollowUpJob
from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, DncEntry
from server.db.models.saas_models import Lead
from server.services.saas.followup_policy import FollowUpConfig, utc


def campaign_job_id(row):
    return (row.metadata_ or {}).get("followup_job_id")


async def audience(db, tenant_id, agent_id, kind, *, now, limit=500, offset=0):
    agent = await db.scalar(select(Agent.agent_id).where(Agent.tenant_id == tenant_id, Agent.agent_id == agent_id))
    if agent is None:
        raise HTTPException(404, "Agent not found")
    policy = await db.scalar(select(AgentFollowUpPolicy).where(
        AgentFollowUpPolicy.tenant_id == tenant_id, AgentFollowUpPolicy.agent_id == agent_id))
    cfg = FollowUpConfig.model_validate(policy.config if policy else {})
    if not cfg.enabled or (kind == "missed" and cfg.missedMode == "off"):
        return {"jobs": [], "total": 0, "unavailableReason": "Enable this follow-up flow in agent settings first. Review callback times before adding them to a campaign."}
    blocked = select(DncEntry.phone_e164).where(DncEntry.tenant_id == tenant_id, DncEntry.active.is_(True))
    stmt = select(FollowUpJob).where(FollowUpJob.tenant_id == tenant_id, FollowUpJob.agent_id == agent_id,
        FollowUpJob.kind == kind, FollowUpJob.status.in_(("scheduled", "needs_review") if kind == "missed" else ("scheduled",)), FollowUpJob.due_at.is_not(None),
        FollowUpJob.expires_at > now, FollowUpJob.payload["campaignId"].as_string().is_(None),
        FollowUpJob.phone.not_in(blocked))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.scalars(stmt.order_by(FollowUpJob.due_at, FollowUpJob.id).limit(limit).offset(offset))).all()
    return {"jobs": [await contact_for_job(db, row) for row in rows], "total": total,
            "limit": limit, "offset": offset}


async def contact_for_job(db, row):
    lead = await db.scalar(select(Lead).where(Lead.tenant_id == row.tenant_id,
        Lead.agent_id == str(row.agent_id), Lead.phone == row.phone).order_by(Lead.updated_at.desc()).limit(1))
    return {"jobId": str(row.id), "phone": row.phone, "kind": row.kind,
            "dueAt": utc(row.due_at).isoformat() if row.due_at else None,
            "expiresAt": utc(row.expires_at).isoformat(), "timezone": (row.payload or {}).get("timezone"),
            "full_name": lead.name if lead else "", "email": lead.email if lead else "",
            "notes": lead.notes if lead else "", "custom_fields": {"followup_kind": row.kind, "followup_job_id": str(row.id)}}


async def bind_jobs(db, ctx, campaign, ids, now):
    from server.services.saas.followup_service import _block_reason
    from server.auth.rbac import require_role_permission
    require_role_permission(ctx.role, "app.telephony.write")
    if not ctx.subscriber:
        raise HTTPException(403, "A signed-in workspace member must approve follow-up campaigns")
    ids = set(ids)
    # The caller already holds the workspace lock. Skip a job currently reserved
    # by a worker instead of reversing its job->workspace lock order.
    rows = (await db.scalars(select(FollowUpJob).where(FollowUpJob.tenant_id == ctx.workspace_tenant_id,
        FollowUpJob.agent_id == campaign.agent_id, FollowUpJob.id.in_(ids)).with_for_update(skip_locked=True))).all()
    if len(rows) != len(ids):
        raise HTTPException(409, "Some follow-ups are unavailable or being dispatched. Refresh the audience.")
    policy = await db.scalar(select(AgentFollowUpPolicy).where(AgentFollowUpPolicy.tenant_id == ctx.workspace_tenant_id,
        AgentFollowUpPolicy.agent_id == campaign.agent_id))
    cfg = FollowUpConfig.model_validate(policy.config if policy else {})
    contacts = []
    for row in rows:
        reviewable_missed = row.kind == "missed" and row.status == "needs_review" and row.due_at is not None
        if (row.status != "scheduled" and not reviewable_missed) or not row.due_at or utc(row.expires_at) <= now or (row.payload or {}).get("campaignId"):
            raise HTTPException(409, "Only scheduled, unclaimed follow-ups can be added. Review unclear timing first.")
        row.payload = {**(row.payload or {}), "approval": {"kind": "tenant", "at": now.isoformat()}}
        reason = await _block_reason(db, row, policy, cfg)
        if reason:
            raise HTTPException(409, "A selected follow-up is blocked by the agent settings, contact status or Do Not Call policy. Refresh and review it.")
        contact = await contact_for_job(db, row)
        contact["followup_job_id"] = str(row.id)
        contacts.append(contact)
        row.payload = {**row.payload, "campaignId": str(campaign.campaign_id), "campaignName": campaign.name}
        row.status = "scheduled"
        if (campaign.schedule or {}).get("starts_at"):
            row.due_at = max(utc(row.due_at), utc(datetime.fromisoformat(campaign.schedule["starts_at"])))
        row.authorized_by, row.billing_tenant_id = uuid.UUID(ctx.subject), ctx.tenant_id
        row.updated_at = now
    campaign.schedule = {**(campaign.schedule or {}), "audience": "followups"}
    return contacts


async def dispatch_gate(db, row, now):
    """Return (action, reason, outbound contact context) under the workspace lock."""
    from server.services.saas.campaign_runner import _principal, within_calling_window
    cid = (row.payload or {}).get("campaignId")
    if not cid:
        return "allow", "", None
    try:
        cid = uuid.UUID(cid)
    except (ValueError, TypeError):
        return "review", "invalid_campaign_reference", None
    camp = await db.scalar(select(Campaign).where(Campaign.tenant_id == row.tenant_id,
        Campaign.agent_id == row.agent_id, Campaign.campaign_id == cid))
    if not camp or camp.status in ("cancelled", "completed"):
        return "cancel", "campaign_closed", None
    if row.attempts >= max(1, int((camp.retry_rules or {}).get("max_attempts") or 1)):
        return "finish", "campaign_attempt_limit", None
    schedule = camp.schedule or {}
    if schedule.get("expires_at") and utc(datetime.fromisoformat(schedule["expires_at"])) <= now:
        return "expire", "campaign_expired", None
    if camp.status != "running" or not within_calling_window(schedule, row.payload, now):
        return "wait", "campaign_waiting", None
    run = await db.scalar(select(CampaignRun).where(CampaignRun.campaign_id == cid, CampaignRun.status == "running")
                          .order_by(CampaignRun.started_at.desc()).limit(1))
    try:
        if run is None:
            raise HTTPException(403, "Missing campaign authorization")
        await _principal(db, run, row.tenant_id)
    except HTTPException:
        return "review", "campaign_authorization_changed", None
    active = await db.scalar(select(func.count()).select_from(FollowUpJob).where(
        FollowUpJob.tenant_id == row.tenant_id, FollowUpJob.payload["campaignId"].as_string() == str(cid),
        FollowUpJob.status.in_(("dispatching", "dialed")), FollowUpJob.id != row.id))
    if active >= max(1, int(camp.concurrency or 1)):
        return "wait", "campaign_capacity", None
    contact = await db.scalar(select(CampaignContact).where(CampaignContact.campaign_id == cid,
        CampaignContact.metadata_["followup_job_id"].as_string() == str(row.id)))
    if contact is None:
        return "review", "campaign_contact_missing", None
    return "allow", "", {**(contact.metadata_ or {}), "campaign_id": str(cid),
                            "contact_id": str(contact.id), "resolved_variables": contact.resolved_variables or {},
                            "_from_e164": schedule.get("from_e164")}


async def sync_progress(db, camp, run):
    from server.services.saas.campaign_runner import _utcnow
    expiry = (camp.schedule or {}).get("expires_at")
    if expiry and utc(datetime.fromisoformat(expiry)) <= _utcnow():
        await cancel_pending(db, camp, _utcnow(), expired=True)
    rows = (await db.scalars(select(CampaignContact).where(CampaignContact.campaign_id == camp.campaign_id))).all()
    jobs = {str(job.id): job for job in (await db.scalars(select(FollowUpJob).where(
        FollowUpJob.tenant_id == camp.tenant_id, FollowUpJob.payload["campaignId"].as_string() == str(camp.campaign_id)))).all()}
    waiting = False
    for row in rows:
        job = jobs.get(campaign_job_id(row))
        if job is None:
            row.status = "requires_review"
            continue
        row.attempts, row.next_attempt_at = job.attempts, job.due_at
        if job.status in ("planning", "resolving", "scheduled", "dispatching", "dialed"):
            row.status = {"dispatching": "dialing", "dialed": "placed"}.get(job.status, "pending")
            waiting = True
        elif job.status == "completed":
            row.status = "completed" if job.reason == "call_connected" else "not_connected"
        else:
            row.status = "dnc_excluded" if job.reason == "do_not_call" else job.status
    groups = {}
    for row in rows:
        groups[row.status] = groups.get(row.status, 0) + 1
    run.stats = {**(run.stats or {}), "contacts": groups}
    if not waiting:
        camp.status = run.status = "requires_review" if groups.get("needs_review") or groups.get("requires_review") else "completed"
        run.ended_at, run.lease_owner, run.lease_expires_at = _utcnow(), None, None


async def cancel_pending(db, camp, now, *, expired=False):
    from sqlalchemy import update
    await db.execute(update(FollowUpJob).where(FollowUpJob.tenant_id == camp.tenant_id,
        FollowUpJob.payload["campaignId"].as_string() == str(camp.campaign_id),
        FollowUpJob.status.in_(("planning", "scheduled", "resolving", "needs_review")))
        .values(status="expired" if expired else "cancelled", reason="campaign_expired" if expired else "campaign_cancelled",
                lease_token=None, lease_until=None, updated_at=now))
