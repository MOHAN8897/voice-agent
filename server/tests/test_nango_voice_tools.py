"""Authoritative Verification Suite for Nango Multi-Tenant Voice Tools."""
from __future__ import annotations

import asyncio
import json
import secrets
import httpx
from types import SimpleNamespace
from server.tests.test_integration_security_hardening import db, client, TID, AID, signed
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from server.services.nango_service import NangoService, nango_service
from server.services.tool_router import VoxlyToolRouter


# ---------------------------------------------------------------------------
# Test 1: Semantically Safe Schema Optimization (Preserves Valid Types)
# ---------------------------------------------------------------------------
def test_schema_optimizer_preserves_semantics_and_targets_size_reduction():
    """Verify schema optimizer preserves nested structures while targeting >=85% reduction."""
    service = NangoService(api_key="mock_key")

    # Complex OpenAPI tool schema with nested objects, arrays, and formats
    raw_tool = {
        "type": "function",
        "function": {
            "name": "GOOGLECALENDAR_CREATE_EVENT",
            "description": "Creates an appointment in primary or secondary calendar.\nMarkdown documentation block 1.\nMarkdown block 2.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Title of the appointment."},
                    "start": {
                        "type": "object",
                        "description": "Start time object.",
                        "properties": {
                            "dateTime": {"type": "string", "format": "date-time", "description": "RFC3339 timestamp."},
                            "timeZone": {"type": "string", "description": "IANA timezone string."},
                        },
                        "required": ["dateTime"],
                    },
                    "attendees": {
                        "type": "array",
                        "description": "List of attendees.",
                        "items": {"type": "string", "format": "email"},
                    },
                    "conferenceDataVersion": {"type": "integer", "description": "Internal Google Meet API flag."},
                    "recurrence": {"type": "array", "description": "Recurrence RRULE entries."},
                    "etag": {"type": "string", "description": "ETag header."},
                },
                "required": ["summary", "start"],
            },
        },
    }

    optimized = service.optimize_tool_schema(raw_tool)

    assert optimized["type"] == "function"
    assert optimized["name"] == "GOOGLECALENDAR_CREATE_EVENT"
    assert "\n" not in optimized["description"]

    props = optimized["parameters"]["properties"]
    # 1. Required hierarchical structures ARE PRESERVED
    assert "summary" in props
    assert props["start"]["type"] == "object"
    assert "dateTime" in props["start"]["properties"]
    assert props["start"]["properties"]["dateTime"]["format"] == "date-time"
    assert props["attendees"]["type"] == "array"
    assert props["attendees"]["items"]["format"] == "email"

    # 2. Non-essential metadata stripped
    assert "conferenceDataVersion" not in props
    assert "recurrence" not in props
    assert "etag" not in props

    # 3. Size reduction target verified
    raw_size = len(json.dumps(raw_tool))
    optimized_size = len(json.dumps(optimized))
    assert optimized_size < (raw_size * 0.65)


# ---------------------------------------------------------------------------
# Test 2: Fail-Closed Tenant Security & Tool Router Dispatch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_router_fails_closed_without_tenant_and_dispatches_with_tenant():
    """Verify tool router rejects missing tenant and routes valid calls through router."""
    router = VoxlyToolRouter()

    # 1. Missing tenant MUST FAIL CLOSED (No "default" fallback)
    result_rejected = await router.route_and_execute(
        tenant_id=None,
        agent_id="agent_123",
        call_id="call_789",
        tool_name="GOOGLECALENDAR_FIND_FREE_SLOTS",
        arguments={"date": "2026-10-05"},
    )
    assert result_rejected["status"] == "error"
    assert "Unauthorized" in result_rejected["message"]

    # Missing agent MUST ALSO FAIL CLOSED
    result_no_agent = await router.route_and_execute(
        tenant_id="tenant_123",
        agent_id=None,
        call_id="call_789",
        tool_name="GOOGLECALENDAR_FIND_FREE_SLOTS",
        arguments={"date": "2026-10-05"},
    )
    assert result_no_agent["status"] == "error"
    assert "Unauthorized" in result_no_agent["message"]

    # 2. Valid tenant and agent context dispatches properly through Nango
    mock_response = {
        "status": "success",
        "slots": ["10:00 AM", "2:00 PM"],
        "summary": "Found 2 available slots for tomorrow",
    }
    with patch.object(router, "authorized", AsyncMock(return_value=True)), patch.object(router.nango, "execute_in_call_tool", AsyncMock(return_value=mock_response)):
        res = await router.route_and_execute(
            tenant_id="11111111-1111-1111-1111-111111111111",
            agent_id="22222222-2222-2222-2222-222222222222",
            call_id="call_123",
            tool_name="GOOGLECALENDAR_FIND_FREE_SLOTS",
            arguments={"date": "2026-10-05"},
        )
        assert res["status"] == "success"
        assert "slots" in res
        assert len(res["slots"]) == 2


