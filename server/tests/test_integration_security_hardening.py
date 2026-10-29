"""Offline security regressions with real tenant, agent and audit persistence."""
import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from server.db.models.entities import Agent, Base, Tenant
from server.db.models.integration_models import AgentIntegration, OAuthState, TenantIntegration, ToolExecution
from server.routes import integrations as routes
from server.services import tool_router as router_module
from server.services.integration_calendar import execute_calendar_action
from server.services.integration_safety import path_segment, soql_literal
from server.services.nango_service import NangoService
from server.services.tool_schema_registry import validate_tool_arguments

TID, OTHER, AID, FOREIGN = [UUID(f"aaaaaaaa-0000-4000-8000-{i:012d}") for i in (101, 102, 103, 104)]


@compiles(JSONB, "sqlite")
def sqlite_json(_type, _compiler, **_kw):
    return "JSON"


@pytest.fixture
async def db(monkeypatch):
    models = [Tenant, Agent, TenantIntegration, AgentIntegration, OAuthState, ToolExecution]
    for model in models:
        for column in model.__table__.columns:
            if isinstance(column.type, ARRAY):
                monkeypatch.setattr(column, "type", column.type.with_variant(JSON(), "sqlite"))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in models]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(routes, "get_session_factory", lambda: factory)
    monkeypatch.setattr(router_module, "get_session_factory", lambda: factory)
    async with factory() as session:
        session.add_all([
            Tenant(tenant_id=TID, name="First"), Tenant(tenant_id=OTHER, name="Other"),
            Agent(agent_id=AID, tenant_id=TID, name="Own agent"),
            Agent(agent_id=FOREIGN, tenant_id=OTHER, name="Foreign agent"),
            TenantIntegration(tenant_id=TID, app_name="SLACK", connection_id="owned", metadata_={"gateway_verified": True}),
        ])
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(db, monkeypatch):
    async def principal(request, csrf, authorization):
        from fastapi import HTTPException
        if authorization != "Bearer test-session":
            raise HTTPException(status_code=401)
        return SimpleNamespace(tenant_id=TID, subject=UUID(int=105), role="owner")
    monkeypatch.setattr(routes, "require_api_tenant", principal)
    monkeypatch.setattr(routes, "require_role_permission", lambda *_: None)
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(
        nango_webhook_signing_key="test-webhook-key", voxly_frontend_url="https://console.example.test", app_environment="production"))
    monkeypatch.setattr(routes.nango_service, "is_configured", lambda: False)
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://console.example.test") as value:
        yield value


def signed(payload):
    raw = json.dumps(payload).encode()
    signature = hmac.new(b"test-webhook-key", raw, hashlib.sha256).hexdigest()
    return raw, {"x-nango-hmac-sha256": signature}


async def test_header_spoof_and_unverified_activation_are_rejected(client, monkeypatch):
    response = await client.post("/api/integrations/SLACK/activate", headers={"x-tenant-id": str(TID)}, json={"connection_id": "foreign"})
    assert response.status_code == 401
    verify = AsyncMock(return_value=False)
    monkeypatch.setattr(routes.nango_service, "verify_or_sync_connection", verify)
    response = await client.post("/api/integrations/SLACK/activate", headers={"authorization": "Bearer test-session"}, json={"connection_id": "foreign"})
    assert response.status_code == 403
    verify.assert_awaited_once_with(str(TID), "SLACK", "foreign")


async def test_keys_and_foreign_redirects_never_create_connections(client, monkeypatch):
    start = AsyncMock()
    monkeypatch.setattr(routes.nango_service, "initiate_connection", start)
    headers = {"authorization": "Bearer test-session"}
    response = await client.post("/api/integrations/SLACK/connect", headers=headers,
                                json={"base_redirect_uri": "https://console.example.test/callback", "api_key": "test-only"})
    assert response.status_code == 422
    response = await client.post("/api/integrations/SLACK/connect", headers=headers,
                                json={"base_redirect_uri": "https://attacker.example.test/callback"})
    assert response.status_code == 400
    start.assert_not_awaited()


async def test_every_configured_console_origin_can_open_the_connection_form(client, monkeypatch):
    # The console is served from more than one deliberate origin; a wildcard never qualifies.
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(
        voxly_frontend_url="https://console.example.test", public_app_url="https://app.example.test",
        cors_origins="*,https://alt.example.test", app_environment="production"))
    start = AsyncMock(return_value={"status": "INITIATED", "session_token": "tok"})
    monkeypatch.setattr(routes.nango_service, "initiate_connection", start)
    headers = {"authorization": "Bearer test-session"}
    for origin in ("https://app.example.test", "https://alt.example.test", "https://ALT.example.test"):
        response = await client.post("/api/integrations/SLACK/connect", headers=headers,
                                     json={"base_redirect_uri": f"{origin}/api/integrations/callback"})
        assert response.status_code == 200, origin
    response = await client.post("/api/integrations/SLACK/connect", headers=headers,
                                 json={"base_redirect_uri": "http://alt.example.test/api/integrations/callback"})
    assert response.status_code == 400


