"""Primary campaign/admission regressions. All carrier operations are isolated fakes."""
import asyncio
import os
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from server.db.models.entities import Agent, Base, Call, Tenant
from server.db.models.saas_models import TenantMembership, User
from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, Contact, ContactList, ContactImportTemplate, DialAttempt, DncEntry, PstnDialRequest
from server.routes import campaigns as routes
from server.services.saas import call_admission as admission, campaign_runner as runner

TID, OTHER, UID, AID = [uuid.UUID(f"aaaaaaaa-0000-4000-8000-{i:012d}") for i in (6001, 6002, 6003, 6004)]


@compiles(JSONB, "sqlite")
def sqlite_json(*_args, **_kw):
    return "JSON"


@pytest.fixture
async def db(tmp_path, monkeypatch):
    models = [Tenant, Agent, User, TenantMembership, Call, Contact, ContactList, ContactImportTemplate, Campaign, CampaignContact, CampaignRun, DialAttempt, DncEntry, PstnDialRequest]
    for model in models:
        for column in model.__table__.columns:
            if isinstance(column.type, ARRAY):
                monkeypatch.setattr(column, "type", column.type.with_variant(JSON(), "sqlite"))
    pg_url = os.environ.get("CAMPAIGN_AUDIT_DATABASE_URL")
    schema = "audit_" + uuid.uuid4().hex
    admin_engine = create_async_engine(pg_url) if pg_url else None
    if admin_engine:
        from sqlalchemy import text
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(pg_url, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'campaign.db'}", connect_args={"timeout": 20})
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in models]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    for module in (admission, runner, routes):
        monkeypatch.setattr(module, "get_session_factory", lambda: factory)
    from server.config.env import get_settings
    settings = get_settings().model_copy(update={"saas_max_concurrent_pstn": 20,
        "saas_max_outbound_cps": 100, "campaign_max_concurrency": 20,
        "campaign_default_retry_attempts": 3, "redis_url": "", "app_environment": "test"})
    monkeypatch.setattr(admission, "get_settings", lambda: settings)
    monkeypatch.setattr(runner, "get_settings", lambda: settings)
    monkeypatch.setattr("server.config.env.get_settings", lambda: settings)
    monkeypatch.setattr("server.services.saas.tenant_guard.subscriber_workspace_tenant_id", lambda p: p.tenant_id)
    async with factory() as session:
        session.add_all([Tenant(tenant_id=TID, name="Own", limits={"max_concurrent_pstn": 2}),
            Tenant(tenant_id=OTHER, name="Other"), User(user_id=UID, email="audit@example.test", password_hash="unused"),
        ])
        await session.flush()
        session.add_all([TenantMembership(user_id=UID, tenant_id=TID, role="customer_admin"),
                         Agent(agent_id=AID, tenant_id=TID, name="Audit agent")])
        await session.commit()
    yield factory
    await engine.dispose()
    if admin_engine:
        # Generated schema on the explicitly owned audit container, never a tenant DB.
        from sqlalchemy import text
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


async def test_atomic_capacity_and_idempotency(db):
    calls = []
    async def dial(key):
        calls.append(key)
        await asyncio.sleep(.02)
        return {"ok": True, "call_control_id": key, "stream_url": "secret", "history": {"token": "secret"}}
    async def request(i):
        try:
            return await admission.execute(tenant_id=TID, request_id=f"r{i}", provider="vobiz", payload={"i": i}, operation=dial)
        except HTTPException as exc:
            return exc.status_code
    results = await asyncio.gather(*(request(i) for i in range(15)))
    assert len(calls) == 2
    assert results.count(429) == 13
    first = next(i for i, result in enumerate(results) if isinstance(result, dict))
    replay = await request(first)
    assert replay["ok"] and "stream_url" not in replay and "history" not in replay
    assert len(calls) == 2
    async with db() as session:
        assert await admission.active_capacity(session, TID) == 2
    key = calls[0]
    await admission.provider_event(tenant_id=OTHER, key=key, status="ended")
    async with db() as session:
        assert (await session.get(PstnDialRequest, key)).status == "accepted"
    await admission.provider_event(tenant_id=TID, key=key, status="ended")
    await admission.provider_event(tenant_id=TID, key=key, status="answered")
    async with db() as session:
        assert (await session.get(PstnDialRequest, key)).status == "ended"
        assert await admission.active_capacity(session, TID) == 1