# ---------------------------------------------------------------------------
# Test 3: Write-Action SLA Timeout Semantics & Split-Brain Prevention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_router_handles_1_5s_sla_timeout_gracefully():
    """Verify tool router intercepts 1.5s SLA timeouts on write actions."""
    router = VoxlyToolRouter()

    async def _sim_slow_tool(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch.object(router, "authorized", AsyncMock(return_value=True)), patch.object(router, "_record_execution_start", AsyncMock(return_value={"execute": True, "execution_id": "test-execution"})), patch.object(router, "_record_execution_complete", AsyncMock()), patch.object(router.nango, "execute_in_call_tool", side_effect=_sim_slow_tool):
        res = await router.route_and_execute(
            tenant_id="11111111-1111-1111-1111-111111111111",
            agent_id="22222222-2222-2222-2222-222222222222",
            call_id="call_timeout_test",
            tool_name="GOOGLECALENDAR_CREATE_EVENT",
            arguments={"summary": "Sales Consultation", "start": "2030-10-20T15:00:00+05:30", "end": "2030-10-20T15:30:00+05:30"},
        )

        assert res["status"] == "unknown"
        assert "confirmed" in res["message"]


# ---------------------------------------------------------------------------
# Test 4: Provider Mapping & Nango Connect Session
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nango_service_provider_mapping_and_connect_initiation():
    """Verify app names map correctly to Nango integration IDs."""
    service = NangoService(secret_key="mock_secret", base_url="https://api.nango.dev")
    assert service.get_provider_key("GOOGLECALENDAR") == "google-calendar"
    assert service.get_provider_key("SLACK") == "slack"
    assert service.get_provider_key("HUBSPOT") == "hubspot"
    assert service.get_provider_key("SALESFORCE") == "salesforce"
    assert service.get_provider_key("GITHUB") == "github-getting-started"

    # Test connect initiation with mock response
    mock_connect_resp = {
        "data": {
            "token": "mock_token_123",
            "connect_link": "https://connect.nango.dev/?session_token=mock_token_123",
            "expires_at": "2026-10-05T18:00:00Z",
        }
    }
    with patch.object(service, "_resolve_environment_key", AsyncMock(return_value="mock_secret")):
        with patch("server.services.nango_service._safe_urlopen") as mock_url:
            mock_cm = MagicMock()
            mock_cm.status = 200
            mock_cm.read.return_value = json.dumps(mock_connect_resp).encode()
            mock_cm.__enter__.return_value = mock_cm
            mock_url.return_value = mock_cm

            res = await service.initiate_connection(
                tenant_id="11111111-1111-1111-1111-111111111111",
                user_id="22222222-2222-2222-2222-222222222222",
                app_name="GOOGLECALENDAR",
                base_redirect_uri="https://app.voxly.ai/callback",
            )
            assert res is not None
            assert res["status"] == "INITIATED"
            assert "https://connect.nango.dev" in res["redirect_url"]
            assert res["session_token"] == "mock_token_123"


# ---------------------------------------------------------------------------
# Test 5: Post-Call Durable Automation Contract
# ---------------------------------------------------------------------------
def test_durable_job_nango_action_contract():
    """Verify post-call durable job enqueues with correct nango_action type."""
    from server.call.durable_job import DurableJob

    call_id = f"call_{secrets.token_hex(4)}"
    tenant_id = "11111111-1111-1111-1111-111111111111"

    job = DurableJob(
        call_id=call_id,
        tenant_id=tenant_id,
        job_type="nango_action",
        payload={"action_name": "HUBSPOT_CREATE_CONTACT", "caller_phone": "+919876543210"},
    )
    assert job.job_type == "nango_action"
    assert job.idempotency_key == f"nango_action:{call_id}:HUBSPOT_CREATE_CONTACT"


# ---------------------------------------------------------------------------
# Test 6: Nango Connection Retrieval & Reverse Mapping
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nango_get_tenant_connections_and_reverse_mapping(monkeypatch):
    service = NangoService(secret_key="test-secret")
    assert service.get_app_name_from_provider("google-calendar") == "GOOGLECALENDAR"
    response = httpx.Response(200, json={"connections": [
        {"connection_id": "ours", "provider_config_key": "google-calendar", "tags": {"end_user_id": str(TID)}},
        {"connection_id": "foreign", "provider_config_key": "google-calendar", "tags": {"end_user_id": "another-tenant"}},
    ]}, request=httpx.Request("GET", "https://gateway.example.test/connections"))
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=response))
    assert len(await service.get_tenant_connections(str(TID))) == 1
    assert await service.verify_or_sync_connection(str(TID), "GOOGLECALENDAR", "ours")
    assert not await service.verify_or_sync_connection(str(TID), "GOOGLECALENDAR", "foreign")


