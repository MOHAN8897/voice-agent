"""No live carrier/LLM: durable permissions, safety gates, retries and timing boundaries."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.db.models.entities import Agent, Call, CallAttempt, CallCallback, Tenant
from server.db.models.followup_models import AgentFollowUpPolicy, FollowUpJob, LeadAssessment
from server.db.models.phase5_models import AgentTelephonyProfile, DncEntry, Campaign, CampaignContact, CampaignRun
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction, Lead, TenantMembership, User
from server.services.saas import followup_service as svc
from server.services.saas.followup_policy import FollowUpConfig, extracted_due, local_instant, next_allowed
from server.services.saas.lead_scoring import score_outcome
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.services.saas.call_callback_service import request_callback as REAL_REQUEST_CALLBACK

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
PHONE = "+12025550123"


@pytest.fixture
async def queue(monkeypatch, tmp_path):
    from server.db import connection
    from server.services.saas import telephony_profile, call_callback_service, callback_request_service, lead_scoring, tenant_guard, followup_retention
    tables = [Tenant, Agent, User, TenantMembership, Call, CallAttempt, CallCallback, AgentTelephonyProfile,
              DncEntry, Lead, BillingWallet, BillingWalletTransaction, AgentFollowUpPolicy, FollowUpJob, LeadAssessment,
              Campaign, CampaignContact, CampaignRun]
    changed = [(c, c.type) for model in tables for c in model.__table__.columns if isinstance(c.type, (ARRAY, JSONB))]
    for c, _ in changed:
        c.type = JSON()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue.db'}")
    try:
        async with engine.begin() as conn:
            for model in tables:
                await conn.run_sync(lambda sync, table=model.__table__: table.create(sync))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        for module in (svc, connection, telephony_profile, call_callback_service, callback_request_service, lead_scoring, tenant_guard, followup_retention):
            monkeypatch.setattr(module, "get_session_factory", lambda: factory)
        monkeypatch.setattr(svc, "now_utc", lambda: NOW)
        principal = SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "customer_admin", "queue@example.invalid")
        aid = uuid.uuid4()
        async with factory() as session:
            session.add_all([Tenant(tenant_id=principal.tenant_id, name="Synthetic queue"),
                Agent(agent_id=aid, tenant_id=principal.tenant_id, name="Synthetic agent"),
                User(user_id=principal.user_id, email=principal.email, password_hash="test-only", status="active", email_verified_at=NOW),
                TenantMembership(user_id=principal.user_id, tenant_id=principal.tenant_id, role=principal.role)])
            await session.commit()
        dial = AsyncMock(return_value={"ok": True, "callControlId": "synthetic-control"})
        monkeypatch.setattr(call_callback_service, "request_callback", dial)
        yield SimpleNamespace(factory=factory, principal=principal, aid=aid, dial=dial)
    finally:
        await engine.dispose()
        for c, original in changed:
            c.type = original


async def enable(queue, **kwargs):
    cfg = FollowUpConfig(enabled=True, timezone="UTC", callbackMode="automatic", missedMode="automatic", **kwargs)
    return await svc.save_policy(queue.principal, queue.aid, cfg, 0, True)


async def job(queue, **kwargs):
    row = FollowUpJob(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, origin_key=str(uuid.uuid4()),
        source_id=str(uuid.uuid4()), kind="callback", phone=PHONE, status="scheduled", reason="requested_time_resolved",
        due_at=NOW, expires_at=NOW + timedelta(days=2), authorized_by=queue.principal.user_id,
        billing_tenant_id=queue.principal.tenant_id, payload={}, created_at=NOW, updated_at=NOW)
    for k, v in kwargs.items():
        setattr(row, k, v)
    async with queue.factory() as session:
        session.add(row)
        await session.commit()
    return row


def test_defaults_require_permission_and_validate_config():
    cfg = FollowUpConfig()
    assert not cfg.enabled and cfg.callbackMode == "review" and cfg.missedMode == "off"
    for patch in ({"weekdays": []}, {"timezone": "Mars/Base"}, {"maxAttempts": 4},
                  {"scoreWeights": {"interest": 100}}, {"startTime": "18:00", "endTime": "09:00"}):
        with pytest.raises(ValueError):
            FollowUpConfig(**patch)


def test_timing_analysis_uses_configured_analyzer_without_mutating_voice_tiers(monkeypatch):
    from server.services.saas.followup_policy import timing_model_snapshot
    from server.realtime import models
    selected = SimpleNamespace(provider="sarvam", model="sarvam-105b-conversations", options={"api_mode": "chat_completions_v1"})
    monkeypatch.setattr(models, "http_openai_model", lambda: "configured-analysis-model")
    assert timing_model_snapshot(selected)["model"] == "configured-analysis-model"
    assert selected.model == "sarvam-105b-conversations"
    native = SimpleNamespace(provider="gemini", model="gemini-3.8-live", options={"api_mode": "websocket"})
    assert timing_model_snapshot(native)["model"] == "configured-analysis-model"
    assert native.model == "gemini-3.8-live"


@pytest.mark.parametrize("text", ["call after 6 hours", "ఆరు గంటల తర్వాత కాల్ చేయండి", "छह घंटे बाद कॉल करें"])
def test_grounded_relative_time_in_any_language(text):
    assert extracted_due({"kind": "relative", "delay_minutes": 360, "evidence": text}, text, NOW, FollowUpConfig()) == NOW + timedelta(hours=6)
    assert extracted_due({"kind": "relative", "delay_minutes": 360, "evidence": "invented"}, text, NOW, FollowUpConfig()) is None


def test_ambiguous_and_nonexistent_dst_times_require_review():
    for value in ("2026-11-01T01:30", "2026-03-08T02:30"):
        with pytest.raises(ValueError):
            local_instant(value, "America/New_York")
    assert local_instant("2026-11-01T01:30-04:00", "America/New_York").hour == 5


def test_windows_holidays_and_agent_hours_intersect():
    cfg = FollowUpConfig(timezone="UTC", weekdays=[0, 1, 2, 3, 4])
    assert next_allowed(NOW, cfg) == NOW
    profile = {"business_hours": {"wed": [{"open": "12:00", "close": "13:00"}]}, "timezone": "UTC"}
    assert next_allowed(NOW, cfg, profile) == NOW.replace(hour=12)
    profile["business_hours"]["closed"] = ["2026-10-28"]
    assert next_allowed(NOW, cfg, profile).date().isoformat() == "2026-11-04"


def test_overnight_hours_belong_to_the_previous_day():
    from server.services.saas.followup_policy import within_profile_hours
    hours = {"mon": [{"open": "22:00", "close": "02:00"}]}
    assert within_profile_hours(datetime(2026, 10, 27, 1, tzinfo=timezone.utc), hours, "UTC")
    assert not within_profile_hours(datetime(2026, 10, 26, 1, tzinfo=timezone.utc), hours, "UTC")


async def test_explicit_target_keeps_original_call_identity_and_rejects_foreign_call(queue):
    from server.services.saas.call_callback_service import _resolve_target
    cid = uuid.uuid4()
    async with queue.factory() as session:
        session.add(Call(call_id=cid, tenant_id=queue.principal.tenant_id, agent_id=queue.aid,
            combination_id="test", storage_path="test", status_tags=[]))
        await session.commit()
    target, agent, source = await _resolve_target(queue.principal, call_id=str(cid), to_e164=PHONE)
    assert (target, agent, source) == (PHONE, str(queue.aid), "call")
    foreign = SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "customer_admin", "foreign@example.invalid")
    with pytest.raises(HTTPException) as denied:
        await _resolve_target(foreign, call_id=str(cid), to_e164=PHONE)
    assert denied.value.status_code == 404


async def test_requested_callback_is_atomic_and_resolves_to_a_durable_time(queue, monkeypatch):
    await enable(queue)
    cid = uuid.uuid4()
    async with queue.factory() as session:
        callback = CallCallback(callback_id=uuid.uuid4(), tenant_id=queue.principal.tenant_id, agent_id=str(queue.aid),
            original_call_id=cid, to_e164=PHONE, dial_request_id="requested:test", mode="requested", status="requested")
        session.add(callback)
        await session.flush()
        await svc.capture_request(session, callback, request_text="Call after six hours", llm={"provider": "fixture", "model": "selected"})
        await session.commit()
    monkeypatch.setattr(svc, "_extract_time", AsyncMock(return_value=NOW + timedelta(hours=6)))
    await svc.run_once()
    queue.dial.assert_not_awaited()
    async with queue.factory() as session:
        row = await session.scalar(select(FollowUpJob))
        assert row.status == "scheduled" and row.due_at.replace(tzinfo=timezone.utc) == NOW + timedelta(hours=6)
        assert row.payload["requestText"] == "Call after six hours"


async def test_retries_require_confirmed_no_answer_and_respect_current_attempt_limit(queue):
    await enable(queue, maxAttempts=2)
    row = await job(queue)
    await svc.run_once()
    async with queue.factory() as session:
        session.add(CallAttempt(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, direction="outbound",
            provider_call_control_id="synthetic-control", status="missed", from_number="+12025550124", to_number=PHONE,
            started_at=NOW, ended_at=NOW, created_at=NOW))
        await session.commit()
    await svc.run_once()
    async with queue.factory() as session:
        pending = await session.get(FollowUpJob, row.id)
        assert pending.status == "scheduled" and pending.reason == "retry_unanswered"
        pending.due_at = NOW
        policy = await session.scalar(select(AgentFollowUpPolicy))
        policy.config = {**policy.config, "maxAttempts": 1}
        await session.commit()
    await svc.run_once()
    queue.dial.assert_awaited_once()


async def test_manual_callback_cannot_duplicate_a_dispatch(queue):
    from server.services.saas.call_callback_service import _cancel_queued_followups
    await enable(queue)
    row = await job(queue, status="dispatching")
    with pytest.raises(HTTPException) as denied:
        await _cancel_queued_followups(queue.principal.tenant_id, row.source_id)
    assert denied.value.status_code == 409


async def test_migration_upgrade_and_rollback_on_disposable_database(queue):
    import importlib
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    migration = importlib.import_module("server.db.migrations.versions.047_durable_followups")
    async with queue.factory().bind.begin() as connection:
        def check(sync):
            for table in (LeadAssessment.__table__, FollowUpJob.__table__, AgentFollowUpPolicy.__table__):
                table.drop(sync)
            with Operations.context(MigrationContext.configure(sync)):
                migration.upgrade()
                migration.downgrade()
                migration.upgrade()
        await connection.run_sync(check)


async def test_permission_revision_and_disable_cancel_pending(queue):
    with pytest.raises(HTTPException) as error:
        await svc.save_policy(queue.principal, queue.aid, FollowUpConfig(enabled=True), 0, False)
    assert error.value.status_code == 422
    saved = await enable(queue)
    assert saved["revision"] == 1 and saved["authorizedAt"]
    row = await job(queue)
    with pytest.raises(HTTPException) as stale:
        await svc.save_policy(queue.principal, queue.aid, FollowUpConfig(), 0, True)
    assert stale.value.status_code == 409
    await svc.save_policy(queue.principal, queue.aid, FollowUpConfig(), 1, False)
    async with queue.factory() as session:
        assert (await session.get(FollowUpJob, row.id)).status == "cancelled"
    await svc.run_once()
    queue.dial.assert_not_awaited()


async def test_dispatch_exactly_once_and_resume_after_restart(queue):
    await enable(queue)
    row = await job(queue)
    assert await svc.run_once() == 1
    assert await svc.run_once() == 0
    queue.dial.assert_awaited_once()
    assert queue.dial.call_args.kwargs["dial_request_id"] == f"fu:{row.id}:1"
    async with queue.factory() as session:
        assert (await session.get(FollowUpJob, row.id)).status == "dialed"


@pytest.mark.parametrize("block", ["dnc", "converted", "membership", "expired"])
async def test_dispatch_rechecks_safety(queue, block):
    await enable(queue)
    row = await job(queue, expires_at=NOW - timedelta(seconds=1) if block == "expired" else NOW + timedelta(days=2))
    async with queue.factory() as session:
        if block == "dnc":
            session.add(DncEntry(tenant_id=queue.principal.tenant_id, phone_e164=PHONE, active=True))
        elif block == "converted":
            session.add(Lead(tenant_id=queue.principal.tenant_id, phone=PHONE, stage="converted", name="Converted"))
        elif block == "membership":
            member = await session.scalar(select(TenantMembership))
            await session.delete(member)
        await session.commit()
    await svc.run_once()
    queue.dial.assert_not_awaited()
    async with queue.factory() as session:
        assert (await session.get(FollowUpJob, row.id)).status in ("suppressed", "needs_review", "expired")


async def test_uncertain_dispatch_never_retries_automatically(queue):
    await enable(queue)
    queue.dial.side_effect = TimeoutError()
    row = await job(queue)
    await svc.run_once()
    await svc.run_once()
    queue.dial.assert_awaited_once()
    async with queue.factory() as session:
        assert (await session.get(FollowUpJob, row.id)).reason == "dispatch_uncertain_do_not_redial"


async def test_expired_dispatch_lease_requires_review(queue):
    await enable(queue)
    row = await job(queue, status="dispatching", lease_until=NOW - timedelta(minutes=1))
    await svc.run_once()
    queue.dial.assert_not_awaited()
    async with queue.factory() as session:
        assert (await session.get(FollowUpJob, row.id)).status == "needs_review"


async def test_missed_capture_is_delayed_deduplicated_and_inbound_only(queue):
    await enable(queue)
    async with queue.factory() as session:
        for direction, status, answered in (("inbound", "missed", False), ("outbound", "missed", False), ("inbound", "declined", False), ("inbound", "missed", True)):
            session.add(CallAttempt(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, provider_call_control_id=str(uuid.uuid4()),
                direction=direction, status=status, from_number=PHONE, started_at=NOW, created_at=NOW, ended_at=NOW,
                answered_at=NOW if answered else None))
        await session.commit()
    await svc.run_once()
    await svc.run_once()
    queue.dial.assert_not_awaited()
    async with queue.factory() as session:
        rows = (await session.scalars(select(FollowUpJob))).all()
        assert len(rows) == 1 and rows[0].kind == "missed"
        assert rows[0].due_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=30)


async def test_review_requires_time_permission_and_tenant_scope(queue):
    await enable(queue)
    row = await job(queue, status="needs_review")
    foreign = SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "customer_admin", "foreign@example.invalid")
    with pytest.raises(HTTPException) as denied:
        await svc.edit_job(foreign, row.id, "schedule", NOW + timedelta(hours=1), NOW)
    assert denied.value.status_code == 404
    with pytest.raises(HTTPException):
        await svc.edit_job(queue.principal, row.id, "schedule", None, NOW)
    result = await svc.edit_job(queue.principal, row.id, "schedule", NOW + timedelta(hours=1), NOW)
    assert result["status"] == "scheduled"


def test_scores_are_explainable_configurable_and_never_claim_conversion():
    result = score_outcome({"disposition": "interested", "disposition_confidence": .9,
        "facts": {"product": "Service", "callback_when": "Tomorrow", "phone": PHONE, "gender": "ignored"}})
    assert result["score"] == 100 and result["band"] == "hot"
    assert sum(c["points"] for c in result["components"]) == result["score"]
    assert score_outcome({"disposition": "interested", "disposition_confidence": .2})["score"] is None
    assert score_outcome({"disposition": "not_interested", "disposition_confidence": .9})["band"] == "disqualified"
    assert score_outcome({"disposition": "converted", "disposition_confidence": .9})["band"] != "converted"


async def test_performance_counts_over_100_and_500_rows_with_real_charge_cpl(queue):
    from server.services.saas.agent_performance import performance
    async with queue.factory() as session:
        for _ in range(605):
            call = Call(call_id=uuid.uuid4(), tenant_id=queue.principal.tenant_id, agent_id=queue.aid,
                combination_id="synthetic", storage_path="test", started_at=NOW, ended_at=NOW + timedelta(seconds=45),
                duration_sec=45, channel="pstn", status="outbound", is_test=False, status_tags=[])
            session.add(call)
            session.add(BillingWalletTransaction(tenant_id=queue.principal.tenant_id, amount_cents=-10,
                amount_inr_paise=0, reference_id=f"call:{call.call_id}", kind="call", created_at=NOW))
        session.add(BillingWallet(tenant_id=queue.principal.tenant_id, currency="usd"))
        session.add(Lead(tenant_id=queue.principal.tenant_id, agent_id=str(queue.aid), name="One", stage="converted", created_at=NOW))
        await session.commit()
    result = await performance(str(queue.principal.tenant_id), str(queue.aid))
    assert result["total"] == result["connected"] == 605
    assert result["avgDurationSec"] == 45 and result["conversionRate"] == 100
    assert result["cost"]["costPerLead"] == 60.5
    assert result["cost"]["complete"]


async def test_callback_journal_uses_exactly_one_original_foreign_key(queue):
    from server.services.saas.call_callback_service import _create_callback_row
    for source in ("call", "attempt"):
        origin = str(uuid.uuid4())
        request_id = await _create_callback_row(queue.principal, call_id=origin, request_id=source,
            agent_id=str(queue.aid), to_e164=PHONE, from_e164=None, mode="scheduled",
            original_call_id=origin if source == "call" else None)
        async with queue.factory() as session:
            row = await session.scalar(select(CallCallback).where(CallCallback.dial_request_id == request_id))
            assert str(row.original_call_id if source == "call" else row.original_attempt_id) == origin
            assert (row.original_attempt_id if source == "call" else row.original_call_id) is None


async def test_journal_failure_prevents_paid_dial(queue, monkeypatch):
    from server.services.saas import call_callback_service as callbacks, telephony_orchestrator
    class FailedSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            pass
        def add(self, row):
            pass
        async def commit(self):
            raise RuntimeError("synthetic storage outage")
        async def rollback(self):
            pass
    monkeypatch.setattr(callbacks, "get_session_factory", lambda: FailedSession)
    monkeypatch.setattr(callbacks, "_resolve_target", AsyncMock(return_value=(PHONE, str(queue.aid), "attempt")))
    monkeypatch.setattr(callbacks, "resolve_workspace_agent", AsyncMock(return_value={}))
    monkeypatch.setattr(callbacks, "_existing_callback", AsyncMock(return_value=None))
    outbound = AsyncMock()
    monkeypatch.setattr(telephony_orchestrator, "subscriber_outbound", outbound)
    with pytest.raises(HTTPException) as failure:
        await REAL_REQUEST_CALLBACK(queue.principal, call_id=str(uuid.uuid4()), agent_id=str(queue.aid), mode="scheduled")
    assert failure.value.status_code == 503
    outbound.assert_not_awaited()


async def test_later_rejection_reassesses_existing_lead_without_changing_stage(queue):
    from server.services.saas.lead_scoring import persist_assessment, assess_existing_contact
    lid = uuid.uuid4()
    async with queue.factory() as session:
        session.add(Lead(lead_id=lid, tenant_id=queue.principal.tenant_id, agent_id=str(queue.aid), name="Known", phone=PHONE, stage="qualified"))
        await session.commit()
    await persist_assessment(str(queue.principal.tenant_id), str(queue.aid), str(lid), "positive",
        {"disposition": "qualified", "disposition_confidence": .9}, at=NOW - timedelta(hours=1))
    result = await assess_existing_contact({"tenant_id": str(queue.principal.tenant_id), "agent_id": str(queue.aid),
        "direction": "outbound", "callee_e164": PHONE, "ended_at": NOW.isoformat()}, "rejected",
        {"disposition": "not_interested", "disposition_confidence": .9})
    assert result["score"] == 0 and result["band"] == "disqualified"
    async with queue.factory() as session:
        assert (await session.get(Lead, lid)).stage == "qualified"
    stale = await persist_assessment(str(queue.principal.tenant_id), str(queue.aid), str(lid), "old",
        {"disposition": "interested", "disposition_confidence": .9}, at=NOW - timedelta(hours=2))
    assert stale["band"] == "disqualified"


def test_only_recorded_caller_optout_controls_call_tag():
    from server.call.outcome_schema import derive_status_tags
    assert "signal:do_not_call" not in derive_status_tags("not_interested", {}, model_tags=["signal:do_not_call"])
    tags = derive_status_tags("interested", {}, contact_preference="do_not_call", next_action="Call back", model_tags=["signal:ready_to_buy"])
    assert "signal:do_not_call" in tags and "followup:callback" not in tags
    assert score_outcome({"contact_preference": "do_not_call", "disposition": "no_outcome"})["band"] == "disqualified"


async def test_followup_api_enforces_permission_and_returns_persisted_settings(queue):
    import httpx
    from fastapi import FastAPI
    from server.routes import app_followups
    from server.auth.subscriber_dependencies import require_subscriber_jwt
    app = FastAPI()
    app.include_router(app_followups.router)
    app.dependency_overrides[require_subscriber_jwt] = lambda: queue.principal
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as client:
        response = await client.get(f"/api/agents/{queue.aid}/follow-up-policy")
        assert response.status_code == 200, response.text
        assert response.json()["config"]["enabled"] is False
        write = {"config": {"enabled": True}, "revision": 0, "acknowledgeCharges": True}
        assert (await client.put(f"/api/agents/{queue.aid}/follow-up-policy", json=write)).status_code == 200
        viewer = SubscriberPrincipal(queue.principal.user_id, queue.principal.tenant_id, "customer_viewer", queue.principal.email)
        app.dependency_overrides[require_subscriber_jwt] = lambda: viewer
        assert (await client.put(f"/api/agents/{queue.aid}/follow-up-policy", json=write)).status_code == 403
        assert (await client.get("/api/follow-ups")).status_code == 200


async def test_export_and_purge_include_new_data_without_crossing_tenants_or_exposing_internals(queue):
    from server.services.saas.followup_retention import export_followup_data, purge_followup_data
    await enable(queue)
    owned = await job(queue, payload={"llm": {"provider": "internal-model"}, "requestText": "Call later"}, control_id="private-network-id")
    other = await job(queue, tenant_id=uuid.uuid4())
    exported = await export_followup_data(queue.principal.tenant_id)
    assert [j["id"] for j in exported["jobs"]] == [str(owned.id)]
    import json
    assert "private-network-id" not in json.dumps(exported) and "internal-model" not in json.dumps(exported)
    await purge_followup_data(queue.principal.tenant_id)
    async with queue.factory() as session:
        assert await session.get(FollowUpJob, owned.id) is None
        assert await session.get(FollowUpJob, other.id) is not None


async def test_quarantined_workspace_cannot_dispatch_followups(queue):
    await enable(queue)
    await job(queue)
    async with queue.factory() as session:
        tenant = await session.get(Tenant, queue.principal.tenant_id)
        tenant.status = "quarantined"
        await session.commit()
    await svc.run_once()
    queue.dial.assert_not_awaited()


async def test_no_dispatch_even_seconds_before_calling_window(queue, monkeypatch):
    edge = NOW.replace(hour=8, minute=59, second=30)
    monkeypatch.setattr(svc, "now_utc", lambda: edge)
    await enable(queue)
    row = await job(queue, due_at=edge, created_at=edge)
    await svc.run_once()
    queue.dial.assert_not_awaited()
    async with queue.factory() as session:
        saved = await session.get(FollowUpJob, row.id)
        assert saved.due_at.replace(tzinfo=timezone.utc) == edge.replace(hour=9, minute=0, second=0)


async def test_explicit_approval_survives_calling_window_adjustment(queue, monkeypatch):
    cfg = FollowUpConfig(enabled=True, callbackMode="review", timezone="UTC")
    await svc.save_policy(queue.principal, queue.aid, cfg, 0, True)
    row = await job(queue, status="needs_review")
    requested = NOW.replace(hour=19)
    await svc.edit_job(queue.principal, row.id, "schedule", requested, NOW)
    monkeypatch.setattr(svc, "now_utc", lambda: requested)
    await svc.run_once()
    queue.dial.assert_not_awaited()
    async with queue.factory() as session:
        adjusted = await session.get(FollowUpJob, row.id)
        assert adjusted.reason == "adjusted_to_calling_window"
        next_window = adjusted.due_at.replace(tzinfo=timezone.utc)
    monkeypatch.setattr(svc, "now_utc", lambda: next_window)
    await svc.run_once()
    queue.dial.assert_awaited_once()


async def test_explicit_approval_survives_permitted_retry(queue, monkeypatch):
    cfg = FollowUpConfig(enabled=True, callbackMode="review", timezone="UTC", maxAttempts=2, cooldownMinutes=30)
    await svc.save_policy(queue.principal, queue.aid, cfg, 0, True)
    row = await job(queue, status="needs_review")
    due = NOW + timedelta(minutes=1)
    await svc.edit_job(queue.principal, row.id, "schedule", due, NOW)
    monkeypatch.setattr(svc, "now_utc", lambda: due)
    await svc.run_once()
    async with queue.factory() as session:
        session.add(CallAttempt(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, direction="outbound",
            provider_call_control_id="synthetic-control", status="missed", from_number="+12025550124", to_number=PHONE,
            started_at=due, ended_at=due, created_at=due))
        await session.commit()
    await svc.run_once()
    async with queue.factory() as session:
        retry_at = (await session.get(FollowUpJob, row.id)).due_at.replace(tzinfo=timezone.utc)
    monkeypatch.setattr(svc, "now_utc", lambda: retry_at)
    await svc.run_once()
    assert queue.dial.await_count == 2


async def test_callback_timing_answer_and_utterance_timestamp_survive_capture(queue, monkeypatch):
    from server.services.saas import callback_request_service
    import server.providers
    import json
    await enable(queue)
    cid = uuid.uuid4()
    stated_at = NOW - timedelta(minutes=5)
    transcript = [
        {"role": "user", "text": "Please call me later", "ts": (NOW - timedelta(minutes=6)).isoformat()},
        {"role": "assistant", "text": "When should I call?", "ts": (stated_at - timedelta(seconds=10)).isoformat()},
        {"role": "user", "text": "ఆరు గంటల తర్వాత", "ts": stated_at.isoformat()},
        {"role": "assistant", "text": "I will save that request.", "ts": (NOW - timedelta(minutes=4)).isoformat()},
        {"role": "user", "text": "Thanks, that is all", "ts": NOW.isoformat()},
    ]
    monkeypatch.setattr(callback_request_service.call_ledger, "read_lines", lambda _: transcript)
    async with queue.factory() as session:
        session.add(Call(call_id=cid, tenant_id=queue.principal.tenant_id, agent_id=queue.aid,
            combination_id="synthetic", storage_path="test", status_tags=[]))
        await session.commit()
    ctx = SimpleNamespace(call_id=str(cid), tenant_id=str(queue.principal.tenant_id), agent_id=str(queue.aid),
        callback_phone=PHONE, callback_when="ఆరు గంటల తర్వాత", resolved_stack=None)
    saved = await callback_request_service.record_callback_request(ctx, "Please call me later")
    assert saved
    async with queue.factory() as session:
        captured = await session.scalar(select(FollowUpJob))
        assert captured.payload["recentTurns"][2]["text"] == "ఆరు గంటల తర్వాత"
        assert svc.job_public(captured)["requestedWhen"] == "ఆరు గంటల తర్వాత"
    adapter = SimpleNamespace(structured_completion=AsyncMock(return_value={"kind": "relative", "delay_minutes": 360, "evidence": "ఆరు గంటల తర్వాత"}))
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: SimpleNamespace(get_llm=lambda _: adapter))
    due = await svc._extract_time(captured, FollowUpConfig(timezone="UTC"))
    assert due == stated_at + timedelta(hours=6)
    prompt = json.loads(adapter.structured_completion.call_args.args[0][1]["content"])
    assert prompt["recentTurns"][1]["role"] == "assistant"


async def test_disconnect_retains_unfinished_callback_for_review_not_automatic_dial(queue, monkeypatch):
    from server.services.saas import callback_request_service
    await enable(queue)
    cid = uuid.uuid4()
    async with queue.factory() as session:
        session.add(Call(call_id=cid, tenant_id=queue.principal.tenant_id, agent_id=queue.aid,
                         combination_id="synthetic", storage_path="test", status_tags=[]))
        await session.commit()
    ctx = SimpleNamespace(call_id=str(cid), tenant_id=str(queue.principal.tenant_id), agent_id=str(queue.aid),
        callback_phone=PHONE, callback_when="in six hours", callback_close_phase="collecting_timing",
        callback_request_text="Please call in six hours", contact_preference="none", resolved_stack=None)
    saved = await callback_request_service.recover_interrupted_callback(ctx)
    assert saved
    async with queue.factory() as session:
        row = await session.scalar(select(FollowUpJob))
        assert row.status == "needs_review" and row.reason == "interrupted_request_review"
    queue.dial.assert_not_awaited()
    ctx.contact_preference = "do_not_call"
    assert await callback_request_service.recover_interrupted_callback(ctx) is None


async def test_historical_missed_import_is_opt_in_review_only_and_idempotent(queue):
    await enable(queue)
    async with queue.factory() as session:
        session.add(CallAttempt(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, direction="inbound",
            provider_call_control_id="historical-missed", status="missed", from_number=PHONE, to_number="+12025550124", started_at=NOW - timedelta(days=1),
            ended_at=NOW - timedelta(days=1), created_at=NOW - timedelta(days=1)))
        await session.commit()
    result = await svc.import_for_review(queue.principal, queue.aid, "missed", 7)
    assert result["imported"] == 1 and result["reviewOnly"] is True
    assert (await svc.import_for_review(queue.principal, queue.aid, "missed", 7))["imported"] == 0
    await svc.run_once()
    queue.dial.assert_not_awaited()


async def test_historical_callback_import_stays_in_review_and_cannot_resurrect_closed_jobs(queue):
    await enable(queue)
    cid, rid = uuid.uuid4(), uuid.uuid4()
    async with queue.factory() as session:
        session.add(Call(call_id=cid, tenant_id=queue.principal.tenant_id, agent_id=queue.aid,
                         combination_id="synthetic", storage_path="test", status_tags=[]))
        await session.flush()
        session.add(CallCallback(callback_id=rid, tenant_id=queue.principal.tenant_id, original_call_id=cid,
            agent_id=str(queue.aid), to_e164=PHONE, mode="requested", status="requested",
            created_at=NOW - timedelta(days=1), dial_request_id=f"requested:{cid}"))
        await session.commit()
    assert (await svc.import_for_review(queue.principal, queue.aid, "callback", 7))["imported"] == 1
    await svc.run_once()
    queue.dial.assert_not_awaited()
    async with queue.factory() as session:
        row = await session.scalar(select(FollowUpJob))
        assert row.status == "needs_review"
        row.status = "cancelled"
        await session.commit()
    assert (await svc.import_for_review(queue.principal, queue.aid, "callback", 7))["imported"] == 0


async def test_known_predial_block_does_not_spend_attempt_and_next_approval_has_new_identity(queue):
    await enable(queue)
    row = await job(queue)
    queue.dial.side_effect = [{"ok": False, "code": "predial_policy_changed"}, {"ok": True, "callControlId": "accepted"}]
    await svc.run_once()
    async with queue.factory() as session:
        saved = await session.get(FollowUpJob, row.id)
        assert saved.status == "needs_review" and saved.attempts == 0
        assert saved.payload["dispatches"] == []
        saved.status, saved.due_at = "scheduled", NOW
        await session.commit()
    await svc.run_once()
    first, second = queue.dial.call_args_list
    assert first.kwargs["dial_request_id"].endswith(":1") and second.kwargs["dial_request_id"].endswith(":2")


async def test_connected_callback_is_removed_from_pending_requests(queue):
    await enable(queue)
    cid, rid = uuid.uuid4(), uuid.uuid4()
    async with queue.factory() as session:
        session.add(Call(call_id=cid, tenant_id=queue.principal.tenant_id, agent_id=queue.aid,
                         combination_id="synthetic", storage_path="test", status_tags=[]))
        await session.flush()
        session.add(CallCallback(callback_id=rid, tenant_id=queue.principal.tenant_id, original_call_id=cid,
            agent_id=str(queue.aid), to_e164=PHONE, mode="requested", status="requested", dial_request_id=f"requested:{cid}"))
        session.add(CallAttempt(tenant_id=queue.principal.tenant_id, agent_id=queue.aid, direction="outbound",
            provider_call_control_id="completed-callback", status="completed", from_number="+12025550124", to_number=PHONE,
            started_at=NOW, answered_at=NOW, ended_at=NOW, created_at=NOW))
        await session.commit()
    row = await job(queue, status="dialed", control_id="completed-callback", attempts=1, payload={"callbackId": str(rid)})
    await svc.run_once()
    async with queue.factory() as session:
        assert (await session.get(CallCallback, rid)).status == "completed"
        assert (await session.get(FollowUpJob, row.id)).status == "completed"


async def test_agent_suggestion_cannot_supply_unspoken_caller_time(queue, monkeypatch):
    import server.providers
    adapter = SimpleNamespace(structured_completion=AsyncMock(return_value={"kind": "relative", "delay_minutes": 360, "evidence": "six hours"}))
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: SimpleNamespace(get_llm=lambda _: adapter))
    row = await job(queue, payload={"requestText": "Call me later", "requestedAt": NOW.isoformat(),
        "llm": {"provider": "fixture", "model": "configured"}, "recentTurns": [
            {"role": "assistant", "text": "Would six hours work?", "at": NOW.isoformat()},
            {"role": "user", "text": "I am not sure", "at": NOW.isoformat()}]})
    assert await svc._extract_time(row, FollowUpConfig(timezone="UTC")) is None


async def test_changed_policy_timezone_requires_review_of_unresolved_timing(queue):
    row = await job(queue, payload={"requestText": "Tomorrow at ten", "requestedAt": NOW.isoformat(), "timezone": "Asia/Kolkata"})
    assert await svc._extract_time(row, FollowUpConfig(timezone="America/New_York")) is None


def test_absolute_offset_cannot_silently_override_recipient_timezone():
    assert extracted_due({"kind": "absolute", "local_datetime": "2026-10-29T10:00:00-07:00", "timezone": None,
        "evidence": "tomorrow at ten Pacific"}, "Call tomorrow at ten Pacific", NOW, FollowUpConfig()) is None


async def test_authorization_rechecks_email_verification(queue, monkeypatch):
    from server.config import env
    await enable(queue)
    await job(queue)
    async with queue.factory() as session:
        user = await session.get(User, queue.principal.user_id)
        user.email_verified_at = None
        await session.commit()
    monkeypatch.setattr(env, "get_settings", lambda: SimpleNamespace(saas_require_email_verification_for_login=True))
    await svc.run_once()
    queue.dial.assert_not_awaited()


async def test_authorization_uses_current_effective_role(queue, monkeypatch):
    from server.services.saas import platform_admins
    await enable(queue)
    await job(queue)
    monkeypatch.setattr(platform_admins, "effective_membership_role", lambda *_: "customer_viewer")
    await svc.run_once()
    queue.dial.assert_not_awaited()