async def test_conflicting_and_uncertain_requests_never_redial(db):
    count = 0
    async def uncertain(_key):
        nonlocal count
        count += 1
        raise TimeoutError("isolated timeout")
    with pytest.raises(TimeoutError):
        await admission.execute(tenant_id=TID, request_id="same", provider="vobiz", payload={"a": 1}, operation=uncertain)
    result = await admission.execute(tenant_id=TID, request_id="same", provider="vobiz", payload={"a": 1}, operation=uncertain)
    assert result["code"] == "dial_pending" and count == 1
    with pytest.raises(HTTPException) as error:
        await admission.reserve(TID, "same", provider="vobiz", payload={"a": 2})
    assert error.value.status_code == 409
    async with db() as session:
        assert await admission.active_capacity(session, TID) == 1


@pytest.mark.parametrize("status", [200, 408, 503])
async def test_unconfirmed_carrier_response_keeps_capacity_and_never_redials(db, status):
    count = 0
    async def operation(_key):
        nonlocal count
        count += 1
        return {"ok": False, "status": status}
    args = dict(tenant_id=TID, request_id="unconfirmed", provider="vobiz", payload={}, operation=operation)
    await admission.execute(**args)
    await admission.execute(**args)
    assert count == 1
    async with db() as session:
        row = await session.get(PstnDialRequest, admission.request_key(TID, "unconfirmed"))
        assert row.status == "uncertain"
        assert await admission.active_capacity(session, TID) == 1


async def seeded_campaign(db, count=3):
    cid, rid = uuid.uuid4(), uuid.uuid4()
    async with db() as session:
        session.add(Campaign(campaign_id=cid, tenant_id=TID, agent_id=AID, name="Audit", status="running",
            concurrency=1, consent_confirmed=True, retry_rules={"max_attempts": 2, "retry_delay_minutes": 30}))
        await session.flush()
        session.add(CampaignRun(run_id=rid, campaign_id=cid, status="running", stats={"actor": {"user_id": str(UID), "tenant_id": str(TID)}}))
        for n in range(count):
            session.add(CampaignContact(campaign_id=cid, phone_e164=f"+120255501{n:02d}", metadata_={"campaign_id": "untrusted"}))
        await session.commit()
    return cid, rid


async def test_campaign_holds_slot_through_ring_and_retries_wait(db, monkeypatch):
    cid, rid = await seeded_campaign(db)
    owner = uuid.uuid4()
    dialed = []
    async def outbound(principal, **args):
        assert args["contact"]["campaign_id"] == str(cid)
        dialed.append(args)
        async def carrier(key):
            return {"ok": True, "call_control_id": key}
        return await admission.execute(tenant_id=principal.tenant_id, request_id=args["dial_request_id"],
            provider="vobiz", payload=args, operation=carrier)
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", outbound)
    assert await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=owner)
    assert len(dialed) == 1
    assert await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=uuid.uuid4()) is False
    await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=owner)
    assert len(dialed) == 1  # placing is not connected, and ringing retains capacity
    key = admission.request_key(TID, dialed[0]["dial_request_id"])
    await admission.provider_event(tenant_id=TID, key=key, status="ended")
    await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=owner)
    assert len(dialed) == 2 and dialed[0]["to_e164"] != dialed[1]["to_e164"]
    async with db() as session:
        old = (await session.execute(select(CampaignContact).where(CampaignContact.campaign_id == cid,
            CampaignContact.phone_e164 == dialed[0]["to_e164"]))).scalar_one()
        assert old.status == "failed" and old.attempts == 1
        assert runner._aware(old.next_attempt_at) > runner._utcnow() + timedelta(minutes=29)
        camp = await session.get(Campaign, cid)
        camp.status = "paused"
        await session.commit()
    assert await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=owner) is False
    assert len(dialed) == 2


async def test_answered_without_media_is_not_automatically_retried(db, monkeypatch):
    cid, rid = await seeded_campaign(db, 1)
    owner = uuid.uuid4()
    async def outbound(principal, **args):
        async def carrier(key):
            await admission.provider_event(tenant_id=TID, key=key, status="answered")
            await admission.provider_event(tenant_id=TID, key=key, status="ended")
            return {"ok": True, "call_control_id": "isolated"}
        return await admission.execute(tenant_id=TID, request_id=args["dial_request_id"], provider="vobiz", payload=args, operation=carrier)
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", outbound)
    await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=owner)
    assert await runner.campaign_tick(cid, rid, workspace_tenant_id=TID, owner=owner) is False
    async with db() as session:
        assert (await session.get(Campaign, cid)).status == "completed"
        assert (await session.execute(select(CampaignContact).where(CampaignContact.campaign_id == cid))).scalar_one().status == "completed"
    from server.auth.api_tenant import ApiTenantContext
    stats = await routes.campaign_analytics(str(cid), ApiTenantContext(tenant_id=TID, role="customer_admin", subject=str(UID), subscriber=False))
    assert stats["status"] == "completed" and stats["connects"] == 1 and stats["attempts"] == 1


