"""Per-call / per-campaign integration selection.

Covers selection validation (shape, unsupported apps, not connected, another
tenant's agent), the exposure rule selected ∩ connected-verified ∩ agent-allowed,
campaign inheritance (and that an imported contact column cannot inject a
selection), post-call gating, the prompt rows, and the console options API.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.db.models.entities import Agent, Base, Tenant
from server.db.models.integration_models import AgentIntegration, TenantIntegration, ToolExecution
from server.db.models.phase5_models import Campaign
from server.routes import integrations as routes
from server.services import call_integrations as ci
from server.services import tenant_tool_cache
from server.services import tool_router as router_module
from server.services.tool_schema_registry import get_tools_for_agent
from server.tests.test_integration_security_hardening import sqlite_json  # noqa: F401 - JSONB on sqlite

TID, OTHER, AID, FOREIGN, CAMP = [UUID(f"bbbbbbbb-0000-4000-8000-{i:012d}") for i in (1, 2, 3, 4, 5)]


@pytest.fixture
async def db(monkeypatch):
    models = [Tenant, Agent, TenantIntegration, AgentIntegration, ToolExecution, Campaign]
    for model in models:
        for column in model.__table__.columns:
            if isinstance(column.type, ARRAY):
                monkeypatch.setattr(column, "type", column.type.with_variant(JSON(), "sqlite"))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[m.__table__ for m in models]))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import server.db.connection as connection_module

    monkeypatch.setattr(connection_module, "get_session_factory", lambda: factory)
    monkeypatch.setattr(routes, "get_session_factory", lambda: factory)
    monkeypatch.setattr(router_module, "get_session_factory", lambda: factory)
    async with factory() as session:
        session.add_all([
            Tenant(tenant_id=TID, name="First"), Tenant(tenant_id=OTHER, name="Other"),
            Agent(agent_id=AID, tenant_id=TID, name="Own agent"),
            Agent(agent_id=FOREIGN, tenant_id=OTHER, name="Foreign agent"),
            # The live test tenant's set: Calendar, Gmail, Todoist, Calendly verified.
            *[TenantIntegration(tenant_id=TID, app_name=app, connection_id=f"c-{app}", status="ACTIVE",
                                metadata_={"gateway_verified": True})
              for app in ("GOOGLECALENDAR", "GMAIL", "TODOIST", "CALENDLY", "SLACK")],
            # Connected but never verified: never selectable.
            TenantIntegration(tenant_id=TID, app_name="HUBSPOT", connection_id="c-h", status="ACTIVE", metadata_={}),
            # Another tenant's Shopify must not count for this tenant.
            TenantIntegration(tenant_id=OTHER, app_name="SHOPIFY", connection_id="c-s", status="ACTIVE",
                              metadata_={"gateway_verified": True}),
            Campaign(campaign_id=CAMP, tenant_id=TID, agent_id=AID, name="Spring", status="running",
                     schedule={"integration_selection": [{"app": "TODOIST", "mode": "post_call"},
                                                         {"app": "GOOGLECALENDAR", "mode": "in_call"}]},
                     retry_rules={}),
        ])
        await session.commit()
    tenant_tool_cache.invalidate(str(TID))
    tenant_tool_cache.invalidate(str(OTHER))
    ci.clear_cache()
    yield factory
    ci.clear_cache()
    tenant_tool_cache.invalidate(str(TID))
    await engine.dispose()


def _meta(monkeypatch, metas: dict):
    from server.call.call_ledger import call_ledger

    monkeypatch.setattr(call_ledger, "read_meta", lambda call_id: metas.get(call_id, {}))
    ci.clear_cache()


# ------------------------------------------------------------------ validation
def test_shape_and_unsupported_apps_are_rejected():
    assert ci.normalize_selection(None) is None and ci.normalize_selection([]) is None
    assert ci.normalize_selection([{"app": "google-calendar", "mode": "in_call"}, "todoist"]) == [
        {"app": "GOOGLECALENDAR", "mode": "in_call"}, {"app": "TODOIST", "mode": "post_call"},  # catalog default
    ]
    for bad, code in (
        ([{"app": "SLACK", "mode": "post_call"}], "integration_not_available"),      # needs a channel configured
        ([{"app": "GOOGLECALENDAR", "mode": "post_call"}], "integration_mode_unsupported"),
        ([{"app": "TODOIST", "mode": "in_call"}, {"app": "TODOIST", "mode": "post_call"}], "integration_selection_invalid"),
        ([{"app": "../etc", "mode": "in_call"}], "integration_selection_invalid"),
        ("GMAIL", "integration_selection_invalid"),
        ([{"app": "GMAIL"}] * 13, "integration_selection_invalid"),
    ):
        with pytest.raises(ci.SelectionError) as err:
            ci.normalize_selection(bad)
        assert err.value.code == code and err.value.status_code == 422


async def test_selection_must_be_connected_verified_and_owned(db):
    ok = await ci.validate_selection(str(TID), str(AID), [{"app": "GMAIL", "mode": "post_call"}])
    assert ok == [{"app": "GMAIL", "mode": "post_call"}]
    for app, status in (("HUBSPOT", 409), ("SHOPIFY", 409), ("ZOOM", 409)):  # unverified / other tenant's / absent
        with pytest.raises(ci.SelectionError) as err:
            await ci.validate_selection(str(TID), str(AID), [{"app": app, "mode": "in_call"}])
        assert err.value.status_code == status and err.value.code == "integration_not_connected"
    with pytest.raises(ci.SelectionError) as err:  # another tenant's agent
        await ci.validate_selection(str(TID), str(FOREIGN), [{"app": "GMAIL", "mode": "in_call"}])
    assert err.value.status_code == 404
    async with db() as session:
        session.add(AgentIntegration(tenant_id=TID, agent_id=AID, app_name="GMAIL", enabled=False, timing_mode="post_call"))
        await session.commit()
    with pytest.raises(ci.SelectionError) as err:
        await ci.validate_selection(str(TID), str(AID), [{"app": "GMAIL", "mode": "in_call"}])
    assert err.value.code == "integration_disabled_for_agent"


# ------------------------------------------------------------------ exposure
async def _tool_names(db, selection):
    active = await tenant_tool_cache.get_active_app_names(str(TID), db)
    tools = await get_tools_for_agent(active, str(TID), str(AID), db, selection=selection)
    return {t["name"].split("_")[0] for t in tools}, {t["name"] for t in tools}


async def test_exposed_tools_are_selected_connected_and_agent_allowed(db):
    apps, _ = await _tool_names(db, None)
    assert apps == {"GOOGLECALENDAR", "CALENDLY"}  # agent defaults: catalog in-call apps only
    apps, names = await _tool_names(db, [{"app": "GMAIL", "mode": "in_call"}, {"app": "TODOIST", "mode": "post_call"}])
    assert apps == {"GMAIL"}  # Calendar is connected but not attached; Todoist runs after the call only
    assert "TODOIST_CREATE_TASK" not in names
    apps, _ = await _tool_names(db, [{"app": "ZOOM", "mode": "in_call"}])  # selected but not connected
    assert apps == set()
    async with db() as session:
        session.add(AgentIntegration(tenant_id=TID, agent_id=AID, app_name="GOOGLECALENDAR", enabled=True,
                                     timing_mode="in_call", action_whitelist=["GOOGLECALENDAR_FIND_FREE_SLOTS"]))
        await session.commit()
    _, names = await _tool_names(db, [{"app": "GOOGLECALENDAR", "mode": "in_call"}])
    assert names == {"GOOGLECALENDAR_FIND_FREE_SLOTS"}  # the agent's action list still applies


async def test_router_refuses_actions_outside_the_calls_selection(db, monkeypatch):
    _meta(monkeypatch, {
        "single": {"tenant_id": str(TID), "contact": {"integration_selection": [{"app": "TODOIST", "mode": "in_call"}]}},
        "plain": {"tenant_id": str(TID), "contact": {}},
        "foreign": {"tenant_id": str(OTHER), "contact": {}},
    })
    router = router_module.DialtactToolRouter()
    ok = lambda tool, call, timing="in_call": router.authorized(str(TID), str(AID), tool, timing=timing, call_id=call)  # noqa: E731
    assert await ok("TODOIST_CREATE_TASK", "single")
    assert not await ok("GOOGLECALENDAR_CREATE_EVENT", "single")  # connected, agent-default, but not attached
    assert not await ok("TODOIST_CREATE_TASK", "single", "post_call")
    assert await ok("GOOGLECALENDAR_CREATE_EVENT", "plain")  # no selection: agent defaults unchanged
    assert not await ok("TODOIST_CREATE_TASK", "plain")
    assert not await ok("GOOGLECALENDAR_CREATE_EVENT", "foreign")  # ledger of another tenant exposes nothing
    execute = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(router.nango, "execute_in_call_tool", execute)
    result = await router.route_and_execute(str(TID), str(AID), "single", "GOOGLECALENDAR_FIND_FREE_SLOTS", {"date": "2026-11-02"})
    assert result["status"] == "error"
    execute.assert_not_awaited()


# ------------------------------------------------------------------ campaigns
async def test_campaign_calls_inherit_the_campaign_set_and_ignore_contact_columns(db, monkeypatch):
    injected = [{"app": "GMAIL", "mode": "in_call"}]
    _meta(monkeypatch, {"camp-call": {"tenant_id": str(TID), "contact": {
        "campaign_id": str(CAMP), "contact_id": "x", "integration_selection": injected}}})
    selection = await ci.selection_for_call("camp-call", tenant_id=str(TID))
    assert selection == [{"app": "TODOIST", "mode": "post_call"}, {"app": "GOOGLECALENDAR", "mode": "in_call"}]
    router = router_module.DialtactToolRouter()
    assert await router.authorized(str(TID), str(AID), "GOOGLECALENDAR_CREATE_EVENT", call_id="camp-call")
    assert not await router.authorized(str(TID), str(AID), "GMAIL_SEND_EMAIL", call_id="camp-call")
    assert await router.authorized(str(TID), str(AID), "TODOIST_CREATE_TASK", timing="post_call", call_id="camp-call")
    # A campaign id from another tenant resolves to nothing, not to its selection.
    assert await ci.campaign_selection(str(CAMP), str(OTHER)) is None


async def test_campaign_create_stores_validated_selection(db, monkeypatch):
    from server.routes import campaigns as campaign_routes

    body = campaign_routes.CampaignCreate.model_validate({
        "name": "Spring", "agentId": str(AID), "consentConfirmed": True,
        "integrations": [{"app": "TODOIST", "mode": "post_call"}],
    })
    assert body.integrations == [{"app": "TODOIST", "mode": "post_call"}]
    with pytest.raises(ci.SelectionError):
        await ci.validate_selection(str(TID), str(AID), [{"app": "CLICKUP", "mode": "post_call"}])


# ------------------------------------------------------------------ post-call
async def test_post_call_runs_only_selected_after_call_apps(db):
    rules: list = []
    plan = await ci.post_call_plan([{"app": "TODOIST", "mode": "post_call"}, {"app": "GMAIL", "mode": "in_call"}], rules)
    assert plan == ["TODOIST_CREATE_TASK"]
    assert await ci.post_call_plan([{"app": "GOOGLECALENDAR", "mode": "in_call"}], rules) == []
    off = [SimpleNamespace(app_name="TODOIST", enabled=False, timing_mode="post_call", action_whitelist=[])]
    assert await ci.post_call_plan([{"app": "TODOIST", "mode": "post_call"}], off) == []
    outcome = {"summary_en": "Wants a quote for 20 chairs.", "next_action": "Send the quote by Friday",
               "extracted_fields": {"name": "Asha Rao", "email": "asha@example.com"}}
    assert ci.post_call_arguments("TODOIST_CREATE_TASK", outcome, {}) == {
        "content": "Follow up with Asha Rao: Send the quote by Friday"}
    draft = ci.post_call_arguments("GMAIL_CREATE_DRAFT", outcome, {})
    assert draft["to"] == "asha@example.com" and "20 chairs" in draft["body"]
    assert ci.post_call_arguments("GMAIL_CREATE_DRAFT", {**outcome, "extracted_fields": {}}, {}) is None  # no guessed recipient
    assert ci.post_call_arguments("TODOIST_CREATE_TASK", {}, {}) is None


async def test_post_call_dispatch_uses_the_selection(db, monkeypatch):
    from server.call import post_call_pipeline as pcp

    _meta(monkeypatch, {"pc": {"tenant_id": str(TID), "contact": {
        "integration_selection": [{"app": "TODOIST", "mode": "post_call"}]}}})
    monkeypatch.setattr(pcp.call_store, "get", AsyncMock(return_value={"tenant_id": str(TID), "agent_id": str(AID)}))
    import server.db.connection as connection_module

    monkeypatch.setattr(connection_module, "get_session_factory", lambda: db)
    calls = []

    async def route(tenant_id, agent_id, call_id, action, arguments, *, timing):
        calls.append((action, arguments, timing))
        return {"status": "success"}

    monkeypatch.setattr(router_module.tool_router, "route_and_execute", route)
    outcome = {"summary_en": "Interested.", "next_action": "Call back Monday", "extracted_fields": {}}
    await pcp.reconcile_and_dispatch_post_call("pc", outcome)
    assert calls == [("TODOIST_CREATE_TASK", {"content": "Follow up with the caller: Call back Monday"}, "post_call")]


# ------------------------------------------------------------------ prompt + API
def test_prompt_rows_name_only_attached_apps():
    tools = [{"name": "GMAIL_SEND_EMAIL"}, {"name": "SAVE_ENQUIRY"}]
    rows = ci.capability_rows([{"app": "GMAIL", "mode": "in_call"}, {"app": "TODOIST", "mode": "post_call"}], tools)
    text = "\n".join(rows)
    assert "Gmail Follow-Up (during the call)" in text and "Todoist (after the call" in text
    assert "Do not offer bookings" in text and "Google Calendar" not in text
    none = "\n".join(ci.capability_rows([{"app": "TODOIST", "mode": "post_call"}], [{"name": "SAVE_ENQUIRY"}]))
    assert "No external app can be used during this call" in none
    assert ci.capability_rows(None, tools) == []
    from server.brain.capabilities import apply_available_tools

    brain = "--- CALL CAPABILITIES ---\nold\n\n--- PLATFORM CALL RULES ---\nx"
    assert "(during the call)" in apply_available_tools(brain, tools, call_integration_rows=rows)


async def test_call_options_api_marks_unavailable_apps(db, monkeypatch):
    async def principal(request, csrf, authorization):
        return SimpleNamespace(tenant_id=TID, subject=UUID(int=9), role="owner")

    monkeypatch.setattr(routes, "require_api_tenant", principal)
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://console.example.test") as client:
        res = await client.get(f"/api/integrations/call-options?agentId={AID}")
        assert res.status_code == 200
        items = {i["app"]: i for i in res.json()["items"]}
        foreign = await client.get(f"/api/integrations/call-options?agentId={FOREIGN}")
    assert foreign.status_code == 404
    assert {a for a, i in items.items() if i["selectable"]} == {"GOOGLECALENDAR", "GMAIL", "TODOIST", "CALENDLY"}
    assert items["SLACK"]["state"] == "setup_required" and not items["SLACK"]["selectable"]  # connected but unusable
    assert items["HUBSPOT"]["state"] == "not_connected" and items["SHOPIFY"]["state"] == "not_connected"
    assert [m["mode"] for m in items["TODOIST"]["modes"]] == ["in_call", "post_call"]
    assert items["TODOIST"]["defaultMode"] == "post_call"
    assert all(m["description"] for i in items.values() for m in i["modes"])


async def test_shopify_email_lookup_never_returns_another_customers_order(monkeypatch):
    from server.services.nango_service import NangoService

    service = NangoService()
    monkeypatch.setattr(NangoService, "secret_key", property(lambda self: "test"))
    response = httpx.Response(200, json={"orders": [{"id": 1, "name": "#1001", "email": "other@example.com"}]},
                              request=httpx.Request("GET", "https://x"))
    monkeypatch.setattr(httpx.AsyncClient, "get", AsyncMock(return_value=response))
    result = await service._execute_proxy_tool(provider_key="shopify-api-key", connection_id="c",
                                               action_name="SHOPIFY_GET_ORDER", params={"email": "asha@example.com"})
    assert result["status"] == "error"


async def test_single_call_api_validates_and_carries_the_selection(db, monkeypatch):
    from fastapi import HTTPException

    from server.routes import app_telephony as tel

    monkeypatch.setattr(tel, "require_subscriber_permission", lambda *_: None)
    monkeypatch.setattr(tel, "get_settings", lambda: SimpleNamespace(saas_telephony_enabled=True))
    monkeypatch.setattr(tel, "subscriber_workspace_tenant_id", lambda principal: TID)
    dial = AsyncMock(return_value={"ok": True})  # never reaches a carrier
    monkeypatch.setattr(tel, "subscriber_outbound", dial)
    principal = SimpleNamespace(tenant_id=TID, user_id=UUID(int=7))
    body = tel.OutboundCallBody(agentId=str(AID), toE164="+15550100000",
                                integrations=[{"app": "GOOGLECALENDAR", "mode": "in_call"}])
    await tel.telephony_outbound(body, principal)
    assert dial.await_args.kwargs["contact"] == {"integration_selection": [{"app": "GOOGLECALENDAR", "mode": "in_call"}]}
    for bad, status in (([{"app": "HUBSPOT", "mode": "in_call"}], 409), ([{"app": "SLACK", "mode": "post_call"}], 422)):
        with pytest.raises(HTTPException) as err:
            await tel.telephony_outbound(tel.OutboundCallBody(agentId=str(AID), toE164="+15550100000", integrations=bad), principal)
        assert err.value.status_code == status
    with pytest.raises(HTTPException) as err:  # another tenant's agent
        await tel.telephony_outbound(tel.OutboundCallBody(agentId=str(FOREIGN), toE164="+15550100000",
                                                          integrations=[{"app": "GMAIL", "mode": "in_call"}]), principal)
    assert err.value.status_code == 404
    await tel.telephony_outbound(tel.OutboundCallBody(agentId=str(AID), toE164="+15550100000"), principal)
    assert dial.await_args.kwargs["contact"] is None  # nothing chosen: agent defaults
    assert dial.await_count == 2