async def test_webhook_signature_unknown_event_and_stale_replay(client, db, monkeypatch):
    assert (await client.post("/api/integrations/nango-webhook", json={})).status_code == 401
    raw, headers = signed({"type": "sync", "success": True})
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).json()["status"] == "ignored"
    monkeypatch.setattr(routes.nango_service, "verify_or_sync_connection", AsyncMock(return_value=True))
    payload = {"type": "auth", "operation": "creation", "success": True, "tags": {"end_user_id": str(TID)},
               "connectionId": "stale", "providerConfigKey": "slack"}
    raw, headers = signed(payload)
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).json()["status"] == "ignored"
    async with db() as session:
        row = (await session.execute(select(TenantIntegration))).scalar_one()
        assert row.connection_id == "owned"
        row.status = "DISCONNECTING"
        await session.commit()
    payload["connectionId"] = "owned"
    raw, headers = signed(payload)
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).json()["status"] == "ignored"


async def test_failed_auth_and_disconnect_do_not_authorize_foreign_connections(client, db, monkeypatch):
    payload = {"type": "auth", "operation": "creation", "success": False, "tags": {"end_user_id": str(TID)},
               "connectionId": "owned", "providerConfigKey": "slack"}
    raw, headers = signed(payload)
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).status_code == 200
    async with db() as session:
        assert (await session.execute(select(TenantIntegration))).scalar_one().status != "ACTIVE"
    monkeypatch.setattr(routes.nango_service, "get_tenant_connections", AsyncMock(return_value=[]))
    revoke = AsyncMock()
    monkeypatch.setattr(routes.nango_service, "delete_connection", revoke)
    assert (await client.delete("/api/integrations/SLACK", headers={"authorization": "Bearer test-session"})).status_code == 200
    revoke.assert_not_awaited()


async def enable_live_slack(factory):
    # Slack's catalog default is post-call. These action-execution tests exercise
    # an agent whose owner explicitly enabled this particular live write.
    async with factory() as session:
        session.add(AgentIntegration(tenant_id=TID, agent_id=AID, app_name="SLACK", enabled=True,
                                    timing_mode="in_call", action_whitelist=["SLACK_SEND_MESSAGE"]))
        await session.commit()


async def test_router_ownership_disable_and_durable_idempotency(db, monkeypatch):
    await enable_live_slack(db)
    router = router_module.VoxlyToolRouter()
    execute = AsyncMock(return_value={"status": "success", "message_id": "real-id"})
    monkeypatch.setattr(router.nango, "execute_in_call_tool", execute)
    args = dict(tenant_id=str(TID), agent_id=str(FOREIGN), call_id="call-test", tool_name="SLACK_SEND_MESSAGE",
                arguments={"channel": "C-test", "text": "Test only"})
    assert (await router.route_and_execute(**args))["status"] == "error"
    execute.assert_not_awaited()
    args["agent_id"] = str(AID)
    first = await router.route_and_execute(**args)
    assert first == await router.route_and_execute(**args) and first["status"] == "success"
    execute.assert_awaited_once()
    async with db() as session:
        assert (await session.execute(select(ToolExecution))).scalar_one().status == "succeeded"
        rule = (await session.execute(select(AgentIntegration).where(
            AgentIntegration.tenant_id == TID, AgentIntegration.agent_id == AID, AgentIntegration.app_name == "SLACK",
        ))).scalar_one()
        rule.enabled = False
        await session.commit()
    args["arguments"]["text"] = "Another message"
    assert (await router.route_and_execute(**args))["status"] == "error"
    execute.assert_awaited_once()


async def test_timeout_and_storage_failure_do_not_repeat_writes(db, monkeypatch):
    await enable_live_slack(db)
    router = router_module.VoxlyToolRouter()
    execute = AsyncMock(side_effect=asyncio.TimeoutError)
    monkeypatch.setattr(router.nango, "execute_in_call_tool", execute)
    args = dict(tenant_id=str(TID), agent_id=str(AID), call_id="call-timeout", tool_name="SLACK_SEND_MESSAGE",
                arguments={"channel": "C-test", "text": "Test only"})
    assert (await router.route_and_execute(**args))["status"] == "unknown"
    assert (await router.route_and_execute(**args))["status"] == "unknown"
    execute.assert_awaited_once()
    # Different arguments must not turn an uncertain outcome into a second write.
    args["arguments"] = {"channel": "C-test", "text": "Different message"}
    assert (await router.route_and_execute(**args))["status"] == "unknown"
    execute.assert_awaited_once()
    async with db() as session:
        assert (await session.execute(select(ToolExecution))).scalar_one().status == "timed_out_pending"
    monkeypatch.setattr(router, "_record_execution_start", AsyncMock(return_value=None))
    args["call_id"] = "call-db-down"
    assert (await router.route_and_execute(**args))["status"] == "error"
    execute.assert_awaited_once()