async def test_start_is_idempotent_and_checks_tenant(db, monkeypatch):
    cid, rid = await seeded_campaign(db)
    from server.auth.api_tenant import ApiTenantContext
    ctx = ApiTenantContext(tenant_id=TID, role="customer_admin", subject=str(UID), subscriber=False)
    monkeypatch.setattr(runner, "spawn_campaign_runner", lambda *args, **kw: None)
    results = await asyncio.gather(*(routes.start_campaign(str(cid), ctx) for _ in range(8)))
    assert {r["runId"] for r in results} == {str(rid)}
    other = ApiTenantContext(tenant_id=OTHER, role="customer_admin", subject=str(UID), subscriber=False)
    with pytest.raises(HTTPException) as error:
        await routes.start_campaign(str(cid), other)
    assert error.value.status_code == 404


def test_calling_windows_are_recipient_aware():
    from datetime import datetime, timezone
    schedule = {"calling_window": {"start": "09:00", "end": "18:00", "timezone": "Asia/Kolkata"}}
    now = datetime(2026, 10, 20, 5, 0, tzinfo=timezone.utc)
    assert runner.within_calling_window(schedule, {}, now)
    assert not runner.within_calling_window(schedule, {"timezone": "America/New_York"}, now)
    assert not runner.within_calling_window(schedule, {"timezone": "untrusted"}, now)