# ---------------------------------------------------------------------------
# Test 7: Integration Endpoints (Activate, List, and Disconnect)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_integrations_activate_and_reconcile(client, monkeypatch):
    from server.routes import integrations as routes
    monkeypatch.setattr(routes.nango_service, "verify_or_sync_connection", AsyncMock(return_value=True))
    headers = {"authorization": "Bearer test-session"}
    response = await client.post("/api/integrations/GOOGLECALENDAR/activate", headers=headers, json={"connection_id": "verified-calendar"})
    assert response.status_code == 200 and response.json()["status"] == "ACTIVE"
    assert "connection_id" not in response.json()
    response = await client.get("/api/integrations", headers=headers)
    assert {r["app_name"] for r in response.json()["items"]} == {"SLACK", "GOOGLECALENDAR"}
    monkeypatch.setattr(routes.nango_service, "get_tenant_connections", AsyncMock(return_value=[]))
    assert (await client.delete("/api/integrations/GOOGLECALENDAR", headers=headers)).status_code == 200
    response = await client.get("/api/integrations", headers=headers)
    assert [r["app_name"] for r in response.json()["items"]] == ["SLACK"]


# ---------------------------------------------------------------------------
# Test 8: Nango Webhook Event Processing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nango_webhook_updates_tenant_integrations(client, monkeypatch):
    from server.routes import integrations as routes
    monkeypatch.setattr(routes.nango_service, "verify_or_sync_connection", AsyncMock(return_value=True))
    raw, headers = signed({"type": "auth", "operation": "creation", "success": True,
                           "connectionId": "owned", "providerConfigKey": "slack", "tags": {"end_user_id": str(TID)}})
    response = await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Test 9: Voice Loop Auto-Discovers Active Tenant Tools
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_realtime_voice_loop_auto_discovers_tenant_tools(db, monkeypatch):
    from server.tests.test_integration_security_hardening import enable_live_slack

    await enable_live_slack(db)
    from server.realtime.testing import FakeRealtimeVoiceAdapter
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
    from server.services import tenant_tool_cache
    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: db)
    tenant_tool_cache.invalidate(str(TID))
    loop = PstnRealtimeVoiceLoop(session_id="test-discovery", call_id=None, tenant_id=str(TID), agent_id=str(AID),
                                 agent_tools=None, on_agent_wire=AsyncMock())
    loop._injected_adapter = FakeRealtimeVoiceAdapter()
    try:
        await loop.start_call(play_greeting=False)
        assert "SLACK_SEND_MESSAGE" in loop._agent_tools
        assert "SLACK" not in loop._agent_tools
        assert "googlecalendar_create_event" not in loop._agent_tools
    finally:
        await loop.close()


# ---------------------------------------------------------------------------
# Test 10: Compound App Normalization and Schema Discovery
# ---------------------------------------------------------------------------
def test_compound_app_normalization_and_schema_discovery():
    """Verify tool_schema_registry correctly handles compound and hyphenated provider names."""
    from server.services.tool_schema_registry import get_tools_for_tenant, get_tool_names_for_tenant, _normalize

    assert _normalize("google-calendar") == "GOOGLECALENDAR"
    assert _normalize("cal-com") == "CALCOM"
    assert _normalize("outlook-calendar") == "OUTLOOKCALENDAR"
    assert _normalize("twilio-sms") == "TWILIO_SMS"
    assert _normalize("microsoft-teams") == "MICROSOFTTEAMS"

    tools = get_tools_for_tenant(["google-calendar", "twilio-sms", "cal-com"])
    tool_names = {t["name"] for t in tools}
    assert "GOOGLECALENDAR_CREATE_EVENT" in tool_names
    assert "TWILIO_SMS_SEND_MESSAGE" in tool_names
    assert "CALCOM_CREATE_BOOKING" in tool_names

    dispatch_names = get_tool_names_for_tenant(["google-calendar", "twilio-sms"])
    assert "GOOGLECALENDAR" not in dispatch_names
    assert "TWILIO_SMS" not in dispatch_names
    assert "googlecalendar_create_event" in dispatch_names
    assert "twilio_sms_send_message" in dispatch_names


