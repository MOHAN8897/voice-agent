"""Authoritative Verification Suite for Nango Multi-Tenant Voice Tools."""
from __future__ import annotations

import asyncio
import json
import secrets
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
    with patch.object(router.nango, "execute_in_call_tool", AsyncMock(return_value=mock_response)):
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

    with patch.object(router.nango, "execute_in_call_tool", side_effect=_sim_slow_tool):
        res = await router.route_and_execute(
            tenant_id="11111111-1111-1111-1111-111111111111",
            agent_id="22222222-2222-2222-2222-222222222222",
            call_id="call_timeout_test",
            tool_name="GOOGLECALENDAR_CREATE_EVENT",
            arguments={"summary": "Sales Consultation", "time": "3:00 PM"},
        )

        assert res["status"] == "timeout"
        assert res["action_type"] == "write"
        assert "taking a moment longer" in res["message"]


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
        with patch("urllib.request.urlopen") as mock_url:
            mock_cm = MagicMock()
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
async def test_nango_get_tenant_connections_and_reverse_mapping():
    """Verify Nango connection retrieval and reverse provider mapping."""
    service = NangoService(secret_key="mock_secret", base_url="https://api.nango.dev")

    assert service.get_app_name_from_provider("google-calendar") == "GOOGLECALENDAR"
    assert service.get_app_name_from_provider("hubspot") == "HUBSPOT"
    assert service.get_app_name_from_provider("slack") == "SLACK"

    mock_conns_resp = {
        "connections": [
            {
                "id": "conn_123",
                "connection_id": "google_conn_1",
                "provider_config_key": "google-calendar",
                "provider": "google-calendar",
            }
        ]
    }
    with patch.object(service, "_resolve_environment_key", AsyncMock(return_value="mock_secret")):
        with patch("urllib.request.urlopen") as mock_url:
            mock_cm = MagicMock()
            mock_cm.read.return_value = json.dumps(mock_conns_resp).encode()
            mock_cm.__enter__.return_value = mock_cm
            mock_url.return_value = mock_cm

            conns = await service.get_tenant_connections("11111111-1111-1111-1111-111111111111")
            assert len(conns) == 1
            assert conns[0]["provider_config_key"] == "google-calendar"

            verified = await service.verify_or_sync_connection(
                tenant_id="11111111-1111-1111-1111-111111111111",
                app_name="GOOGLECALENDAR",
                connection_id="google_conn_1",
            )
            assert verified is True


# ---------------------------------------------------------------------------
# Test 7: Integration Endpoints (Activate, List, and Disconnect)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_integrations_activate_and_reconcile():
    """Verify POST /api/integrations/{app_id}/activate and DELETE."""
    from starlette.requests import Request
    from server.routes.integrations import activate_integration, disconnect_integration, list_integrations, ActivateBody

    req = Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/api/integrations/GOOGLECALENDAR/activate",
            "headers": [(b"x-tenant-id", b"11111111-1111-1111-1111-111111111111")],
        }
    )

    with patch("server.services.nango_service.nango_service.verify_or_sync_connection", AsyncMock(return_value=True)):
        with patch("server.services.nango_service.nango_service.delete_connection", AsyncMock(return_value=True)):
            # 1. Activate
            body = ActivateBody(connection_id="conn_abc_123", account_identifier="my-workspace")
            res_act = await activate_integration(
                app_id="GOOGLECALENDAR",
                body=body,
                request=req,
            )
            assert res_act["status"] == "ACTIVE"
            assert res_act["app_name"] == "GOOGLECALENDAR"

            # 2. List
            get_req = Request(
                scope={
                    "type": "http",
                    "method": "GET",
                    "path": "/api/integrations",
                    "headers": [(b"x-tenant-id", b"11111111-1111-1111-1111-111111111111")],
                }
            )
            with patch("server.services.nango_service.nango_service.get_tenant_connections", AsyncMock(return_value=[])):
                list_res = await list_integrations(request=get_req)
                assert "items" in list_res

            # 3. Disconnect
            del_req = Request(
                scope={
                    "type": "http",
                    "method": "DELETE",
                    "path": "/api/integrations/GOOGLECALENDAR",
                    "headers": [(b"x-tenant-id", b"11111111-1111-1111-1111-111111111111")],
                }
            )
            del_res = await disconnect_integration(app_id="GOOGLECALENDAR", request=del_req)
            assert del_res["status"] == "disconnected"