async def test_complete_contact_import_and_saved_list_are_not_truncated(db, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from server.routes import contacts as contact_routes
    from server.auth.api_tenant import ApiTenantContext, require_api_tenant
    monkeypatch.setattr(contact_routes, "get_session_factory", lambda: db)
    ctx = ApiTenantContext(tenant_id=TID, role="customer_admin", subject=str(UID), subscriber=False)
    app = FastAPI()
    app.dependency_overrides[require_api_tenant] = lambda: ctx
    app.include_router(contact_routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://isolated.test") as client:
        csv = "phone,full_name\n" + "\n".join(f"+1202555{100 + n:04d},Example {n}" for n in range(250))
        parsed = await client.post("/api/contacts/parse", json={"fileName": "contacts.csv", "rawText": csv})
        assert parsed.status_code == 200, parsed.text
        result = parsed.json()
        assert result["totalRows"] == len(result["rows"]) == 250
        assert len(result["previewRows"]) == 50
        normalized = await client.post("/api/contacts/normalize-preview", json={"rows": result["rows"], "mapping": {"phone": "phone", "full_name": "full_name"}})
        assert normalized.json()["validCount"] == 250
        assert len(normalized.json()["validContacts"]) == 250
        saved = await client.post("/api/contacts/lists", json={"name": "All 250", "contacts": normalized.json()["validContacts"]})
        assert saved.status_code == 200, saved.text
        list_id = saved.json()["listId"]
        listed = await client.get(f"/api/contacts/lists/{list_id}/contacts")
        assert listed.status_code == 200
        assert len(listed.json()["contacts"]) == listed.json()["totalContacts"] == 250
        assert listed.json()["truncated"] is False
        template = {"templateName": "Audit mapping", "sourceHeaders": ["phone"], "mapping": {"phone": "phone"}}
        created = await client.post("/api/contacts/templates", json=template)
        updated = await client.post("/api/contacts/templates", json={**template, "defaultCountry": "IN"})
        assert created.status_code == updated.status_code == 200
        assert created.json()["templateId"] == updated.json()["templateId"]


async def test_import_limits_reject_oversize_and_zip_expansion(db):
    from server.services.saas.contact_import_service import parse_file_to_rows
    import io, zipfile
    with pytest.raises(ValueError, match="5 MB"):
        parse_file_to_rows(b"a" * (5 * 1024 * 1024 + 1), "large.csv")
    with pytest.raises(ValueError, match="10,000"):
        parse_file_to_rows(b"phone\n" + b"+12025550101\n" * 10001, "too-many.csv")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        output.writestr("large.xml", b"x" * (26 * 1024 * 1024))
    with pytest.raises(ValueError, match="expands"):
        parse_file_to_rows(archive.getvalue(), "expanded.xlsx")


async def test_legacy_saved_lists_cannot_bypass_campaign_batch_limit(db):
    from sqlalchemy import insert
    from server.auth.api_tenant import ApiTenantContext
    list_id = uuid.uuid4()
    async with db() as session:
        session.add(ContactList(id=list_id, tenant_id=TID, name="Legacy oversized list", total_contacts=10001))
        await session.flush()
        await session.execute(insert(Contact), [{"id": uuid.uuid4(), "tenant_id": TID,
            "contact_list_id": list_id, "phone": "+12025550101"} for _ in range(10001)])
        await session.commit()
    ctx = ApiTenantContext(tenant_id=TID, role="customer_admin", subject=str(UID), subscriber=False)
    body = routes.CampaignCreate(name="Bounded", agentId=str(AID), contactListId=str(list_id), consentConfirmed=True)
    with pytest.raises(HTTPException) as error:
        await routes.create_campaign(Request({"type": "http", "headers": []}), body, ctx)
    assert error.value.status_code == 422


async def test_additive_migration_roundtrip_on_isolated_postgres(db):
    engine = db.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("Run with the owned PostgreSQL audit container")
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    migration_path = __import__("pathlib").Path("server/db/migrations/versions/041_campaign_execution_safety.py")
    spec = importlib.util.spec_from_file_location("audit_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    def check(connection):
        with Operations.context(MigrationContext.configure(connection)):
            # Prepare the pre-041 shape inside this generated throwaway schema.
            migration.downgrade()
            assert "pstn_dial_requests" not in inspect(connection).get_table_names()
            migration.upgrade()
            columns = {c["name"] for c in inspect(connection).get_columns("pstn_dial_requests")}
            assert {"request_key", "tenant_id", "destination_hash", "answered_at"} <= columns
            assert {"lease_owner", "lease_expires_at"} <= {c["name"] for c in inspect(connection).get_columns("campaign_runs")}
    async with engine.begin() as connection:
        await connection.run_sync(check)


async def test_create_request_is_idempotent_and_never_links_foreign_contacts(db):
    from starlette.requests import Request
    from server.auth.api_tenant import ApiTenantContext
    request = Request({"type": "http", "method": "POST", "path": "/api/campaigns", "headers": [], "client": ("127.0.0.1", 1234)})
    ctx = ApiTenantContext(tenant_id=TID, role="customer_admin", subject=str(UID), subscriber=False)
    foreign_id = uuid.uuid4()
    async with db() as session:
        session.add(Contact(id=foreign_id, tenant_id=OTHER, phone="+12025550101"))
        await session.commit()
    body = routes.CampaignCreate(name="Idempotency audit", agentId=str(AID), clientRequestId=str(uuid.uuid4()),
        contacts=[{"phone": "+12025550101", "id": str(foreign_id)}], consentConfirmed=True)
    results = await asyncio.gather(*(routes.create_campaign(request, body, ctx) for _ in range(6)))
    assert len({r["id"] for r in results}) == 1
    async with db() as session:
        row = (await session.execute(select(CampaignContact).where(CampaignContact.campaign_id == uuid.UUID(results[0]["id"])))).scalar_one()
        assert row.contact_id is None
    with pytest.raises(HTTPException) as error:
        await routes.create_campaign(request, body.model_copy(update={"name": "Changed"}), ctx)
    assert error.value.status_code == 409


async def test_outbound_cps_is_shared_and_distinct_from_concurrency(db, monkeypatch):
    monkeypatch.setattr(admission, "get_settings", lambda: SimpleNamespace(saas_max_concurrent_pstn=20, saas_max_outbound_cps=1))
    key, _ = await admission.reserve(TID, "paced-first", provider="vobiz", payload={"to": "+12025550101"})
    with pytest.raises(HTTPException) as error:
        await admission.reserve(TID, "paced-second", provider="vobiz", payload={"to": "+12025550102"})
    assert error.value.status_code == 429 and error.value.detail["error"]["code"] == "call_pacing"
    async with db() as session:
        row = await session.get(PstnDialRequest, key)
        row.created_at = admission._now() - timedelta(seconds=2)
        await session.commit()
    assert (await admission.reserve(TID, "paced-second", provider="vobiz", payload={"to": "+12025550102"}))[1] is None


async def test_durable_media_claim_rejects_replay_and_wrong_tenant(db):
    key, _ = await admission.reserve(TID, "media-claim", provider="vobiz", payload={})
    assert await admission.claim_media(OTHER, key) is False
    results = await asyncio.gather(*(admission.claim_media(TID, key) for _ in range(8)))
    assert results.count(True) == 1
    assert await admission.claim_media(TID, key) is False
    await admission.provider_event(tenant_id=TID, key=key, status="ended")
    assert await admission.claim_media(TID, key) is False


async def test_resume_last_attempt_reuses_run_and_supersedes_older_runs(db, monkeypatch):
    from server.auth.api_tenant import ApiTenantContext
    cid, rid = await seeded_campaign(db, 1)
    older = uuid.uuid4()
    async with db() as session:
        camp = await session.get(Campaign, cid)
        camp.status = "paused"
        run = await session.get(CampaignRun, rid)
        run.started_at = runner._utcnow()
        session.add(CampaignRun(run_id=older, campaign_id=cid, status="running", started_at=runner._utcnow() - timedelta(days=1)))
        contact = (await session.execute(select(CampaignContact).where(CampaignContact.campaign_id == cid))).scalar_one()
        contact.status, contact.attempts = "placed", 2
        await session.commit()
    monkeypatch.setattr(runner, "spawn_campaign_runner", lambda *args, **kw: None)
    ctx = ApiTenantContext(tenant_id=TID, role="customer_admin", subject=str(UID), subscriber=False)
    result = await routes.start_campaign(str(cid), ctx)
    assert result["runId"] == str(rid)
    async with db() as session:
        assert (await session.get(CampaignRun, older)).status == "superseded"


async def test_password_verification_runs_outside_voice_event_loop(db, monkeypatch):
    import threading
    from unittest.mock import AsyncMock
    from server.services.saas import auth_service
    monkeypatch.setattr(auth_service, "get_session_factory", lambda: db)
    monkeypatch.setattr(auth_service, "_log_event", AsyncMock())
    threads = []
    def verify(_stored, _provided):
        threads.append(threading.get_ident())
        return False
    monkeypatch.setattr(auth_service, "verify_portal_password", verify)
    with pytest.raises(ValueError, match="invalid_credentials"):
        await auth_service.login(email="audit@example.test", password="isolated")
    assert len(threads) == 1 and threads[0] != threading.get_ident()


@pytest.mark.parametrize("failure", ["inactive", "deleted", "missing", "database", "wallet", "wallet_error", "capacity"])
async def test_primary_inbound_fails_closed_before_paid_routing(db, monkeypatch, failure):
    import httpx
    from unittest.mock import AsyncMock, Mock
    from server.app import app
    from server.routes import vobiz
    from server.services.vobiz_client import vobiz_stream_tokens
    from server.services.saas.telephony_profile import InboundDecision
    tenant_id = TID if failure != "missing" else uuid.uuid4()
    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: None if failure == "database" else db)
    monkeypatch.setattr(vobiz.get_settings(), "pstn_enforce_wallet_on_inbound", True)
    monkeypatch.setattr("server.services.saas.telephony_profile.profile_for_number", AsyncMock(return_value={
        "agent_id": str(AID), "tenant_id": str(tenant_id)}))
    decision = Mock(return_value=InboundDecision(should_answer=failure == "capacity", route="transfer",
        transfer_number="+12025550101", reason="audit"))
    monkeypatch.setattr("server.services.saas.telephony_profile.evaluate_inbound_policy", decision)
    wallet = AsyncMock(return_value=failure != "wallet", side_effect=RuntimeError("isolated unavailable") if failure == "wallet_error" else None)
    monkeypatch.setattr("server.services.saas.billing_wallet_service.wallet_allows_inbound", wallet)
    if failure in ("inactive", "deleted"):
        async with db() as session:
            tenant = await session.get(Tenant, TID)
            if failure == "inactive": tenant.status = "suspended"
            else: tenant.deleted_at = runner._utcnow()
            await session.commit()
    if failure == "capacity":
        for n in range(2):
            await admission.reserve(TID, f"held-{n}", provider="vobiz", payload={})
    call_id = "audit-inbound-" + uuid.uuid4().hex
    token = vobiz_stream_tokens.create(call_uuid=call_id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://isolated.test") as client:
        response = await client.post("/api/vobiz/answer", params={"token": token}, data={
            "CallUUID": call_id, "From": "+12025550101", "To": "+12025550102", "Direction": "inbound"})
    assert response.status_code == 200
    assert "<Hangup" in response.text
    assert "<Stream" not in response.text and "<Dial" not in response.text
    if failure != "capacity": decision.assert_not_called()
