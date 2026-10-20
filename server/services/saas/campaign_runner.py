"""Database-leased campaign execution; Redis is only an optional wake-up signal.

Each tick claims a bounded batch. Reservations cover ringing and talking, and
ambiguous carrier requests are held for review instead of automatically redialed.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Tenant
from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, DialAttempt, DncEntry, PstnDialRequest
from server.services.saas.call_admission import request_key

logger = logging.getLogger(__name__)
_active_runners: dict[str, asyncio.Task] = {}
LEASE_SECONDS = 120
IN_FLIGHT = ("dialing", "placed", "connected")
READY = ("pending", "queued", "failed")


def _utcnow():
    return datetime.now(timezone.utc)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def actor_context(ctx):
    # Persist identity, never a reusable JWT or an unverified role snapshot.
    return {"user_id": str(ctx.subject), "tenant_id": str(ctx.tenant_id)}


async def _principal(db, run, workspace_tenant_id):
    from server.auth.rbac import require_role_permission
    from server.db.models.saas_models import User
    from server.services.saas.tenant_guard import SubscriberPrincipal, assert_membership, subscriber_workspace_tenant_id

    actor = (run.stats or {}).get("actor") or {}
    try:
        user_id, tenant_id = uuid.UUID(actor["user_id"]), uuid.UUID(actor["tenant_id"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(403, "Campaign needs a verified subscriber to resume")
    user = await db.get(User, user_id)
    tenant = await db.get(Tenant, tenant_id)
    if user is None or user.status != "active" or user.deleted_at is not None or tenant is None or tenant.status != "active" or tenant.deleted_at is not None:
        raise HTTPException(403, "Campaign account is inactive")
    member = await assert_membership(db, user_id, tenant_id)
    require_role_permission(member.role, "app.campaigns.write")
    principal = SubscriberPrincipal(user_id=user_id, tenant_id=tenant_id, role=member.role, email=user.email)
    if subscriber_workspace_tenant_id(principal) != workspace_tenant_id:
        raise HTTPException(403, "Campaign workspace is no longer accessible")
    return principal


def within_calling_window(schedule, metadata, now=None):
    window = (schedule or {}).get("calling_window")
    if not window:
        return True
    # Explicit recipient timezone takes precedence over the chosen fallback zone.
    zone = str((metadata or {}).get("timezone") or window["timezone"])
    try:
        local = (now or _utcnow()).astimezone(ZoneInfo(zone)).strftime("%H:%M")
    except (ValueError, KeyError):
        return False
    start, end = window["start"], window["end"]
    return start <= local < end if start < end else local >= start or local < end


async def _lock_campaign(db, campaign_id, tenant_id):
    from sqlalchemy import text
    if db.bind.dialect.name == "sqlite":
        await db.execute(text("BEGIN IMMEDIATE"))
    return (await db.execute(select(Campaign).where(Campaign.campaign_id == campaign_id,
        Campaign.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()


async def _reconcile(db, campaign, principal):
    rows = (await db.execute(select(CampaignContact).where(CampaignContact.campaign_id == campaign.campaign_id,
        CampaignContact.status.in_(IN_FLIGHT)).order_by(CampaignContact.id).limit(20))).scalars().all()
    retry = campaign.retry_rules or {}
    for row in rows:
        attempt = (await db.execute(select(DialAttempt).where(DialAttempt.campaign_id == campaign.campaign_id,
            DialAttempt.contact_id == row.id).order_by(DialAttempt.created_at.desc()).limit(1))).scalar_one_or_none()
        if attempt is None:
            row.status = "requires_review"
            continue
        key = request_key(principal.tenant_id, f"camp:{campaign.campaign_id}:{row.id}:{attempt.id}")
        ledger = (await db.execute(select(PstnDialRequest).where(PstnDialRequest.tenant_id == principal.tenant_id,
            PstnDialRequest.request_key == key))).scalar_one_or_none()
        if ledger is None:
            # Includes a crash after claiming but before admission. Never guess
            # whether an older/untracked carrier request was accepted.
            if row.last_attempt_at is None or _aware(row.last_attempt_at) < _utcnow() - timedelta(seconds=LEASE_SECONDS):
                row.status, attempt.status = "requires_review", "requires_review"
            continue
        attempt.carrier_call_uuid, attempt.call_id = ledger.carrier_id, ledger.call_id
        if ledger.status == "answered":
            row.status, attempt.status = "connected", "connected"
        elif ledger.status == "ended":
            connected = ledger.answered_at is not None or ledger.call_id is not None or row.status == "connected"
            row.status, attempt.status = ("completed", "completed") if connected else ("failed", "not_connected")
            row.next_attempt_at = _utcnow() + timedelta(minutes=int(retry.get("retry_delay_minutes") or 30))
        elif ledger.status in ("uncertain", "reserved") and _aware(ledger.updated_at) < _utcnow() - timedelta(seconds=LEASE_SECONDS):
            row.status, attempt.status = "requires_review", "requires_review"
        elif ledger.status == "failed":
            row.status, attempt.status = "failed", "failed"
            row.next_attempt_at = _utcnow() + timedelta(minutes=int(retry.get("retry_delay_minutes") or 30))


async def _dial_claim(campaign_id, run_id, tenant_id, owner, contact_id, attempt_id):
    from server.services.saas.telephony_orchestrator import subscriber_outbound
    factory = get_session_factory()
    async with factory() as db:
        camp = await _lock_campaign(db, campaign_id, tenant_id)
        run = (await db.execute(select(CampaignRun).where(CampaignRun.run_id == run_id,
            CampaignRun.campaign_id == campaign_id))).scalar_one_or_none()
        row = (await db.execute(select(CampaignContact).where(CampaignContact.campaign_id == campaign_id,
            CampaignContact.id == contact_id))).scalar_one_or_none()
        if not camp or not run or not row or run.lease_owner != owner:
            return
        if camp.status != "running" or run.status != "running":
            row.status = "pending"
            row.attempts = max(0, row.attempts - 1)
            attempt = await db.get(DialAttempt, attempt_id)
            attempt.status = "cancelled_before_dial"
            await db.commit()
            return
        principal = await _principal(db, run, tenant_id)
        dnc = (await db.execute(select(DncEntry.id).where(DncEntry.tenant_id == principal.tenant_id,
            DncEntry.phone_e164 == row.phone_e164, DncEntry.active.is_(True)).limit(1))).scalar_one_or_none()
        if dnc:
            row.status = "dnc_excluded"
            attempt = (await db.execute(select(DialAttempt).where(DialAttempt.campaign_id == campaign_id,
                DialAttempt.id == attempt_id))).scalar_one()
            attempt.status, attempt.error = "dnc_skipped", "Excluded by the Do Not Call registry before dialing."
            await db.commit()
            return
        payload = {**(row.metadata_ or {}), "campaign_id": str(campaign_id), "contact_id": str(contact_id),
                   "resolved_variables": row.resolved_variables or {}}
        args = dict(agent_id=str(camp.agent_id), from_e164=(camp.schedule or {}).get("from_e164"),
                    to_e164=row.phone_e164, contact=payload,
                    dial_request_id=f"camp:{campaign_id}:{contact_id}:{attempt_id}")
        await db.commit()
    # Subscriber outbound repeats wallet, verification, ownership, DNC and shared
    # admission checks immediately before the carrier request.
    try:
        result = await subscriber_outbound(principal, **args)
        state = "placed" if result.get("ok") else "requires_review"
        error = None if result.get("ok") else "Call request could not be confirmed; review before retrying."
    except HTTPException as exc:
        code = ((exc.detail or {}).get("error") or {}).get("code") if isinstance(exc.detail, dict) else ""
        state = "pending" if exc.status_code == 429 else "dnc_excluded" if code == "dnc_blocked" else "blocked"
        error = "Waiting for call capacity" if state == "pending" else "Call blocked by account or contact policy"
        if state == "blocked":
            logger.warning("campaign.dial_blocked campaign=%s status=%s", campaign_id, exc.status_code)
    except Exception as exc:
        state, error = "requires_review", "Call result is uncertain; review before retrying."
        logger.error("campaign.dial_uncertain campaign=%s error_type=%s", campaign_id, type(exc).__name__)
    async with factory() as db:
        camp = await _lock_campaign(db, campaign_id, tenant_id)
        row = (await db.execute(select(CampaignContact).where(CampaignContact.campaign_id == campaign_id,
            CampaignContact.id == contact_id))).scalar_one()
        attempt = (await db.execute(select(DialAttempt).where(DialAttempt.campaign_id == campaign_id,
            DialAttempt.id == attempt_id))).scalar_one()
        row.status, attempt.status, attempt.error = state, state, error
        if state == "pending":
            row.attempts = max(0, row.attempts - 1)
            row.next_attempt_at = _utcnow() + timedelta(seconds=5)
        if state == "placed":
            attempt.carrier_call_uuid = str(result.get("call_control_id") or "")[:100] or None
        await db.commit()


async def campaign_tick(campaign_id, run_id, *, workspace_tenant_id, owner):
    factory = get_session_factory()
    if factory is None:
        return False
    claims = []
    async with factory() as db:
        camp = await _lock_campaign(db, campaign_id, workspace_tenant_id)
        run = (await db.execute(select(CampaignRun).where(CampaignRun.run_id == run_id,
            CampaignRun.campaign_id == campaign_id).with_for_update())).scalar_one_or_none()
        if not camp or not run or camp.status != "running" or run.status != "running":
            return False
        if not camp.consent_confirmed:
            camp.status, run.status = "paused", "blocked"
            run.stats = {**(run.stats or {}), "error": "Calling authorization must be confirmed before resuming."}
            await db.commit()
            return False
        if run.lease_owner != owner and _aware(run.lease_expires_at) and _aware(run.lease_expires_at) > _utcnow():
            return False
        run.lease_owner, run.lease_expires_at = owner, _utcnow() + timedelta(seconds=LEASE_SECONDS)
        try:
            principal = await _principal(db, run, workspace_tenant_id)
        except HTTPException:
            camp.status, run.status = "paused", "blocked"
            run.stats = {**(run.stats or {}), "error": "Account access changed. Review and resume the campaign."}
            await db.commit()
            return False
        await _reconcile(db, camp, principal)
        max_attempts = max(1, min(5, int((camp.retry_rules or {}).get("max_attempts") or 3)))
        concurrency = max(1, min(20, int(get_settings().campaign_max_concurrency or 20), int(camp.concurrency or 1)))
        active = (await db.execute(select(func.count()).select_from(CampaignContact).where(
            CampaignContact.campaign_id == campaign_id, CampaignContact.status.in_(IN_FLIGHT)))).scalar_one()
        if active < concurrency:
            billing_tenant = await db.get(Tenant, principal.tenant_id)
            platform_cps = int(getattr(get_settings(), "saas_max_outbound_cps", 1))
            batch_size = max(1, min(20, platform_cps, int((billing_tenant.limits or {}).get("max_outbound_cps") or platform_cps)))
            candidates = (await db.execute(select(CampaignContact).where(CampaignContact.campaign_id == campaign_id,
                CampaignContact.status.in_(READY), CampaignContact.attempts < max_attempts,
                or_(CampaignContact.next_attempt_at.is_(None), CampaignContact.next_attempt_at <= _utcnow()))
                .order_by(CampaignContact.next_attempt_at.asc().nullsfirst(), CampaignContact.id)
                .limit(100).with_for_update(skip_locked=True))).scalars().all()
            for row in candidates:
                if len(claims) >= min(concurrency - active, batch_size):
                    break
                if not within_calling_window(camp.schedule, row.metadata_):
                    row.next_attempt_at = _utcnow() + timedelta(minutes=1)
                    continue
                row.status, row.last_attempt_at = "dialing", _utcnow()
                row.attempts = int(row.attempts or 0) + 1
                attempt_id = uuid.uuid4()
                db.add(DialAttempt(id=attempt_id, campaign_id=campaign_id, contact_id=row.id, status="queued"))
                claims.append((row.id, attempt_id))
        groups = dict((await db.execute(select(CampaignContact.status, func.count()).where(
            CampaignContact.campaign_id == campaign_id).group_by(CampaignContact.status))).all())
        eligible = (await db.execute(select(func.count()).select_from(CampaignContact).where(
            CampaignContact.campaign_id == campaign_id, CampaignContact.status.in_(READY),
            CampaignContact.attempts < max_attempts))).scalar_one()
        run.stats = {**(run.stats or {}), "contacts": groups}
        if not claims and not active and not eligible:
            needs_review = groups.get("requires_review", 0) or groups.get("blocked", 0)
            camp.status = run.status = "requires_review" if needs_review else "completed"
            run.ended_at, run.lease_owner, run.lease_expires_at = _utcnow(), None, None
        await db.commit()
        more = camp.status == "running"
    if claims:
        await asyncio.gather(*(_dial_claim(campaign_id, run_id, workspace_tenant_id, owner, cid, aid) for cid, aid in claims))
    return more


async def run_campaign(campaign_id, run_id, *, workspace_tenant_id, principal=None):
    owner = uuid.uuid4()
    try:
        while await campaign_tick(uuid.UUID(str(campaign_id)), uuid.UUID(str(run_id)),
                                 workspace_tenant_id=workspace_tenant_id, owner=owner):
            await asyncio.sleep(1)
    finally:
        factory = get_session_factory()
        if factory:
            async with factory() as db:
                run = (await db.execute(select(CampaignRun).join(Campaign).where(CampaignRun.run_id == uuid.UUID(str(run_id)),
                    Campaign.tenant_id == workspace_tenant_id, CampaignRun.lease_owner == owner).with_for_update())).scalar_one_or_none()
                if run:
                    run.lease_owner, run.lease_expires_at = None, None
                    await db.commit()


def spawn_campaign_runner(campaign_id, run_id, *, workspace_tenant_id, principal=None):
    previous = _active_runners.get(campaign_id)
    if previous and not previous.done():
        return
    async def wrap():
        try:
            await run_campaign(campaign_id, run_id, workspace_tenant_id=workspace_tenant_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("campaign.worker_failed campaign=%s error_type=%s", campaign_id, type(exc).__name__)
        finally:
            if _active_runners.get(campaign_id) is asyncio.current_task():
                _active_runners.pop(campaign_id, None)
    _active_runners[campaign_id] = asyncio.create_task(wrap(), name=f"campaign-{campaign_id[:8]}")


async def recover_campaigns_once():
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as db:
        rows = (await db.execute(select(Campaign.campaign_id, Campaign.tenant_id, CampaignRun.run_id)
            .join(CampaignRun).join(Tenant, Tenant.tenant_id == Campaign.tenant_id).where(
                Campaign.status == "running", CampaignRun.status == "running", Tenant.status == "active",
                Tenant.deleted_at.is_(None), or_(CampaignRun.lease_expires_at.is_(None), CampaignRun.lease_expires_at < _utcnow()))
            .order_by(CampaignRun.started_at).limit(100))).all()
    for cid, tid, rid in rows:
        spawn_campaign_runner(str(cid), str(rid), workspace_tenant_id=tid)


async def recovery_loop():
    while True:
        try:
            await recover_campaigns_once()
        except Exception as exc:
            logger.error("campaign.recovery_failed error_type=%s", type(exc).__name__)
        await asyncio.sleep(10)


async def stop_campaign_runners():
    tasks = list(_active_runners.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