async def test_external_error_is_not_a_successful_audit(db, monkeypatch):
    await enable_live_slack(db)
    router = router_module.VoxlyToolRouter()
    monkeypatch.setattr(router.nango, "execute_in_call_tool", AsyncMock(return_value={"status": "error"}))
    await router.route_and_execute(str(TID), str(AID), "call-error", "SLACK_SEND_MESSAGE", {"channel": "C", "text": "test"})
    async with db() as session:
        assert (await session.execute(select(ToolExecution))).scalar_one().status == "failed"


async def test_exact_provider_connection_and_owner_are_required(monkeypatch):
    service = NangoService(secret_key="test-secret")
    connections = [{"provider_config_key": "slack", "connection_id": "ours", "tags": {"end_user_id": str(TID)}}]
    monkeypatch.setattr(service, "get_tenant_connections", AsyncMock(return_value=connections))
    assert await service.verify_or_sync_connection(str(TID), "SLACK", "ours")
    assert not await service.verify_or_sync_connection(str(OTHER), "SLACK", "ours")
    assert not await service.verify_or_sync_connection(str(TID), "SLACK", "someone-else")
    assert not await service.verify_or_sync_connection(str(TID), "GMAIL", "ours")
    monkeypatch.setattr(service, "get_tenant_connections", AsyncMock(side_effect=httpx.ConnectError("offline")))
    assert not await service.verify_or_sync_connection(str(TID), "SLACK", "ours")


async def test_connection_discovery_starts_at_zero_and_preserves_tenant_filter(monkeypatch):
    requested_pages = []
    original_client = httpx.AsyncClient

    def transport(request):
        assert request.url.params["tags[end_user_id]"] == str(TID)
        page = int(request.url.params["page"])
        requested_pages.append(page)
        if page == 0:
            rows = [{"provider_config_key": "slack", "connection_id": f"owned-{i}",
                     "tags": {"end_user_id": str(TID)}} for i in range(99)]
            rows.append({"provider_config_key": "slack", "connection_id": "foreign", "tags": {"end_user_id": str(OTHER)}})
        else:
            rows = [{"provider_config_key": "google-calendar", "connection_id": "last-page", "tags": {"end_user_id": str(TID)}}]
        return httpx.Response(200, json={"connections": rows})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(transport), **kwargs))
    service = NangoService(secret_key="test-secret")
    rows = await service.get_tenant_connections(str(TID))
    assert requested_pages == [0, 1]
    assert len(rows) == 100
    assert not any(row["connection_id"] == "foreign" for row in rows)
    assert rows[-1]["provider_config_key"] == "google-calendar"


@pytest.mark.parametrize("payload", [{}, {"calendars": {"primary": {"errors": [{"reason": "forbidden"}]}}},
                                     {"calendars": {"primary": {"busy": [{"start": "bad", "end": "bad"}]}}}])
async def test_calendar_failure_cannot_fabricate_slots(payload):
    def transport(request):
        return httpx.Response(200, json={"timeZone": "Asia/Kolkata"} if request.method == "GET" else payload)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        result = await execute_calendar_action(client, "https://gateway.example.test", {}, "GOOGLECALENDAR_FIND_FREE_SLOTS", {"date": "2030-10-20"})
    assert result["status"] == "error" and "available_slots" not in result


def test_schema_path_soql_and_tool_output_limits():
    assert validate_tool_arguments("SLACK_SEND_MESSAGE", {"channel": "C", "text": "x", "api_key": "secret"})
    assert validate_tool_arguments("GOOGLECALENDAR_CREATE_EVENT", {"summary": "x", "start": "tomorrow", "end": "later"})
    assert validate_tool_arguments("SLACK_DELETE_EVERYTHING", {})
    assert not validate_tool_arguments("SLACK_SEND_MESSAGE", {"channel": "C", "text": "x"})
    assert path_segment("a/b?x=1") == "a%2Fb%3Fx%3D1"
    with pytest.raises(ValueError):
        path_segment("..")
    assert soql_literal("O'Brien") == "O\\'Brien"
    result = NangoService(secret_key="x").sanitize_voice_response(
        {"status": "success", "access_token": "secret", "unexpected": "secret", "records": [{"password": "secret", "name": "Allowed"}]},
        action_name="AIRTABLE_SEARCH_RECORDS")
    assert "secret" not in json.dumps(result)
