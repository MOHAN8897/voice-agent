"""Integration setup, per-agent rules and model alignment.

Covers tenant setup that fills resource ids the model must not invent, the
per-agent rules API, after-call rules on calls without a per-call pick, the
timing of action whitelists, the whole-app tool cap, explicit picks winning over
script pruning, and provider fixes (Calendly time zone, WooCommerce status
guard, Mailchimp upsert).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from server.db.models.integration_models import AgentIntegration, TenantIntegration
from server.routes import integrations as routes
from server.services import call_integrations as ci
from server.services import integration_settings as settings_module
from server.services import tenant_tool_cache
from server.services import tool_router as router_module
from server.services.nango_service import nango_service
from server.services.tool_schema_registry import cap_whole_apps, get_tools_for_agent, get_tools_for_tenant
from server.tests.test_call_integration_selection import AID, FOREIGN, TID, _meta, db  # noqa: F401 - fixtures
from server.tests.test_integration_security_hardening import sqlite_json  # noqa: F401 - JSONB on sqlite


@pytest.fixture
async def api(db, monkeypatch):
    async def principal(request, csrf, authorization):
        return SimpleNamespace(tenant_id=TID, subject=UUID(int=9), role="owner")

    monkeypatch.setattr(routes, "require_api_tenant", principal)
    monkeypatch.setattr(routes, "require_role_permission", lambda role, perm: None)
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://console.example.test") as client:
        yield client


async def _tools(db, selection=None, compiled_text=""):
    tenant_tool_cache.invalidate(str(TID))
    active = await tenant_tool_cache.get_active_app_names(str(TID), db)
    return {t["name"] for t in await get_tools_for_agent(active, str(TID), str(AID), db, selection=selection,
                                                          compiled_text=compiled_text)}


# ------------------------------------------------------------------ setup API
async def test_settings_api_validates_saves_and_keeps_setup_on_reverify(api, db):
    res = await api.put("/api/integrations/SLACK/settings", json={"settings": {"channel": "C0123", "junk": "x"}})
    assert res.status_code == 200 and res.json()["values"] == {"channel": "C0123"} and res.json()["missing"] == []
    got = (await api.get("/api/integrations/SLACK/settings")).json()
    assert got["values"] == {"channel": "C0123"} and got["fields"][0]["has_options"] is True
    bad = await api.put("/api/integrations/GOOGLECALENDAR/settings", json={"settings": {"day_start": "18:00", "day_end": "09:00"}})
    assert bad.status_code == 422
    assert (await api.put("/api/integrations/HUBSPOT/settings", json={"settings": {}})).status_code == 404  # not verified
    async with db() as session:
        row = (await session.execute(select(TenantIntegration).where(TenantIntegration.app_name == "SLACK"))).scalar_one()
        assert routes._verified(row.metadata_) == {"settings": {"channel": "C0123"}, "gateway_verified": True}


async def test_catalog_reports_setup_state_per_tenant(api, monkeypatch):
    monkeypatch.setattr(routes.nango_service, "get_configured_providers", AsyncMock(return_value={"slack"}))
    items = {i["id"]: i for i in (await api.get("/api/integrations/catalog")).json()["items"]}
    assert items["SLACK"]["setup_missing"] == ["Channel"] and items["SLACK"]["call_setup_note"]
    assert items["TODOIST"]["setup_fields"] == [] and items["TODOIST"]["call_setup_note"] is None
    assert items["CALCOM"]["auth_type"] == "api_key"  # Nango's cal-com-v2 is an API-key integration
    assert items["TWILIO_SMS"]["timing"] == "in_call"


async def test_options_list_live_choices_through_the_tenants_connection(api, monkeypatch):
    seen = {}

    async def fake(resource, client, base, headers, saved):
        seen.update(resource=resource, connection=headers["Connection-Id"], provider=headers["Provider-Config-Key"])
        return [{"value": "C1", "label": "#sales"}]

    monkeypatch.setattr(settings_module, "list_resources", fake)
    res = await api.get("/api/integrations/SLACK/options?field=channel")
    assert res.json()["options"] == [{"value": "C1", "label": "#sales"}]
    assert seen == {"resource": "slack_channels", "connection": "c-SLACK", "provider": "slack"}
    assert (await api.get("/api/integrations/SLACK/options?field=text")).status_code == 404


# ------------------------------------------------------------------ agent rules
async def test_agent_rules_api_round_trip_and_ownership(api, db):
    listed = (await api.get(f"/api/integrations/agent-rules?agentId={AID}")).json()["items"]
    apps = {i["app"]: i for i in listed}
    assert set(apps) == {"GOOGLECALENDAR", "GMAIL", "TODOIST", "CALENDLY", "SLACK"}  # verified apps only
    assert apps["GOOGLECALENDAR"]["default"]["enabled"] is True and apps["GMAIL"]["default"]["enabled"] is False
    assert apps["CALENDLY"]["default"]["enabled"] is False  # one default calendar, as at runtime
    assert apps["SLACK"]["configured"] is False and apps["SLACK"]["setupNote"]
    assert "GOOGLECALENDAR_FIND_SLOTS" not in {a["name"] for a in apps["GOOGLECALENDAR"]["actions"]}
    body = {"rules": [{"app": "GMAIL", "enabled": True, "timing": "in_call", "actions": ["gmail_send_email"]},
                      {"app": "CALENDLY", "enabled": False, "timing": "in_call"}]}
    assert (await api.put(f"/api/integrations/agent-rules?agentId={AID}", json=body)).status_code == 200
    names = await _tools(db)
    assert "GMAIL_SEND_EMAIL" in names and "GMAIL_CREATE_DRAFT" not in names
    # A calendar turned on explicitly is the only one; the console must not show another as on.
    limited = {"rules": [{"app": "GOOGLECALENDAR", "enabled": True, "timing": "in_call", "actions": ["GOOGLECALENDAR_FIND_FREE_SLOTS"]}]}
    assert (await api.put(f"/api/integrations/agent-rules?agentId={AID}", json=limited)).status_code == 200
    after = {i["app"]: i for i in (await api.get(f"/api/integrations/agent-rules?agentId={AID}")).json()["items"]}
    assert after["CALENDLY"]["default"]["enabled"] is False
    assert {n for n in await _tools(db) if n.startswith(("GOOGLECALENDAR_", "CALENDLY_"))} == {"GOOGLECALENDAR_FIND_FREE_SLOTS"}
    body = {"rules": [{"app": "GMAIL", "enabled": True, "timing": "in_call", "actions": ["gmail_send_email"]},
                      {"app": "CALENDLY", "enabled": False, "timing": "in_call"}]}
    assert (await api.put(f"/api/integrations/agent-rules?agentId={AID}", json=body)).status_code == 200
    names = await _tools(db)
    assert not any(n.startswith("CALENDLY_") for n in names)
    bad = {"rules": [{"app": "GOOGLECALENDAR", "enabled": True, "timing": "post_call"}]}
    assert (await api.put(f"/api/integrations/agent-rules?agentId={AID}", json=bad)).status_code == 422
    mixed = {"rules": [{"app": "GMAIL", "enabled": True, "timing": "in_call", "actions": ["SLACK_SEND_MESSAGE"]}]}
    assert (await api.put(f"/api/integrations/agent-rules?agentId={AID}", json=mixed)).status_code == 422
    assert (await api.get(f"/api/integrations/agent-rules?agentId={FOREIGN}")).status_code == 404


async def test_after_call_rule_on_a_call_without_a_pick_builds_its_arguments(db, monkeypatch):
    from server.call import post_call_pipeline as pcp

    async with db() as session:
        session.add(AgentIntegration(tenant_id=TID, agent_id=AID, app_name="TODOIST", enabled=True,
                                     timing_mode="post_call", action_whitelist=[]))
        await session.commit()
    _meta(monkeypatch, {"in": {"tenant_id": str(TID), "direction": "inbound", "caller_id": "+919800000000"}})
    monkeypatch.setattr(pcp.call_store, "get", AsyncMock(return_value={"tenant_id": str(TID), "agent_id": str(AID)}))
    import server.db.connection as connection_module

    monkeypatch.setattr(connection_module, "get_session_factory", lambda: db)
    calls = []

    async def route(tenant_id, agent_id, call_id, action, arguments, *, timing):
        calls.append((action, arguments, timing))
        return {"status": "success"}

    monkeypatch.setattr(router_module.tool_router, "route_and_execute", route)
    outcome = {"summary_en": "Asked for prices.", "next_action": "Send the price list",
               "extracted_fields": {"name": "Ravi Kumar"}}
    await pcp.reconcile_and_dispatch_post_call("in", outcome)
    assert calls == [("TODOIST_CREATE_TASK", {"content": "Follow up with Ravi Kumar: Send the price list"}, "post_call")]


def test_note_builders_for_team_tools():
    outcome = {"summary_en": "Wants 50 visiting cards.", "next_action": "Share artwork options",
               "extracted_fields": {"name": "Asha", "phone": "+919811111111", "email": "asha@example.com"}}
    slack = ci.post_call_arguments("SLACK_SEND_MESSAGE", outcome, {})
    assert slack["text"].startswith("Call with Asha (+919811111111): Wants 50 visiting cards.") and "Next step" in slack["text"]
    assert ci.post_call_arguments("JIRA_CREATE_ISSUE", outcome, {})["summary"] == "Follow up with Asha"
    assert ci.post_call_arguments("AIRTABLE_CREATE_RECORD", outcome, {})["fields"]["Email"] == "asha@example.com"
    assert ci.post_call_arguments("SLACK_SEND_MESSAGE", {}, {}) is None


async def test_router_fills_setup_values_and_ignores_model_supplied_ones(db, monkeypatch):
    async with db() as session:
        row = (await session.execute(select(TenantIntegration).where(TenantIntegration.app_name == "SLACK"))).scalar_one()
        row.metadata_ = {"gateway_verified": True, "settings": {"channel": "C-REAL"}}
        session.add(AgentIntegration(tenant_id=TID, agent_id=AID, app_name="SLACK", enabled=True,
                                     timing_mode="in_call", action_whitelist=[]))
        await session.commit()
    router = router_module.DialtactToolRouter()
    execute = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(router.nango, "execute_in_call_tool", execute)
    result = await router.route_and_execute(str(TID), str(AID), "call-1", "SLACK_SEND_MESSAGE",
                                            {"channel": "#general", "text": "Caller wants a callback"})
    assert result["status"] == "success"
    assert execute.await_args.kwargs["params"] == {"text": "Caller wants a callback", "channel": "C-REAL"}


# ------------------------------------------------------------------ exposure rules
async def test_explicit_pick_beats_script_pruning_and_post_call_whitelist(db):
    script = "--- CALLING SCRIPT ---\nWe sell printed visiting cards and flex banners. Share prices and take the caller's name."
    assert not any(n.startswith("GOOGLECALENDAR_") for n in await _tools(db, compiled_text=script))
    picked = await _tools(db, [{"app": "GOOGLECALENDAR", "mode": "in_call"}], compiled_text=script)
    assert "GOOGLECALENDAR_CREATE_EVENT" in picked  # the tenant chose it for this call
    async with db() as session:
        session.add(AgentIntegration(tenant_id=TID, agent_id=AID, app_name="GMAIL", enabled=True,
                                     timing_mode="post_call", action_whitelist=["GMAIL_CREATE_DRAFT"]))
        await session.commit()
    # An after-call limit does not restrict what a call picked for during the call.
    assert "GMAIL_SEND_EMAIL" in await _tools(db, [{"app": "GMAIL", "mode": "in_call"}])
    router = router_module.DialtactToolRouter()
    _meta_calls = {"c": {"tenant_id": str(TID), "integration_selection": [{"app": "GMAIL", "mode": "in_call"}]}}
    from server.call.call_ledger import call_ledger

    ci.clear_cache()
    with patch.object(call_ledger, "read_meta", lambda call_id: _meta_calls.get(call_id, {})):
        assert await router.authorized(str(TID), str(AID), "GMAIL_SEND_EMAIL", timing="in_call", call_id="c")


def test_tool_cap_keeps_whole_apps():
    tools = get_tools_for_tenant(["GOOGLECALENDAR", "HUBSPOT", "SHOPIFY", "ZENDESK"])
    kept = cap_whole_apps(tools, 10)
    apps = [t["name"].split("_")[0] for t in kept]
    assert apps.count("GOOGLECALENDAR") == 5 and apps.count("HUBSPOT") == 4 and "SHOPIFY" not in apps
    assert "GOOGLECALENDAR_FIND_SLOTS" not in {t["name"] for t in tools}


# ------------------------------------------------------------------ provider fixes
def _ok(payload, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = payload
    return response


async def test_calendly_times_are_returned_in_the_callers_zone():
    data = {"collection": [{"status": "available", "start_time": "2030-01-02T03:30:00Z"}]}
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=_ok(data))):
        res = await nango_service._execute_proxy_tool("calendly", "c", "CALENDLY_GET_AVAILABLE_TIMES", {
            "event_type_uri": "https://api.calendly.com/event_types/abc", "start_date": "2030-01-02", "end_date": "2030-01-02"})
    assert res["slots"] == ["2030-01-02T09:00:00+05:30"] and res["time_zone"] == "Asia/Kolkata"


async def test_woocommerce_never_changes_a_completed_order():
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=_ok({"id": 9, "status": "completed"}))), \
            patch("httpx.AsyncClient.put", new_callable=AsyncMock) as put:
        res = await nango_service._execute_proxy_tool("woocommerce", "c", "WOOCOMMERCE_UPDATE_ORDER_STATUS",
                                                      {"order_id": "9", "status": "cancelled"})
    assert res["status"] == "error"
    put.assert_not_awaited()


async def test_mailchimp_subscribe_is_an_idempotent_upsert():
    with patch("httpx.AsyncClient.put", AsyncMock(return_value=_ok({"id": "abc"}))) as put:
        res = await nango_service._execute_proxy_tool("mailchimp", "c", "MAILCHIMP_ADD_SUBSCRIBER",
                                                      {"list_id": "L1", "email": "Asha@Example.com"})
    assert res["status"] == "subscribed"
    assert put.call_args[0][0].endswith("/proxy/3.0/lists/L1/members/" + __import__("hashlib").md5(b"asha@example.com").hexdigest())
    assert put.call_args.kwargs["json"]["status_if_new"] == "subscribed"


def test_outgoing_messages_with_placeholder_text_are_refused():
    """Live check: with no address in the script the model texted "[Your clinic address would be sent here]"."""
    from server.services.tool_schema_registry import validate_tool_arguments

    sms = {"to": "+919876543210"}
    assert validate_tool_arguments("TWILIO_SMS_SEND_MESSAGE", {**sms, "body": "Address: [Your clinic address would be sent here]"})
    assert validate_tool_arguments("GMAIL_SEND_EMAIL", {"to": "a@example.com", "subject": "Hi", "body": "Hello {{name}}"})
    assert validate_tool_arguments("TWILIO_SMS_SEND_MESSAGE", {**sms, "body": "12 MG Road [opposite bus stand]"}) is None
    # Lookups are never refused for brackets in a search term.
    assert validate_tool_arguments("ZENDESK_SEARCH_TICKETS", {"query": "[your order]"}) is None