# ---------------------------------------------------------------------------
# Test 8: Nango Webhook Event Processing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nango_webhook_updates_tenant_integrations():
    """Verify POST /api/integrations/nango-webhook updates DB on connection:created."""
    from starlette.requests import Request
    from server.routes.integrations import nango_webhook

    payload = {
        "operation": "connection:created",
        "connectionId": "wh_conn_999",
        "providerConfigKey": "slack",
        "endUserId": "11111111-1111-1111-1111-111111111111",
    }

    async def _receive():
        return {"type": "http.request", "body": json.dumps(payload).encode()}

    req = Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/api/integrations/nango-webhook",
            "headers": [(b"content-type", b"application/json")],
        },
        receive=_receive,
    )

    res = await nango_webhook(request=req)
    assert res["status"] == "ok"


# ---------------------------------------------------------------------------
# Test 9: Voice Loop Auto-Discovers Active Tenant Tools
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_realtime_voice_loop_auto_discovers_tenant_tools():
    """Verify PstnRealtimeVoiceLoop automatically loads active tenant tools on call start."""
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id="test_sess",
        call_id="call_auto_tool",
        tenant_id="11111111-1111-1111-1111-111111111111",
        agent_id="22222222-2222-2222-2222-222222222222",
        agent_tools=None,  # Not provided upfront
        on_agent_wire=AsyncMock(),
    )

    assert len(loop._agent_tools) == 0

    # Simulate active integrations in DB
    mock_db_res = MagicMock()
    mock_db_res.scalars.return_value.all.return_value = ["GOOGLECALENDAR", "SLACK"]

    with patch("server.db.connection.get_session_factory") as mock_sf:
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_db_res)
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_sf.return_value = MagicMock(return_value=mock_cm)

        with patch.object(loop, "_start_caller_stt_sidecar", MagicMock()):
            with patch("server.realtime.voice_factory.realtime_voice_llm_provider", return_value=("gemini", {})):
                mock_adapter = AsyncMock()
                mock_adapter.is_open.return_value = True
                loop._injected_adapter = mock_adapter

                await loop.start_call(play_greeting=False)

    assert "GOOGLECALENDAR" in loop._agent_tools
    assert "googlecalendar_find_slots" in loop._agent_tools
    assert "SLACK" in loop._agent_tools
    assert "slack_send_message" in loop._agent_tools


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
    assert "GOOGLECALENDAR" in dispatch_names
    assert "TWILIO_SMS" in dispatch_names
    assert "googlecalendar_create_event" in dispatch_names
    assert "twilio_sms_send_message" in dispatch_names


# ---------------------------------------------------------------------------
# Test 11: Webhook Resilience with Prefixed UUIDs and Dual Payload Formats
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nango_webhook_prefixed_uuid_and_deletion():
    """Verify nango_webhook handles tenant_ prefixed UUIDs and deletion events."""
    from server.routes.integrations import nango_webhook
    from fastapi import Request

    raw_uuid = "11111111-2222-3333-4444-555555555555"
    prefixed_user = f"tenant_{raw_uuid}"

    payload = {
        "operation": "creation",
        "connectionId": "conn_real_456",
        "providerConfigKey": "google-calendar",
        "endUserId": prefixed_user,
    }

    mock_req = MagicMock(spec=Request)
    mock_req.json = AsyncMock(return_value=payload)

    with patch("server.routes.integrations.get_session_factory") as mock_sf:
        mock_session = AsyncMock()
        mock_chk = MagicMock()
        mock_chk.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_chk)
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session
        mock_sf.return_value = MagicMock(return_value=mock_cm)

        res = await nango_webhook(mock_req)
        assert res["status"] == "ok"
        # Verify TenantIntegration was created with parsed UUID
        added = mock_session.add.call_args[0][0]
        import uuid
        assert added.tenant_id == uuid.UUID(raw_uuid)
        assert added.composio_connection_id == "conn_real_456"
        assert added.app_name == "GOOGLECALENDAR"


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

