"""Real PostgreSQL locking/journal tests in an isolated, disposable schema.

Only the final outbound provider boundary and filesystem brain lookup are mocked.
No customer table, phone call, tier setting or billing rate is changed.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from server.config.env import get_settings
from server.db import connection
from server.db.models.entities import Agent, Base, Call, CallAttempt, CallCallback, Tenant
from server.db.models.followup_models import AgentFollowUpPolicy, FollowUpJob, LeadAssessment
from server.db.models.phase5_models import AgentTelephonyProfile, DncEntry, Campaign
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction, Lead, TenantMembership, User
from server.services.saas import callback_request_service, call_callback_service, followup_service as service
from server.services.saas import lead_scoring, telephony_orchestrator, telephony_profile
from server.services.saas.followup_policy import FollowUpConfig
from server.services.saas.tenant_guard import SubscriberPrincipal
import server.services.saas.tenant_guard as tenant_guard

OUT = Path(__file__).resolve().parent
AT = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
PHONE = "+12025550123"
MODELS = [Tenant, Agent, User, TenantMembership, Call, CallAttempt, CallCallback,
          AgentTelephonyProfile, DncEntry, Lead, BillingWallet, BillingWalletTransaction,
          AgentFollowUpPolicy, FollowUpJob, LeadAssessment, Campaign]


async def main():
    database_url = get_settings().database_url or ""
    target = urlsplit(database_url)
    if target.hostname not in ("localhost", "127.0.0.1", "::1") or target.path.lstrip("/") != "voice_agent":
        raise RuntimeError("This verification is restricted to the local development database")
    schema = "codex_followup_audit_" + uuid.uuid4().hex[:12]
    root = create_async_engine(connection._to_async_url(database_url), connect_args={"timeout": 5, "command_timeout": 30})
    engine = None
    patches = []
    created = False
    results = []
    clock = [AT]
    async def outbound(*args, **kwargs):
        await asyncio.sleep(.05)  # Force overlapping workers to contend for real locks.
        return {"ok": True, "call_control_id": "synthetic-control"}
    dial = AsyncMock(side_effect=outbound)
    try:
        async with root.begin() as conn:
            await conn.execute(CreateSchema(schema))
        created = True
        engine = create_async_engine(connection._to_async_url(database_url), connect_args={"timeout": 5,
            "command_timeout": 30, "server_settings": {"search_path": schema + ",pg_catalog", "application_name": "codex_followup_audit"}})
        async with engine.begin() as conn:
            assert (await conn.execute(text("SELECT current_schema()"))).scalar_one() == schema
            await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in MODELS]))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        for module in (service, connection, telephony_profile, call_callback_service, callback_request_service, lead_scoring, tenant_guard):
            patches.append(patch.object(module, "get_session_factory", lambda: factory))
        patches.extend([
            patch.object(service, "now_utc", lambda: clock[0]),
            patch.object(telephony_orchestrator, "subscriber_outbound", dial),
            patch.object(call_callback_service, "resolve_workspace_agent", AsyncMock(return_value={"status": "active"})),
        ])
        for replacement in patches:
            replacement.start()

        async def seed(**overrides):
            # All identifiers resolve exclusively inside this helper-owned schema.
            async with engine.begin() as conn:
                assert (await conn.execute(text("SELECT current_schema()"))).scalar_one() == schema
                await conn.execute(text("TRUNCATE tenants, users CASCADE"))
            clock[0] = AT
            dial.reset_mock()
            dial.side_effect = outbound
            principal = SubscriberPrincipal(uuid.uuid4(), uuid.uuid4(), "customer_admin", "postgres-audit@example.invalid")
            aid, cid = uuid.uuid4(), uuid.uuid4()
            async with factory() as session:
                session.add(Tenant(tenant_id=principal.tenant_id, name="Synthetic audit"))
                session.add(User(user_id=principal.user_id, email=principal.email, password_hash="test-only", email_verified_at=AT, status="active"))
                await session.flush()
                session.add(Agent(agent_id=aid, tenant_id=principal.tenant_id, name="Synthetic audit"))
                session.add(TenantMembership(user_id=principal.user_id, tenant_id=principal.tenant_id, role=principal.role))
                await session.flush()
                session.add(Call(call_id=cid, tenant_id=principal.tenant_id, agent_id=aid,
                    combination_id="synthetic", storage_path="test", status_tags=[]))
                await session.commit()
            cfg = FollowUpConfig.model_validate({"enabled": True, "timezone": "UTC", "callbackMode": "automatic", **overrides})
            await service.save_policy(principal, aid, cfg, 0, True)
            return SimpleNamespace(principal=principal, aid=aid, cid=cid, config=cfg)

        async def scheduled(case, **overrides):
            job = FollowUpJob(tenant_id=case.principal.tenant_id, agent_id=case.aid, origin_key=str(uuid.uuid4()),
                source_id=str(case.cid), kind="callback", phone=PHONE, status="scheduled", reason="requested_time_resolved",
                due_at=clock[0], expires_at=AT + timedelta(days=2), attempts=0, payload={},
                authorized_by=case.principal.user_id, billing_tenant_id=case.principal.tenant_id, created_at=AT, updated_at=AT)
            for key, value in overrides.items():
                setattr(job, key, value)
            async with factory() as session:
                session.add(job)
                await session.commit()
            return job

        case = await seed()
        job = await scheduled(case)
        await asyncio.gather(service.run_once(), service.run_once())
        assert dial.await_count == 1
        async with factory() as session:
            journal = (await session.scalars(select(CallCallback).where(CallCallback.tenant_id == case.principal.tenant_id))).all()
            assert len(journal) == 1 and journal[0].original_call_id == case.cid
            assert journal[0].original_attempt_id is None and journal[0].status == "dialed"
        results.append({"case": "concurrent_workers_same_job_and_real_journal", "pass": True})

        case = await seed()
        await scheduled(case)
        await scheduled(case)
        await asyncio.gather(service.run_once(), service.run_once())
        assert dial.await_count == 1
        async with factory() as session:
            reasons = (await session.scalars(select(FollowUpJob.reason).where(FollowUpJob.tenant_id == case.principal.tenant_id))).all()
            assert "contact_cooldown" in reasons
        results.append({"case": "concurrent_workers_same_number_cooldown", "pass": True})

        case = await seed(missedMode="automatic", missedDelayMinutes=30)
        attempt_id = uuid.uuid4()
        async with factory() as session:
            session.add(CallAttempt(attempt_id=attempt_id, tenant_id=case.principal.tenant_id, agent_id=case.aid,
                direction="inbound", status="missed", from_number=PHONE, provider_call_control_id="synthetic-inbound",
                created_at=AT, started_at=AT, ended_at=AT))
            await session.commit()
        await service.run_once()
        await service.run_once()
        assert dial.await_count == 0
        clock[0] = AT + timedelta(minutes=30)
        await service.run_once()
        assert dial.await_count == 1
        async with factory() as session:
            journal = await session.scalar(select(CallCallback).where(CallCallback.tenant_id == case.principal.tenant_id))
            assert journal.original_call_id is None and journal.original_attempt_id == attempt_id
            jobs = (await session.scalars(select(FollowUpJob).where(FollowUpJob.tenant_id == case.principal.tenant_id))).all()
            assert len(jobs) == 1
        results.append({"case": "missed_delay_dedupe_and_attempt_foreign_key", "pass": True})

        case = await seed()
        await scheduled(case)
        async with factory() as session:
            session.add(DncEntry(tenant_id=case.principal.tenant_id, phone_e164=PHONE, active=True))
            await session.commit()
        await service.run_once()
        assert dial.await_count == 0
        results.append({"case": "dnd_prevents_dispatch", "pass": True})

        case = await seed(callbackMode="review")
        job = await scheduled(case, status="needs_review")
        requested = AT.replace(hour=19)
        await service.edit_job(case.principal, job.id, "schedule", requested, AT)
        clock[0] = requested
        await service.run_once()
        assert dial.await_count == 0
        clock[0] = AT.replace(hour=9) + timedelta(days=1)
        await service.run_once()
        assert dial.await_count == 1
        results.append({"case": "tenant_approval_survives_overnight_adjustment", "pass": True})

        case = await seed()
        clock[0] = AT.replace(hour=8, minute=59, second=30)
        await scheduled(case)
        await service.run_once()
        assert dial.await_count == 0
        clock[0] = AT.replace(hour=9)
        await service.run_once()
        assert dial.await_count == 1
        results.append({"case": "strict_calling_window_boundary", "pass": True})

        case = await seed()
        await scheduled(case)
        dial.side_effect = TimeoutError("synthetic unknown acceptance")
        await service.run_once()
        await service.run_once()
        assert dial.await_count == 1
        async with factory() as session:
            saved = await session.scalar(select(FollowUpJob).where(FollowUpJob.tenant_id == case.principal.tenant_id))
            assert saved.status == "needs_review" and saved.reason == "dispatch_uncertain_do_not_redial"
        results.append({"case": "uncertain_dispatch_is_not_replayed", "pass": True})
        for result in results:
            print(json.dumps(result), flush=True)
    finally:
        for replacement in reversed(patches):
            replacement.stop()
        if engine:
            await engine.dispose()
        if created:
            assert schema.startswith("codex_followup_audit_") and len(schema) == len("codex_followup_audit_") + 12
            async with root.begin() as conn:
                await conn.execute(DropSchema(schema, cascade=True))
        await root.dispose()
    report = {"database": "isolated disposable PostgreSQL schema", "cases": results,
              "passed": len(results), "realCarrierCalls": 0, "testSchemaRemoved": True}
    (OUT / "postgres-queue-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("VERDICT: PASS")


asyncio.run(main())
