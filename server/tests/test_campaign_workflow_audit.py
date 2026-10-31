"""Regression checks for campaign/follow-up ownership and tenant controls."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import uuid

import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select, func

from server.tests.test_campaign_execution_safety import db as campaign_db, seeded_campaign, TID, OTHER, UID, AID
from server.db.models.saas_models import User
from server.db.models.phase5_models import CampaignContact, CampaignRun, DncEntry
from server.routes import campaigns as routes
from server.services.saas import campaign_runner as runner
from server.db.models.followup_models import AgentFollowUpPolicy, FollowUpJob
from server.services.saas import followup_service as followups
from server.services.saas.followup_policy import FollowUpConfig
from server.auth.api_tenant import ApiTenantContext

AT = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
PHONE = "+12025550123"
db = campaign_db  # Reuse the isolated fixture without importing test cases.


@pytest.fixture
async def linked(db, monkeypatch):
    from server.services.saas import call_callback_service
    cfg = FollowUpConfig(enabled=True, callbackMode="automatic", missedMode="automatic",
                         timezone="UTC", startTime="00:00", endTime="23:59", weekdays=list(range(7)), maxAttempts=2)
    async with db() as session:
        session.add(AgentFollowUpPolicy(tenant_id=TID, agent_id=AID, config=cfg.model_dump(),
            authorized_by=UID, authorized_at=AT - timedelta(days=1), billing_tenant_id=TID))
        row = FollowUpJob(tenant_id=TID, agent_id=AID, phone=PHONE, source_id=str(uuid.uuid4()),
            origin_key=str(uuid.uuid4()), kind="callback", status="scheduled", due_at=AT + timedelta(hours=6),
            expires_at=AT + timedelta(days=2), payload={"timezone": "UTC"}, authorized_by=UID, billing_tenant_id=TID)
        session.add(row)
        await session.commit()
        jid = row.id
    clock = [AT]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz or timezone.utc)
    monkeypatch.setattr(routes, "datetime", Clock)
    monkeypatch.setattr(followups, "get_session_factory", lambda: db)
    monkeypatch.setattr(followups, "now_utc", lambda: clock[0])
    monkeypatch.setattr(runner, "_utcnow", lambda: clock[0])
    monkeypatch.setattr(runner, "spawn_campaign_runner", lambda *args, **kwargs: None)
    dial = AsyncMock(return_value={"ok": True, "callControlId": "synthetic-control"})
    monkeypatch.setattr(call_callback_service, "request_callback", dial)
    ctx = ApiTenantContext(tenant_id=TID, role="customer_admin", subject=str(UID), subscriber=True)
    return SimpleNamespace(db=db, job_id=jid, clock=clock, dial=dial, ctx=ctx)


async def create_linked(linked, **kwargs):
    body = routes.CampaignCreate(name="Reviewed follow-ups", agentId=str(AID), consentConfirmed=True,
                                followupJobIds=[linked.job_id], **kwargs)
    request = Request({"type": "http", "headers": []})
    return await routes.create_campaign(request, body, linked.ctx)


def test_dnd_removal_needs_a_real_trimmed_reason():
    with pytest.raises(ValidationError):
        routes.DncDeactivateBody(removalReason="      ", reconsentConfirmed=True)


async def test_campaign_worker_rechecks_required_email_verification(db):
    cid, rid = await seeded_campaign(db, 1)
    async with db() as session:
        user = await session.get(User, UID)
        user.email_verified_at = None
        await session.commit()
        run = await session.get(CampaignRun, rid)
        with pytest.raises(HTTPException) as exc:
            await runner._principal(session, run, TID)
        assert exc.value.status_code == 403


def test_campaign_schedule_rejects_naive_deadlines():
    with pytest.raises(ValidationError):
        routes.CampaignCreate(name="Later", agentId=str(AID), consentConfirmed=True,
                              startsAt="2026-11-01T10:00:00", expiresAt="2026-11-01T11:00:00")


async def test_followup_campaign_reuses_job_and_never_advances_six_hour_request(linked):
    result = await create_linked(linked, autoStart=True)
    cid = uuid.UUID(result["id"])
    await followups._process(linked.job_id)
    linked.dial.assert_not_awaited()
    linked.clock[0] = AT + timedelta(hours=6)
    await followups._process(linked.job_id)
    await followups._process(linked.job_id)
    linked.dial.assert_awaited_once()
    args = linked.dial.call_args.kwargs
    assert args["dial_request_id"].startswith(f"fu:{linked.job_id}:")
    assert args["contact"]["campaign_id"] == str(cid)
    async with linked.db() as session:
        row = await session.get(FollowUpJob, linked.job_id)
        assert row.status == "dialed" and row.attempts == 1
        assert await session.scalar(select(func.count()).select_from(FollowUpJob)) == 1


async def test_followup_campaign_draft_pause_and_cancel_never_dispatch(linked):
    result = await create_linked(linked)
    cid = result["id"]
    linked.clock[0] = AT + timedelta(hours=7)
    await followups.run_once()
    linked.dial.assert_not_awaited()
    await routes.start_campaign(cid, linked.ctx)
    await routes.pause_campaign(cid, linked.ctx)
    await followups.run_once()
    linked.dial.assert_not_awaited()
    await routes.cancel_campaign(cid, linked.ctx)
    async with linked.db() as session:
        assert (await session.get(FollowUpJob, linked.job_id)).status == "cancelled"


async def test_followup_campaign_rejects_duplicate_foreign_and_unresolved_jobs(linked):
    other = ApiTenantContext(tenant_id=OTHER, role="customer_admin", subject=str(UID), subscriber=True)
    with pytest.raises(HTTPException):
        await routes.followup_audience(AID, "callback", 500, 0, other)
    async with linked.db() as session:
        row = await session.get(FollowUpJob, linked.job_id)
        row.status, row.due_at = "needs_review", None
        await session.commit()
    with pytest.raises(HTTPException) as exc:
        await create_linked(linked)
    assert exc.value.status_code == 409
    async with linked.db() as session:
        row = await session.get(FollowUpJob, linked.job_id)
        row.status, row.due_at = "scheduled", AT
        await session.commit()
    await create_linked(linked)
    with pytest.raises(HTTPException) as exc:
        await create_linked(linked)
    assert exc.value.status_code == 409


async def test_manual_dnd_add_suppresses_job_and_removal_does_not_resurrect_it(linked):
    await routes.add_dnc(routes.DncBody(phoneE164=PHONE), linked.ctx)
    async with linked.db() as session:
        assert (await session.get(FollowUpJob, linked.job_id)).status == "suppressed"
    await routes.deactivate_dnc(PHONE, routes.DncDeactivateBody(removalReason="Caller explicitly renewed permission", reconsentConfirmed=True), linked.ctx)
    async with linked.db() as session:
        row = await session.scalar(select(DncEntry).where(DncEntry.tenant_id == TID, DncEntry.phone_e164 == PHONE))
        assert row.active is False and row.reconsent_confirmed is True
        assert (await session.get(FollowUpJob, linked.job_id)).status == "suppressed"


async def test_stale_dnd_removal_cannot_erase_a_newer_caller_optout(linked):
    await routes.add_dnc(routes.DncBody(phoneE164=PHONE), linked.ctx)
    async with linked.db() as session:
        entry = await session.scalar(select(DncEntry).where(DncEntry.tenant_id == TID, DncEntry.phone_e164 == PHONE))
        old = entry.added_at.replace(tzinfo=timezone.utc)
        entry.added_at = old + timedelta(seconds=1)
        await session.commit()
    with pytest.raises(HTTPException) as exc:
        await routes.deactivate_dnc(PHONE, routes.DncDeactivateBody(removalReason="Renewed permission before latest optout",
                                   reconsentConfirmed=True, expectedAddedAt=old), linked.ctx)
    assert exc.value.status_code == 409
    async with linked.db() as session:
        assert (await session.scalar(select(DncEntry).where(DncEntry.tenant_id == TID))).active is True


@pytest.mark.parametrize("kind", ["callback", "missed"])
async def test_audience_respects_agent_and_kind_and_excludes_reserved_jobs(linked, kind):
    async with linked.db() as session:
        row = await session.get(FollowUpJob, linked.job_id)
        row.kind = kind
        await session.commit()
    data = await routes.followup_audience(AID, kind, 500, 0, linked.ctx)
    assert [job["jobId"] for job in data["jobs"]] == [str(linked.job_id)]
    await create_linked(linked)
    assert (await routes.followup_audience(AID, kind, 500, 0, linked.ctx))["jobs"] == []


async def test_campaign_expiry_closes_future_linked_jobs_without_dialing(linked):
    result = await create_linked(linked, autoStart=True, expiresAt=AT + timedelta(hours=1))
    linked.clock[0] = AT + timedelta(hours=2)
    async with linked.db() as session:
        cid = uuid.UUID(result["id"])
        run = await session.scalar(select(CampaignRun).where(CampaignRun.campaign_id == cid))
    assert await runner.campaign_tick(cid, run.run_id, workspace_tenant_id=TID, owner=uuid.uuid4()) is False
    linked.dial.assert_not_awaited()
    async with linked.db() as session:
        assert (await session.get(FollowUpJob, linked.job_id)).status == "expired"


async def test_generic_campaign_does_not_jump_a_reserved_callback(linked, monkeypatch):
    cid, rid = await seeded_campaign(linked.db, 1)
    async with linked.db() as session:
        row = await session.scalar(select(CampaignContact).where(CampaignContact.campaign_id == cid))
        row.phone_e164 = PHONE
        await session.commit()
    dial = AsyncMock()
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", dial)
    await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=uuid.uuid4())
    dial.assert_not_awaited()
    async with linked.db() as session:
        row = await session.scalar(select(CampaignContact).where(CampaignContact.campaign_id == cid))
        assert row.status == "followup_reserved"


@pytest.mark.parametrize("mode", ["review", "automatic"])
@pytest.mark.parametrize("language", ["en-IN", "te-IN", "hi-IN"])
async def test_session_capabilities_load_saved_callback_policy(linked, monkeypatch, mode, language):
    from server.brain import capabilities
    from server.brain.agent_service import agent_service
    async with linked.db() as session:
        row = await session.scalar(select(AgentFollowUpPolicy).where(AgentFollowUpPolicy.tenant_id == TID))
        row.config = {**row.config, "callbackMode": mode}
        await session.commit()
    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: linked.db)
    monkeypatch.setattr(agent_service, "get_agent", AsyncMock(return_value={"tenant_id": str(TID), "languages": [language]}))
    monkeypatch.setattr(capabilities, "agent_available_tools", AsyncMock(return_value=[]))
    from server.brain.compiled_brain_artifact import assemble_unified_brain
    source = assemble_unified_brain(language="en-IN", script="Answer business questions and record enquiries.")
    text = await capabilities.compile_agent_capabilities(source, str(AID))
    assert f"callback_dispatch: {mode}" in text
    assert "do_not_call" in text
    assert text.count("--- CALL CAPABILITIES ---") == 1
    import re
    assert re.findall(r"--- SPOKEN LANGUAGE \(([^)]+)\) ---", text) == [language]


@pytest.mark.parametrize("changed", [False, True])
async def test_language_save_recompiles_only_when_the_language_changes(linked, monkeypatch, changed):
    from server.brain.agent_service import AgentService
    from server.db.models.entities import Agent
    async with linked.db() as session:
        (await session.get(Agent, AID)).languages = ["en-IN"]
        await session.commit()
    monkeypatch.setattr("server.brain.agent_service.get_session_factory", lambda: linked.db)
    monkeypatch.setattr("server.services.saas.voice_stack_profiles.validate_agent_language_for_tier", AsyncMock())
    service = AgentService()
    compile_next = Mock()
    monkeypatch.setattr(service, "_schedule_disclosure_recompile", compile_next)
    result = await service.patch_agent(str(AID), {"languages": ["te-IN" if changed else "en-IN"]}, tenant_id=str(TID))
    assert result["languages"] == ["te-IN" if changed else "en-IN"]
    assert compile_next.call_count == int(changed)


def test_campaign_hours_use_the_opening_day_and_respect_holidays():
    profile = {"timezone": "UTC", "business_hours": {"wed": [{"open": "22:00", "close": "02:00"}]}}
    assert not runner.within_agent_hours(profile, datetime(2026, 11, 4, 1, tzinfo=timezone.utc))
    assert runner.within_agent_hours(profile, datetime(2026, 11, 5, 1, tzinfo=timezone.utc))
    profile["business_hours"]["closed"] = ["2026-11-05"]
    assert not runner.within_agent_hours(profile, datetime(2026, 11, 5, 1, tzinfo=timezone.utc))


async def test_reviewed_campaign_job_waits_for_explicit_campaign_resume(linked):
    result = await create_linked(linked, autoStart=True)
    cid = uuid.UUID(result["id"])
    from server.db.models.phase5_models import Campaign
    async with linked.db() as session:
        camp = await session.get(Campaign, cid)
        camp.status = "requires_review"
        run = await session.scalar(select(CampaignRun).where(CampaignRun.campaign_id == cid))
        run.status = "requires_review"
        row = await session.get(FollowUpJob, linked.job_id)
        row.due_at = AT
        await session.commit()
    await followups.run_once()
    linked.dial.assert_not_awaited()
    await routes.start_campaign(str(cid), linked.ctx)
    await followups._process(linked.job_id)
    linked.dial.assert_awaited_once()


async def test_pre_dial_rechecks_the_window_after_contact_claim(linked, monkeypatch):
    from server.db.models.phase5_models import Campaign
    cid, rid = await seeded_campaign(linked.db, 1)
    async with linked.db() as session:
        camp = await session.get(Campaign, cid)
        camp.schedule = {"calling_window": {"start": "10:00", "end": "11:00", "timezone": "UTC"}}
        await session.commit()
    original = runner._dial_claim
    async def delayed_claim(*args, **kwargs):
        linked.clock[0] = AT + timedelta(hours=1)
        await original(*args, **kwargs)
    monkeypatch.setattr(runner, "_dial_claim", delayed_claim)
    dial = AsyncMock()
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", dial)
    await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=uuid.uuid4())
    dial.assert_not_awaited()
    async with linked.db() as session:
        contact = await session.scalar(select(CampaignContact).where(CampaignContact.campaign_id == cid))
        assert contact.status == "pending" and contact.attempts == 0


async def test_campaign_start_can_delay_but_never_advance_a_requested_callback(linked):
    await create_linked(linked, autoStart=True, startsAt=AT + timedelta(hours=8))
    linked.clock[0] = AT + timedelta(hours=6)
    await followups._process(linked.job_id)
    linked.dial.assert_not_awaited()
    linked.clock[0] = AT + timedelta(hours=8)
    await followups._process(linked.job_id)
    linked.dial.assert_awaited_once()


async def test_invalid_recipient_timezone_requires_review_without_a_dial(linked, monkeypatch):
    cid, rid = await seeded_campaign(linked.db, 1)
    async with linked.db() as session:
        contact = await session.scalar(select(CampaignContact).where(CampaignContact.campaign_id == cid))
        contact.metadata_ = {"timezone": "not-a-timezone"}
        await session.commit()
    dial = AsyncMock()
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", dial)
    assert await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=uuid.uuid4()) is False
    dial.assert_not_awaited()
    async with linked.db() as session:
        contact = await session.scalar(select(CampaignContact).where(CampaignContact.campaign_id == cid))
        assert contact.status == "requires_review"


async def test_optout_during_voice_preparation_prevents_the_actual_carrier_post(linked, monkeypatch):
    from server.auth.session import SessionData
    from server.brain.agent_service import agent_service
    from server.routes import dev_telephony as dialroutes
    from server.services import vobiz_client as carrier
    from server.services.saas import predial_policy
    from server.services.pstn_prewarm import PstnPrewarmRegistry
    from server.services.saas.tenant_guard import SubscriberPrincipal
    monkeypatch.setattr(predial_policy, "get_session_factory", lambda: linked.db)
    monkeypatch.setattr(predial_policy, "datetime", routes.datetime)
    registry, tokens = carrier.VobizCallRegistry(), carrier.VobizStreamTokens()
    monkeypatch.setattr(registry, "_redis", lambda: None)
    monkeypatch.setattr(tokens, "_redis", lambda: None)
    monkeypatch.setattr(tokens, "_shared_required", lambda: False)
    monkeypatch.setattr(carrier, "vobiz_call_registry", registry)
    monkeypatch.setattr(carrier, "vobiz_stream_tokens", tokens)
    fake = SimpleNamespace(account_tenant_id=str(TID), create_outbound_call=AsyncMock(),
                           build_stream_ws_url=lambda **kw: "wss://isolated.invalid/media")
    monkeypatch.setattr("server.services.saas.voice_kyc_service.vobiz_client_for_number", AsyncMock(return_value=(fake, "tenant")))
    monkeypatch.setattr(agent_service, "get_agent", AsyncMock(return_value={}))
    monkeypatch.setattr("server.config.urls.public_api_base", lambda: "https://isolated.invalid")
    monkeypatch.setattr(dialroutes, "_outbound_pstn_context", lambda _: ("medium", "te-IN", {}, []))
    monkeypatch.setattr(dialroutes, "_resolve_outbound_source_session", lambda _: (None, False))
    cancel = AsyncMock()
    monkeypatch.setattr(PstnPrewarmRegistry, "cancel", cancel)
    async def prepare(*args, **kwargs):
        await routes.add_dnc(routes.DncBody(phoneE164=PHONE), linked.ctx)
    monkeypatch.setattr(PstnPrewarmRegistry, "prepare", prepare)
    body = dialroutes.OutboundTestBody(agentId=str(AID), toE164=PHONE, fromE164="+12025550124")
    principal = SubscriberPrincipal(UID, TID, "customer_admin", "audit@example.test")
    async def final_check():
        await predial_policy.assert_predial_policy(principal, agent_id=str(AID), phone=PHONE)
    body._before_dial_check = final_check
    result = await dialroutes._outbound_vobiz(body, SessionData(kind="app", subject=str(UID), tenant_id=str(TID),
                                                             role="customer_admin", issued_at=0))
    assert result["ok"] is False and result["code"] == "predial_policy_changed"
    fake.create_outbound_call.assert_not_awaited()
    cancel.assert_awaited_once()


def test_client_json_cannot_inject_a_predial_callback():
    from server.routes.dev_telephony import OutboundTestBody
    body = OutboundTestBody(agentId=str(AID), toE164=PHONE, _before_dial_check="untrusted")
    assert body._before_dial_check is None
    assert "_before_dial_check" not in body.model_dump()


async def test_valid_final_policy_check_allows_an_unchanged_call(linked, monkeypatch):
    from server.services.saas import predial_policy
    from server.services.saas.tenant_guard import SubscriberPrincipal
    monkeypatch.setattr(predial_policy, "get_session_factory", lambda: linked.db)
    monkeypatch.setattr(predial_policy, "datetime", routes.datetime)
    wallet = AsyncMock()
    monkeypatch.setattr("server.services.saas.billing_wallet_service.assert_wallet_allows_pstn", wallet)
    await predial_policy.assert_predial_policy(SubscriberPrincipal(UID, TID, "customer_admin", "audit@example.test"),
                                              agent_id=str(AID), phone=PHONE)
    wallet.assert_awaited_once_with(TID)


@pytest.mark.parametrize("change", ["unchanged", "paused", "policy_disabled", "stale_reservation"])
async def test_final_policy_check_uses_current_followup_and_campaign_state(linked, monkeypatch, change):
    from server.db.models.phase5_models import Campaign
    from server.services.saas import predial_policy
    from server.services.saas.tenant_guard import SubscriberPrincipal
    result = await create_linked(linked, autoStart=True)
    cid = uuid.UUID(result["id"])
    linked.clock[0] = AT + timedelta(hours=6)
    async with linked.db() as session:
        row = await session.get(FollowUpJob, linked.job_id)
        row.status, row.attempts = "dispatching", 1
        row.payload = {**row.payload, "dispatchSequence": 2 if change == "stale_reservation" else 1}
        target = await session.scalar(select(CampaignContact).where(CampaignContact.campaign_id == cid))
        contact = {**target.metadata_, "campaign_id": str(cid), "contact_id": str(target.id)}
        if change == "paused":
            (await session.get(Campaign, cid)).status = "paused"
        if change == "policy_disabled":
            policy = await session.scalar(select(AgentFollowUpPolicy).where(AgentFollowUpPolicy.tenant_id == TID))
            policy.config = {**policy.config, "enabled": False}
        await session.commit()
    monkeypatch.setattr(predial_policy, "get_session_factory", lambda: linked.db)
    monkeypatch.setattr(predial_policy, "datetime", routes.datetime)
    wallet = AsyncMock()
    monkeypatch.setattr("server.services.saas.billing_wallet_service.assert_wallet_allows_pstn", wallet)
    args = dict(agent_id=str(AID), phone=PHONE, contact=contact, request_id=f"fu:{linked.job_id}:1")
    principal = SubscriberPrincipal(UID, TID, "customer_admin", "audit@example.test")
    if change == "unchanged":
        await predial_policy.assert_predial_policy(principal, **args)
        wallet.assert_awaited_once()
    else:
        with pytest.raises(HTTPException) as exc:
            await predial_policy.assert_predial_policy(principal, **args)
        assert exc.value.status_code == 409
        wallet.assert_not_awaited()


async def test_secondary_dial_checks_after_preparation_and_cleans_up(monkeypatch):
    from server.routes import dev_telephony as dialroutes
    from server.auth.session import SessionData
    from server.brain.agent_service import agent_service
    from server.services import telnyx_client as carrier
    from server.services.pstn_prewarm import PstnPrewarmRegistry
    fake = SimpleNamespace(create_outbound_call=AsyncMock(), build_stream_ws_url=lambda **kw: "wss://isolated.invalid/media")
    monkeypatch.setattr(carrier, "TelnyxClient", lambda: fake)
    monkeypatch.setattr(carrier, "telnyx_stream_tokens", SimpleNamespace(create=lambda **kw: "synthetic-token"))
    monkeypatch.setattr(agent_service, "get_agent", AsyncMock(return_value={}))
    monkeypatch.setattr("server.services.production_canary.assert_canary_outbound_allowed", lambda _: None)
    monkeypatch.setattr("server.services.outbound_dial_guard.peek_reusable_telnyx_call", lambda _: None)
    monkeypatch.setattr(dialroutes, "_hangup_active_telnyx_to", AsyncMock())
    monkeypatch.setattr(dialroutes, "_outbound_pstn_context", lambda _: ("medium", "te-IN", {}, []))
    monkeypatch.setattr(dialroutes, "_resolve_outbound_source_session", lambda _: (None, False))
    order = []
    async def prepare(*args, **kwargs):
        order.append("prepared")
    async def late_check():
        order.append("policy_checked")
        raise HTTPException(409, "Campaign paused during preparation")
    monkeypatch.setattr(PstnPrewarmRegistry, "prepare", prepare)
    cancelled = AsyncMock()
    monkeypatch.setattr(PstnPrewarmRegistry, "cancel", cancelled)
    body = dialroutes.OutboundTestBody(agentId=str(AID), toE164=PHONE, fromE164="+12025550124")
    body._before_dial_check = late_check
    result = await dialroutes._outbound_telnyx(body, SessionData(kind="app", subject=str(UID), tenant_id=str(TID),
                                                               role="customer_admin", issued_at=0))
    assert order == ["prepared", "policy_checked"]
    assert result["code"] == "predial_policy_changed"
    fake.create_outbound_call.assert_not_awaited()
    cancelled.assert_awaited_once()
