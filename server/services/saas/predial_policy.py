"""Final subscriber policy check after voice preparation, before any carrier POST."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.followup_models import AgentFollowUpPolicy, FollowUpJob
from server.db.models.phase5_models import AgentTelephonyProfile, Campaign, CampaignContact, DncEntry
from server.db.models.saas_models import User
from server.services.saas.followup_policy import FollowUpConfig, next_allowed, utc
from server.services.saas.tenant_guard import SubscriberPrincipal, assert_membership, subscriber_workspace_tenant_id, tenant_is_usable


async def assert_predial_policy(principal, *, agent_id, phone, contact=None, request_id=None):
    from server.auth.rbac import require_role_permission
    from server.config.env import get_settings
    from server.services.saas.platform_admins import effective_membership_role
    from server.services.saas.campaign_runner import _principal, within_calling_window, within_agent_hours
    from server.db.models.phase5_models import CampaignRun
    from server.services.saas.followup_service import _block_reason
    tid, aid = subscriber_workspace_tenant_id(principal), uuid.UUID(str(agent_id))
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(503, "Calling policy cannot be verified")
    now = datetime.now(timezone.utc)
    async with factory() as db:
        user = await db.get(User, principal.user_id)
        billing, workspace = await db.get(Tenant, principal.tenant_id), await db.get(Tenant, tid)
        if (not user or user.status != "active" or user.deleted_at or not tenant_is_usable(billing)
                or billing.status != "active" or not tenant_is_usable(workspace) or workspace.status != "active"):
            raise HTTPException(403, "Calling account is no longer active")
        if get_settings().saas_require_email_verification_for_login and not user.email_verified_at:
            raise HTTPException(403, "Calling account verification changed")
        member = await assert_membership(db, principal.user_id, principal.tenant_id)
        role = effective_membership_role(user.email, member.role)
        require_role_permission(role, "app.telephony.write")
        fresh = SubscriberPrincipal(user.user_id, principal.tenant_id, role, user.email)
        if subscriber_workspace_tenant_id(fresh) != tid:
            raise HTTPException(403, "Calling workspace access changed")
        agent = await db.scalar(select(Agent).where(Agent.tenant_id == tid, Agent.agent_id == aid))
        if not agent or agent.status != "active":
            raise HTTPException(409, "Agent is no longer active")
        if await db.scalar(select(DncEntry.id).where(DncEntry.tenant_id == tid, DncEntry.phone_e164 == phone,
                                                  DncEntry.active.is_(True)).limit(1)):
            raise HTTPException(409, "Caller opted out before the call was placed")
        profile_row = await db.scalar(select(AgentTelephonyProfile).where(AgentTelephonyProfile.tenant_id == tid,
                                                                        AgentTelephonyProfile.agent_id == aid))
        from server.services.saas.telephony_profile import _profile_to_dict
        profile = _profile_to_dict(profile_row) if profile_row else None
        if profile and profile.get("outbound_enabled") is False:
            raise HTTPException(409, "Outbound calls were disabled before dialing")
        data, job, camp = contact or {}, None, None
        if str(request_id or "").startswith("fu:") and data.get("followup_job_id"):
            job = await db.scalar(select(FollowUpJob).where(FollowUpJob.tenant_id == tid, FollowUpJob.agent_id == aid,
                FollowUpJob.id == uuid.UUID(str(data["followup_job_id"])), FollowUpJob.phone == phone))
            if not job or job.status != "dispatching" or request_id != f"fu:{job.id}:{(job.payload or {}).get('dispatchSequence') or job.attempts}":
                raise HTTPException(409, "Follow-up reservation changed before dialing")
            policy = await db.scalar(select(AgentFollowUpPolicy).where(AgentFollowUpPolicy.tenant_id == tid,
                                                                     AgentFollowUpPolicy.agent_id == aid))
            cfg = FollowUpConfig.model_validate(policy.config if policy else {})
            reason = await _block_reason(db, job, policy, cfg)
            if reason or utc(job.expires_at) <= now or not job.due_at or utc(job.due_at) > now or job.attempts > cfg.maxAttempts or next_allowed(now, cfg, profile) != now:
                raise HTTPException(409, "Follow-up settings or calling window changed before dialing")
        if data.get("campaign_id"):
            cid = uuid.UUID(str(data["campaign_id"]))
            camp = await db.scalar(select(Campaign).where(Campaign.tenant_id == tid, Campaign.agent_id == aid,
                                                        Campaign.campaign_id == cid))
            target = await db.scalar(select(CampaignContact.id).where(CampaignContact.campaign_id == cid,
                CampaignContact.id == uuid.UUID(str(data.get("contact_id"))), CampaignContact.phone_e164 == phone))
            if not camp or not target or camp.status != "running" or not within_calling_window(camp.schedule, data, now) or not within_agent_hours(profile, now):
                raise HTTPException(409, "Campaign or its calling window changed before dialing")
            run = await db.scalar(select(CampaignRun).where(CampaignRun.campaign_id == cid, CampaignRun.status == "running")
                                  .order_by(CampaignRun.started_at.desc()).limit(1))
            if not run:
                raise HTTPException(409, "Campaign is no longer authorized")
            await _principal(db, run, tid)
            if not job and await db.scalar(select(FollowUpJob.id).where(FollowUpJob.tenant_id == tid,
                FollowUpJob.phone == phone, FollowUpJob.status.in_(("planning", "resolving", "scheduled", "dispatching", "dialed", "needs_review"))).limit(1)):
                raise HTTPException(409, "An existing callback has priority over this campaign")
        from server.services.saas.billing_wallet_service import assert_wallet_allows_pstn
        await assert_wallet_allows_pstn(principal.tenant_id)
        # Check suppression and the clock last; earlier DB/pool waits must not
        # leave a previously valid window or opt-in cached at the carrier POST.
        if await db.scalar(select(DncEntry.id).where(DncEntry.tenant_id == tid, DncEntry.phone_e164 == phone,
                                                  DncEntry.active.is_(True)).limit(1)):
            raise HTTPException(409, "Caller opted out during voice preparation")
        now = datetime.now(timezone.utc)
        if job and (utc(job.expires_at) <= now or next_allowed(now, cfg, profile) != now):
            raise HTTPException(409, "Follow-up calling window closed during voice preparation")
        if camp and (not within_calling_window(camp.schedule, data, now) or not within_agent_hours(profile, now)):
            raise HTTPException(409, "Campaign window closed during voice preparation")
