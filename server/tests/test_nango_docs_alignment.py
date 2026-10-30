"""Nango gateway behaviour that must match the documented API and provider configs.

Covers auth `refresh` webhooks, signing-key rotation, auth vs sync connection
errors, the current delete path, proxy retry policy, provider base URLs that
already carry a version segment, and caller-safe failures for lookups.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select

from server.db.models.integration_models import TenantIntegration
from server.routes import integrations as routes
from server.services.nango_service import NangoService, nango_service
from server.tests.test_integration_security_hardening import TID, client, db, signed  # noqa: F401 - fixtures

AUTH = {"authorization": "Bearer test-session"}


def _refresh(success: bool, connection_id: str = "owned") -> dict:
    payload = {"type": "auth", "operation": "refresh", "success": success, "tags": {"end_user_id": str(TID), "organization_id": str(TID)},
               "connectionId": connection_id, "providerConfigKey": "slack", "provider": "slack"}
    if not success:
        payload["error"] = {"type": "refresh_token_external_error", "description": "invalid_grant"}
    return payload


async def _row(factory):
    async with factory() as session:
        return (await session.execute(select(TenantIntegration))).scalar_one()


async def test_refresh_failure_disables_tool_and_recovery_restores_it(client, db, monkeypatch):
    raw, headers = signed(_refresh(False))
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).json()["status"] == "ok"
    row = await _row(db)
    assert row.status == "ERROR"
    assert row.metadata_["gateway_verified"] is False and row.metadata_["needs_reauth"] is True

    listed = (await client.get("/api/integrations", headers=AUTH)).json()["items"]
    assert [(i["app_name"], i["status"], i["needs_reauth"]) for i in listed] == [("SLACK", "ERROR", True)]

    monkeypatch.setattr(routes.nango_service, "verify_or_sync_connection", AsyncMock(return_value=True))
    raw, headers = signed(_refresh(True))
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).json()["status"] == "ok"
    row = await _row(db)
    assert row.status == "ACTIVE" and row.metadata_ == {"gateway_verified": True}


async def test_refresh_webhook_for_other_connection_or_unknown_app_row_is_ignored(client, db, monkeypatch):
    raw, headers = signed(_refresh(False, connection_id="someone-else"))
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).json()["status"] == "ignored"
    assert (await _row(db)).status == "ACTIVE"
    # An unconfirmed recovery never re-enables a tool.
    async with db() as session:
        (await session.execute(select(TenantIntegration))).scalar_one().status = "ERROR"
        await session.commit()
    monkeypatch.setattr(routes.nango_service, "verify_or_sync_connection", AsyncMock(return_value=False))
    raw, headers = signed(_refresh(True))
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=headers)).json()["status"] == "ignored"
    assert (await _row(db)).status == "ERROR"


async def test_previous_signing_key_is_accepted_during_rotation(client, db, monkeypatch):
    import hashlib
    import hmac
    import json

    raw = json.dumps({"type": "sync"}).encode()
    old = {"x-nango-hmac-sha256": hmac.new(b"old-key", raw, hashlib.sha256).hexdigest()}
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=old)).status_code == 401
    monkeypatch.setenv("NANGO_WEBHOOK_SIGNING_KEY_PREVIOUS", "old-key")
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=old)).json()["status"] == "ignored"
    # The legacy plain-SHA256 header is never accepted on its own.
    legacy = {"x-nango-signature": hashlib.sha256(b"test-webhook-key" + raw).hexdigest()}
    assert (await client.post("/api/integrations/nango-webhook", content=raw, headers=legacy)).status_code == 401


async def test_console_reconciliation_marks_auth_failed_connection(client, db, monkeypatch):
    monkeypatch.setattr(routes.nango_service, "is_configured", lambda: True)
    live = [{"connection_id": "owned", "provider_config_key": "slack", "tags": {"end_user_id": str(TID)},
             "errors": [{"type": "auth", "log_id": "x"}]}]
    lister = AsyncMock(return_value=live)
    monkeypatch.setattr(routes.nango_service, "get_tenant_connections", lister)
    items = (await client.get("/api/integrations", headers=AUTH)).json()["items"]
    assert lister.await_args.kwargs == {"include_auth_errors": True}
    assert items[0]["needs_reauth"] is True and (await _row(db)).status == "ERROR"


async def test_reconnect_revokes_the_superseded_gateway_connection(client, db, monkeypatch):
    monkeypatch.setattr(routes.nango_service, "verify_or_sync_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(routes.nango_service, "get_tenant_connections", AsyncMock(return_value=[
        {"connection_id": "owned", "provider_config_key": "slack"}, {"connection_id": "fresh", "provider_config_key": "slack"}]))
    revoke = AsyncMock(return_value=True)
    monkeypatch.setattr(routes.nango_service, "delete_connection", revoke)
    response = await client.post("/api/integrations/SLACK/activate", headers=AUTH, json={"connection_id": "fresh"})
    assert response.status_code == 200
    revoke.assert_awaited_once_with(connection_id="owned", app_name="SLACK")
    assert (await _row(db)).connection_id == "fresh"
    # Re-activating the same connection revokes nothing.
    revoke.reset_mock()
    assert (await client.post("/api/integrations/SLACK/activate", headers=AUTH, json={"connection_id": "fresh"})).status_code == 200
    revoke.assert_not_awaited()


def test_only_auth_errors_make_a_connection_unusable():
    base = {"connection_id": "c", "tags": {"end_user_id": "t"}}
    assert NangoService.connection_belongs_to_tenant({**base, "errors": [{"type": "sync", "log_id": "1"}]}, "t")
    assert not NangoService.connection_belongs_to_tenant({**base, "errors": [{"type": "auth", "log_id": "1"}]}, "t")
    assert not NangoService.connection_belongs_to_tenant({**base, "errors": ["unexpected"]}, "t")


async def test_delete_uses_current_connections_path(monkeypatch):
    service = NangoService(secret_key="test-only")
    seen = {}

    def fake(req, timeout=5.0):
        seen["url"], seen["method"] = req.full_url, req.get_method()
        return MagicMock(status=200, __enter__=lambda s: s, __exit__=lambda *a: None)

    monkeypatch.setattr("server.services.nango_service._safe_urlopen", fake)
    assert await service.delete_connection("conn-1", "SLACK")
    assert seen == {"url": "https://api.nango.dev/connections/conn-1?provider_config_key=slack", "method": "DELETE"}


def _ok(payload, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = payload
    return response


async def test_todoist_uses_unified_api_v1_and_forwards_priority():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_ok({"id": "t1", "content": "Call back"})) as post:
        result = await nango_service._execute_proxy_tool("todoist", "c", "TODOIST_CREATE_TASK",
                                                         {"content": "Call back", "due_string": "tomorrow", "priority": 4})
    assert result["status"] == "success"
    assert post.call_args[0][0].endswith("/proxy/api/v1/tasks")
    assert post.call_args.kwargs["json"] == {"content": "Call back", "due_string": "tomorrow", "priority": 4}
    assert "Retries" not in post.call_args.kwargs["headers"]


async def test_calcom_paths_do_not_repeat_base_version_and_send_api_version():
    slots = {"status": "success", "data": {"2026-11-02": [{"start": "2026-11-02T10:00:00.000+05:30"}]}}
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=_ok(slots)) as get:
        result = await nango_service._execute_proxy_tool("cal-com-v2", "c", "CALCOM_GET_AVAILABLE_SLOTS",
                                                         {"event_type_id": 7, "date": "2026-11-02"})
    assert result["slots"] == ["2026-11-02T10:00:00.000+05:30"]
    assert get.call_args[0][0].endswith("/proxy/slots")
    headers = get.call_args.kwargs["headers"]
    assert headers["cal-api-version"] == "2024-09-04" and headers["Retries"] == "1"
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_ok({"data": {"uid": "u1"}}, 201)) as post:
        await nango_service._execute_proxy_tool("cal-com-v2", "c", "CALCOM_CREATE_BOOKING", {
            "event_type_id": 7, "start": "2026-11-02T04:30:00Z", "name": "A", "email": "a@example.test", "notes": "n"})
    assert post.call_args[0][0].endswith("/proxy/bookings")
    assert post.call_args.kwargs["headers"]["cal-api-version"] == "2024-08-13"
    assert post.call_args.kwargs["json"]["bookingFieldsResponses"] == {"notes": "n"}


async def test_jira_and_discord_use_provider_rooted_paths():
    sites = _ok([{"id": "cloud-1", "url": "https://acme.atlassian.net"}])
    issue = _ok({"fields": {"status": {"name": "Done"}}})
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=[sites, issue]) as get:
        result = await nango_service._execute_proxy_tool("jira", "c", "JIRA_GET_ISSUE", {"issue_key": "OPS-1"})
    assert result["issue_status"] == "Done"
    assert get.call_args[0][0].endswith("/proxy/ex/jira/cloud-1/rest/api/3/issue/OPS-1")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_ok({"id": "m1"})) as post:
        await nango_service._execute_proxy_tool("discord-bot", "c", "DISCORD_SEND_MESSAGE", {"channel_id": "42", "content": "hi"})
    assert post.call_args[0][0].endswith("/proxy/api/v10/channels/42/messages")


async def test_failed_lookup_is_unavailable_but_failed_write_stays_unknown(monkeypatch):
    service = NangoService(secret_key="test-only")
    monkeypatch.setattr(service, "_get_nango_connection_id", AsyncMock(return_value="c"))
    monkeypatch.setattr(service, "_execute_proxy_tool", AsyncMock(side_effect=httpx.ConnectTimeout("slow")))
    read = await service.execute_in_call_tool("t", "GOOGLECALENDAR_FIND_FREE_SLOTS", {"date": "2026-11-02"})
    assert read["status"] == "unavailable" and "Google Calendar" in read["message"]
    write = await service.execute_in_call_tool("t", "GOOGLECALENDAR_CREATE_EVENT", {
        "summary": "x", "start": "2026-11-02T10:00:00+05:30", "end": "2026-11-02T10:30:00+05:30"})
    assert write["status"] == "unknown"
    request = httpx.Request("POST", "https://api.nango.dev/proxy")
    monkeypatch.setattr(service, "_execute_proxy_tool", AsyncMock(side_effect=httpx.HTTPStatusError(
        "expired", request=request, response=httpx.Response(401, request=request))))
    expired = await service.execute_in_call_tool("t", "GOOGLECALENDAR_CREATE_EVENT", {
        "summary": "x", "start": "2026-11-02T10:00:00+05:30", "end": "2026-11-02T10:30:00+05:30"})
    assert expired["status"] == "error" and "re-authorized" in expired["message"]


def test_schema_requires_what_the_endpoint_needs():
    from server.services.tool_schema_registry import validate_tool_arguments

    assert validate_tool_arguments("DISCORD_SEND_MESSAGE", {"content": "hi"})
    assert validate_tool_arguments("MONDAY_CREATE_ITEM", {"item_name": "x"})
    assert validate_tool_arguments("TODOIST_CREATE_TASK", {"content": "x", "priority": 9})
    assert validate_tool_arguments("TODOIST_CREATE_TASK", {"content": "x", "priority": 4}) is None