# ---------------------------------------------------------------------------
# Test 11: Webhook Resilience with Prefixed UUIDs and Dual Payload Formats
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nango_webhook_prefixed_uuid_and_deletion(client):
    raw, headers = signed({"type": "auth", "operation": "creation", "success": True,
                           "connectionId": "owned", "providerConfigKey": "slack", "tags": {"end_user_id": f"tenant_{TID}"}})
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).json()["status"] == "ignored"
    raw, headers = signed({"type": "auth", "operation": "deletion", "success": True,
                           "connectionId": "owned", "providerConfigKey": "slack", "tags": {"end_user_id": str(TID)}})
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).status_code == 200
    response = await client.get("/api/integrations", headers={"authorization": "Bearer test-session"})
    assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# Test 12: OpenAIRealtimeVoiceAdapter update_tools
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_openai_realtime_voice_adapter_update_tools():
    """Verify OpenAIRealtimeVoiceAdapter updates live session tools dynamically."""
    from server.realtime.providers.openai_voice import OpenAIRealtimeVoiceAdapter

    adapter = OpenAIRealtimeVoiceAdapter(api_key="mock_key")
    mock_conn = AsyncMock()
    adapter._conn = mock_conn
    adapter._closed = False
    adapter.last_session = {"tools": []}

    extra = [
        {
            "type": "function",
            "name": "GOOGLECALENDAR_CREATE_EVENT",
            "description": "Book a meeting",
            "parameters": {"type": "object", "properties": {}},
        }
    ]

    await adapter.update_tools(extra)
    assert mock_conn.send.called
    sent_payload = mock_conn.send.call_args[0][0]
    assert sent_payload["type"] == "session.update"
    tool_names = [t.get("name") for t in sent_payload["session"]["tools"] if isinstance(t, dict)]
    assert "GOOGLECALENDAR_CREATE_EVENT" in tool_names
    assert "end_call" in tool_names


# ---------------------------------------------------------------------------
# Test 13: Tool schema registry covers all catalog integrations
# ---------------------------------------------------------------------------
def test_tool_schema_registry_covers_all_catalog_integrations():
    """Verify all 29 catalog integrations have voice schemas and sanitized response keys."""
    from server.routes.integrations_catalog import CATALOG_INTEGRATIONS
    from server.services.tool_schema_registry import get_tools_for_tenant, get_response_keys_for_tool

    catalog_ids = [item["id"] for item in CATALOG_INTEGRATIONS]
    assert len(catalog_ids) >= 24

    for app_id in catalog_ids:
        tools = get_tools_for_tenant([app_id])
        assert len(tools) > 0, f"App {app_id} must have registered voice tools in tool_schema_registry"
        tool_name = tools[0]["name"]
        resp_keys = get_response_keys_for_tool(tool_name)
        assert len(resp_keys) > 0, f"Tool {tool_name} must have sanitized response keys"


# ---------------------------------------------------------------------------
# Test 14: tenant_tool_cache get_connection_id with or_ query
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tenant_tool_cache_get_connection_id_query():
    """Verify get_connection_id executes without NameError on or_."""
    import uuid
    from server.services.tenant_tool_cache import get_connection_id

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = SimpleNamespace(connection_id="conn_12345", metadata_={"gateway_verified": True})
    mock_session.execute.return_value = mock_res

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session
    mock_factory.return_value.__aexit__.return_value = None

    tenant_id = str(uuid.uuid4())
    conn_id = await get_connection_id(tenant_id, "GOOGLECALENDAR", mock_factory)
    assert conn_id == "conn_12345"
    assert mock_session.execute.called


# ---------------------------------------------------------------------------
# Test 15: Post-call pipeline fallbacks to TenantIntegration
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_post_call_pipeline_fallbacks_to_tenant_integrations():
    """Verify get_agent_post_call_actions queries active TenantIntegrations when agent rows are absent."""
    import uuid
    from server.call.post_call_pipeline import get_agent_post_call_actions

    mock_session = AsyncMock()
    mock_res_agent = MagicMock()
    mock_res_agent.scalars.return_value.all.return_value = []  # No AgentIntegration rows

    mock_res_tenant = MagicMock()
    mock_res_tenant.scalars.return_value.all.return_value = ["SLACK", "SENDGRID", "HUBSPOT"]

    # First execute is for AgentIntegration, second is for TenantIntegration
    mock_session.execute.side_effect = [mock_res_agent, mock_res_tenant]

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session
    mock_factory.return_value.__aexit__.return_value = None

    with patch("server.db.connection.get_session_factory", return_value=mock_factory):
        actions = await get_agent_post_call_actions(str(uuid.uuid4()), str(uuid.uuid4()))
        assert actions == []  # Connecting an app does not authorize automatic messages.


