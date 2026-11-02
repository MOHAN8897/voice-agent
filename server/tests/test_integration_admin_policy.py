"""Platform-admin integration switches, per-workspace overrides and their enforcement.

An app the admin turns off must disappear from the workspace catalog, refuse
connect and setup, drop out of the model's tools and be refused by the router,
even while the connection itself stays valid. Overrides win in both directions,
the policy fails closed, and only admins with the integrations permission can
change it.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from server.auth import rbac
from server.auth.dependencies import require_dev_session
from server.auth.session import SessionData
from server.db.models.integration_models import (AgentIntegration, PlatformIntegrationSetting, TenantIntegrationOverride,
                                                 ToolExecution)
from server.routes import dev_admin_integrations as admin_routes
from server.routes import integrations as routes
from server.services import integration_policy, tenant_tool_cache
from server.services import tool_router as router_module
from server.services.tool_schema_registry import get_tools_for_agent
from server.tests.test_call_integration_selection import AID, OTHER, TID, db  # noqa: F401 - fixtures
from server.tests.test_integration_security_hardening import sqlite_json  # noqa: F401 - JSONB on sqlite


@pytest.fixture
async def pdb(db):
    engine = db.kw["bind"]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: PlatformIntegrationSetting.__table__.create(sync))
        await connection.run_sync(lambda sync: TenantIntegrationOverride.__table__.create(sync))
    integration_policy.invalidate()
    yield db
    integration_policy.invalidate()


def _admin_app(role: str, monkeypatch) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_routes.router)
    app.dependency_overrides[require_dev_session] = lambda: SessionData(kind="dev", subject="fixture-admin", tenant_id=None,
                                                                         role=role, issued_at=0)
    monkeypatch.setattr(admin_routes, "record_admin_action", AsyncMock())
    import server.db.connection as connection_module

    monkeypatch.setattr(admin_routes, "get_session_factory", connection_module.get_session_factory)
    return app


@pytest.fixture
async def admin(pdb, monkeypatch):
    app = _admin_app(rbac.ROLE_SUPER_ADMIN, monkeypatch)
    from server.services.nango_service import nango_service

    monkeypatch.setattr(nango_service, "get_configured_providers", AsyncMock(return_value={"google-calendar"}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://admin.test") as client:
        yield client


@pytest.fixture
async def tenant_api(pdb, monkeypatch):
    async def principal(request, csrf, authorization):
        return SimpleNamespace(tenant_id=TID, subject=UUID(int=9), role="owner")

    monkeypatch.setattr(routes, "require_api_tenant", principal)
    monkeypatch.setattr(routes, "require_role_permission", lambda role, perm: None)
    monkeypatch.setattr(routes.nango_service, "get_configured_providers", AsyncMock(return_value=set()))
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://console.test") as client:
        yield client


async def _names(db):
    tenant_tool_cache.invalidate(str(TID))
    active = await tenant_tool_cache.get_active_app_names(str(TID), db)
    return {t["name"] for t in await get_tools_for_agent(active, str(TID), str(AID), db)}


async def test_platform_switch_removes_app_everywhere_and_override_restores_it(admin, tenant_api, pdb):
    assert "GOOGLECALENDAR_CREATE_EVENT" in await _names(pdb)
    assert (await admin.put("/api/dev/admin/integrations/GOOGLECALENDAR", json={"enabled": False, "note": "vendor outage"})).status_code == 200

    # Gone from the model's tools, refused by the router even though connected.
    assert not any(n.startswith("GOOGLECALENDAR_") for n in await _names(pdb))
    router = router_module.DialtactToolRouter()
    assert not await router.authorized(str(TID), str(AID), "GOOGLECALENDAR_FIND_FREE_SLOTS")
    # Workspace sees it as switched off and cannot reconnect or set it up.
    catalog = {i["id"]: i for i in (await tenant_api.get("/api/integrations/catalog")).json()["items"]}
    assert catalog["GOOGLECALENDAR"]["admin_disabled"] is True
    assert (await tenant_api.post("/api/integrations/GOOGLECALENDAR/connect",
                                  json={"base_redirect_uri": "http://localhost/cb"})).status_code == 403
    assert (await tenant_api.put("/api/integrations/GOOGLECALENDAR/settings", json={"settings": {}})).status_code == 403
    options = {i["app"]: i for i in (await tenant_api.get(f"/api/integrations/call-options?agentId={AID}")).json()["items"]}
    assert options["GOOGLECALENDAR"]["state"] == "disabled_by_admin" and not options["GOOGLECALENDAR"]["selectable"]

    # A per-workspace override wins over the platform switch.
    assert (await admin.put(f"/api/dev/admin/tenants/{TID}/integrations/GOOGLECALENDAR", json={"enabled": True})).status_code == 200
    assert "GOOGLECALENDAR_CREATE_EVENT" in await _names(pdb)
    assert await router.authorized(str(TID), str(AID), "GOOGLECALENDAR_FIND_FREE_SLOTS")
    # Removing the override falls back to the platform switch (off).
    assert (await admin.put(f"/api/dev/admin/tenants/{TID}/integrations/GOOGLECALENDAR", json={"enabled": None})).status_code == 200
    assert not any(n.startswith("GOOGLECALENDAR_") for n in await _names(pdb))


async def test_workspace_override_can_withhold_one_app_from_one_workspace(admin, tenant_api, pdb):
    assert (await admin.put(f"/api/dev/admin/tenants/{TID}/integrations/CALENDLY", json={"enabled": False})).status_code == 200
    catalog = {i["id"] for i in (await tenant_api.get("/api/integrations/catalog")).json()["items"]}
    assert "ZOOM" in catalog  # untouched apps still offered
    assert await integration_policy.disabled_apps(str(OTHER), pdb) == set()  # another workspace unaffected
    # Off and not connected: not offered at all.
    assert (await admin.put("/api/dev/admin/integrations/ZOOM", json={"enabled": False})).status_code == 200
    assert "ZOOM" not in {i["id"] for i in (await tenant_api.get("/api/integrations/catalog")).json()["items"]}


async def test_status_and_usage_per_workspace(admin, pdb):
    async with pdb() as session:
        session.add_all([
            ToolExecution(tenant_id=TID, agent_id=AID, call_id="c1", action="GOOGLECALENDAR_CREATE_EVENT",
                          idempotency_key="k1", status="succeeded"),
            ToolExecution(tenant_id=TID, agent_id=AID, call_id="c2", action="TODOIST_CREATE_TASK",
                          idempotency_key="k2", status="failed"),
            AgentIntegration(tenant_id=TID, agent_id=AID, app_name="TODOIST", enabled=True, timing_mode="post_call"),
        ])
        await session.commit()
    overview = (await admin.get("/api/dev/admin/integrations")).json()
    apps = {a["app"]: a for a in overview["apps"]}
    assert apps["GOOGLECALENDAR"]["gatewayReady"] is True and apps["SLACK"]["gatewayReady"] is False
    assert apps["GOOGLECALENDAR"]["usage"]["succeeded"] == 1 and apps["TODOIST"]["usage"]["failed"] == 1
    assert apps["GOOGLECALENDAR"]["workspaces"]["connected"] == 1
    assert overview["workspaces"][0]["tenantId"] == str(TID) and overview["workspaces"][0]["usage"]["total"] == 2
    detail = (await admin.get(f"/api/dev/admin/tenants/{TID}/integrations")).json()
    items = {i["app"]: i for i in detail["items"]}
    assert items["TODOIST"]["connection"] == "connected" and items["TODOIST"]["agentRules"][0]["timing"] == "post_call"
    assert items["HUBSPOT"]["connection"] == "unverified" and items["ZOOM"]["connection"] == "not_connected"
    assert items["SLACK"]["setupMissing"] == ["Channel"]
    assert "connection_id" not in str(detail) and "c-GOOGLECALENDAR" not in str(detail)  # no gateway identifiers leak


async def test_only_integration_admins_can_change_switches(pdb, monkeypatch):
    app = _admin_app(rbac.ROLE_SUPPORT_AGENT, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://admin.test") as client:
        assert (await client.get(f"/api/dev/admin/tenants/{TID}/integrations")).status_code == 200  # may look
        assert (await client.put("/api/dev/admin/integrations/SLACK", json={"enabled": False})).status_code == 403
        assert (await client.put(f"/api/dev/admin/tenants/{TID}/integrations/SLACK", json={"enabled": False})).status_code == 403
    admin = _admin_app(rbac.ROLE_SUPER_ADMIN, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=admin), base_url="https://admin.test") as client:
        assert (await client.put("/api/dev/admin/integrations/NOT_AN_APP", json={"enabled": False})).status_code == 404
        assert (await client.put("/api/dev/admin/tenants/not-a-uuid/integrations/SLACK", json={"enabled": False})).status_code == 404


async def test_policy_fails_closed(monkeypatch):
    integration_policy.invalidate()

    def broken():
        raise RuntimeError("db down")

    monkeypatch.setattr(integration_policy, "_factory", lambda factory: broken())
    off = await integration_policy.disabled_apps(str(TID))
    assert off == set(integration_policy.catalog_apps())
    integration_policy.invalidate()
