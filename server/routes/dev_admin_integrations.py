"""Platform admin "Integrations": which apps workspaces may use, and how they are used.

* Platform switch per catalog app: off hides it from every workspace and stops
  agents using it, even where it is already connected.
* Per-workspace override: wins over the platform switch in both directions, so
  an app can be piloted for one workspace or withheld from one.
* Status and usage: each workspace's connections, setup and the integration
  actions its calls ran in the last 30 days.

No credential material is returned. Every change is written to the admin audit log.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.integration_models import (
    AgentIntegration,
    PlatformIntegrationSetting,
    TenantIntegration,
    TenantIntegrationOverride,
    ToolExecution,
)
from server.routes.integrations_catalog import CATALOG_INTEGRATIONS
from server.services import integration_policy
from server.services.saas.admin_audit import record_admin_action
from server.services.tool_schema_registry import _normalize, tool_definition

router = APIRouter(tags=["dev-admin-integrations"])

READ_PERMISSION = "dev.admin.tenants"
WRITE_PERMISSION = "dev.admin.integrations"
USAGE_DAYS = 30
SUCCESS = {"succeeded", "reconciled"}
UNKNOWN = {"initiated", "timed_out_pending"}


class SwitchBody(BaseModel):
    enabled: bool
    note: str | None = Field(None, max_length=500)


class OverrideBody(BaseModel):
    # None removes the override, so the workspace follows the platform switch again.
    enabled: bool | None
    note: str | None = Field(None, max_length=500)


def _factory():
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": {"code": "storage_unavailable", "message": "Storage unavailable."}})
    return factory


def _app(app_id: str) -> str:
    app = _normalize(app_id)
    if app not in integration_policy.catalog_apps():
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Integration not found."}})
    return app


def _tenant_uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Workspace not found."}}) from None


def _connection_state(row: TenantIntegration | None) -> str:
    if row is None or row.status in {"DISCONNECTED", "DISCONNECTING"}:
        return "not_connected"
    meta = row.metadata_ or {}
    if row.status == "ERROR" and meta.get("needs_reauth"):
        return "needs_reauth"
    if row.status == "ACTIVE" and meta.get("gateway_verified") is True:
        return "connected"
    return "unverified"


def _empty_usage() -> dict[str, Any]:
    return {"total": 0, "succeeded": 0, "failed": 0, "unknown": 0, "lastUsedAt": None}


def _add_usage(bucket: dict[str, Any], status: str, count: int, last: datetime | None) -> None:
    bucket["total"] += count
    key = "succeeded" if status in SUCCESS else "unknown" if status in UNKNOWN else "failed"
    bucket[key] += count
    if last and (bucket["lastUsedAt"] is None or last.isoformat() > bucket["lastUsedAt"]):
        bucket["lastUsedAt"] = last.isoformat()


async def _usage_rows(session: Any, tenant_id: uuid.UUID | None = None) -> list[tuple[uuid.UUID, str, str, int, datetime | None]]:
    since = datetime.now(timezone.utc) - timedelta(days=USAGE_DAYS)
    query = select(ToolExecution.tenant_id, ToolExecution.action, ToolExecution.status,
                   func.count(), func.max(ToolExecution.started_at)).where(ToolExecution.started_at >= since)
    if tenant_id is not None:
        query = query.where(ToolExecution.tenant_id == tenant_id)
    rows = (await session.execute(query.group_by(ToolExecution.tenant_id, ToolExecution.action, ToolExecution.status))).all()
    return [tuple(r) for r in rows]


def _action_app(action: str) -> str | None:
    definition = tool_definition(str(action or ""))
    return definition[0] if definition and definition[0] != "PLATFORM" else None


@router.get("/api/dev/admin/integrations")
async def list_platform_integrations(session: SessionData = Depends(require_dev_session)) -> dict[str, Any]:
    """Every catalog app with its platform switch, gateway readiness, adoption and usage."""
    require_permission(session, READ_PERMISSION)
    from server.services.nango_service import nango_service

    factory = _factory()
    try:
        configured = await nango_service.get_configured_providers()
    except Exception:  # noqa: BLE001 - readiness is informative only
        configured = set()
    async with factory() as db:
        switches = {_normalize(r.app_name): r for r in (await db.execute(select(PlatformIntegrationSetting))).scalars().all()}
        overrides = (await db.execute(select(TenantIntegrationOverride))).scalars().all()
        connections = (await db.execute(select(TenantIntegration))).scalars().all()
        usage = await _usage_rows(db)
        tenants = {t.tenant_id: t for t in (await db.execute(select(Tenant))).scalars().all()}
    per_app_usage: dict[str, dict[str, Any]] = defaultdict(_empty_usage)
    per_tenant_usage: dict[uuid.UUID, dict[str, Any]] = defaultdict(_empty_usage)
    for tenant_id, action, status, count, last in usage:
        app = _action_app(action)
        if app:
            _add_usage(per_app_usage[app], status, count, last)
            _add_usage(per_tenant_usage[tenant_id], status, count, last)
    states: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    tenant_apps: dict[uuid.UUID, set[str]] = defaultdict(set)
    for row in connections:
        state = _connection_state(row)
        states[_normalize(row.app_name)][state] += 1
        if state == "connected":
            tenant_apps[row.tenant_id].add(_normalize(row.app_name))
    apps = []
    for item in CATALOG_INTEGRATIONS:
        app = _normalize(item["id"])
        switch = switches.get(app)
        app_overrides = [o for o in overrides if _normalize(o.app_name) == app]
        apps.append({
            "app": app, "name": item["name"], "category": item.get("category"), "authType": item.get("auth_type"),
            "timing": item.get("timing"),
            "gatewayReady": nango_service.get_provider_key(app).lower() in configured,
            "enabled": switch.enabled if switch else True,
            "note": switch.note if switch else None,
            "updatedBy": switch.updated_by if switch else None,
            "updatedAt": switch.updated_at.isoformat() if switch and switch.updated_at else None,
            "overrides": {"on": sum(1 for o in app_overrides if o.enabled), "off": sum(1 for o in app_overrides if not o.enabled)},
            "workspaces": {"connected": states[app].get("connected", 0), "needsReauth": states[app].get("needs_reauth", 0)},
            "usage": per_app_usage[app],
        })
    workspaces = sorted(({
        "tenantId": str(tid), "name": tenants[tid].name if tid in tenants else str(tid),
        "status": tenants[tid].status if tid in tenants else None,
        "connectedApps": sorted(tenant_apps.get(tid, set())), "usage": per_tenant_usage[tid],
    } for tid in set(tenant_apps) | set(per_tenant_usage)), key=lambda w: (-w["usage"]["total"], w["name"].lower()))
    # A reachable gateway always lists its integrations; none at all means it is down.
    return {"apps": apps, "workspaces": workspaces, "usageDays": USAGE_DAYS, "gatewayReachable": bool(configured)}


@router.put("/api/dev/admin/integrations/{app_id}")
async def set_platform_switch(app_id: str, body: SwitchBody, request: Request,
                              session: SessionData = Depends(require_dev_session)) -> dict[str, Any]:
    require_permission(session, WRITE_PERMISSION)
    app = _app(app_id)
    async with _factory()() as db:
        row = await db.get(PlatformIntegrationSetting, app)
        before = row.enabled if row else True
        if row is None:
            row = PlatformIntegrationSetting(app_name=app)
            db.add(row)
        row.enabled, row.note, row.updated_by = body.enabled, (body.note or None), session.subject
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()
    integration_policy.invalidate()
    await record_admin_action(actor=session.subject, action="integration.platform_switch", resource_type="integration",
                              resource_id=app, payload={"before": before, "after": body.enabled, "note": body.note}, request=request)
    return {"app": app, "enabled": body.enabled}


@router.get("/api/dev/admin/tenants/{tenant_id}/integrations")
async def tenant_integrations(tenant_id: str, session: SessionData = Depends(require_dev_session)) -> dict[str, Any]:
    """One workspace: every app's effective availability, connection, setup, agents and usage."""
    require_permission(session, READ_PERMISSION)
    from server.services.integration_settings import missing_required

    tid = _tenant_uuid(tenant_id)
    async with _factory()() as db:
        tenant = await db.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Workspace not found."}})
        switches = {_normalize(r.app_name): r.enabled for r in (await db.execute(select(PlatformIntegrationSetting))).scalars().all()}
        overrides = {_normalize(r.app_name): r for r in (await db.execute(select(TenantIntegrationOverride).where(
            TenantIntegrationOverride.tenant_id == tid))).scalars().all()}
        rows = {_normalize(r.app_name): r for r in (await db.execute(select(TenantIntegration).where(
            TenantIntegration.tenant_id == tid))).scalars().all()}
        agents = {a.agent_id: a.name for a in (await db.execute(select(Agent).where(Agent.tenant_id == tid))).scalars().all()}
        rules = (await db.execute(select(AgentIntegration).where(AgentIntegration.tenant_id == tid))).scalars().all()
        usage = await _usage_rows(db, tid)
    per_app: dict[str, dict[str, Any]] = defaultdict(_empty_usage)
    for _, action, status, count, last in usage:
        app = _action_app(action)
        if app:
            _add_usage(per_app[app], status, count, last)
    items = []
    for item in CATALOG_INTEGRATIONS:
        app = _normalize(item["id"])
        platform_on = switches.get(app, True)
        override = overrides.get(app)
        row = rows.get(app)
        state = _connection_state(row)
        app_rules = [r for r in rules if _normalize(r.app_name) == app and r.agent_id in agents]
        items.append({
            "app": app, "name": item["name"], "category": item.get("category"),
            "platformEnabled": platform_on,
            "override": override.enabled if override else None,
            "overrideNote": override.note if override else None,
            "effective": override.enabled if override else platform_on,
            "connection": state,
            "account": row.account_identifier if row and state != "not_connected" else None,
            "connectedAt": row.created_at.isoformat() if row and state != "not_connected" and row.created_at else None,
            "setupMissing": missing_required(app, (row.metadata_ or {}).get("settings")) if row and state == "connected" else [],
            "agentRules": [{"agent": agents[r.agent_id], "enabled": r.enabled, "timing": r.timing_mode} for r in app_rules],
            "usage": per_app[app],
        })
    order = {"connected": 0, "needs_reauth": 1, "unverified": 2, "not_connected": 3}
    items.sort(key=lambda i: (order[i["connection"]], -i["usage"]["total"], i["name"]))
    return {"tenant": {"tenantId": str(tid), "name": tenant.name, "status": tenant.status}, "items": items, "usageDays": USAGE_DAYS}


@router.put("/api/dev/admin/tenants/{tenant_id}/integrations/{app_id}")
async def set_tenant_override(tenant_id: str, app_id: str, body: OverrideBody, request: Request,
                              session: SessionData = Depends(require_dev_session)) -> dict[str, Any]:
    require_permission(session, WRITE_PERMISSION)
    tid, app = _tenant_uuid(tenant_id), _app(app_id)
    async with _factory()() as db:
        if await db.get(Tenant, tid) is None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Workspace not found."}})
        row = (await db.execute(select(TenantIntegrationOverride).where(
            TenantIntegrationOverride.tenant_id == tid, TenantIntegrationOverride.app_name == app))).scalar_one_or_none()
        before = row.enabled if row else None
        if body.enabled is None:
            if row is not None:
                await db.delete(row)
        else:
            if row is None:
                row = TenantIntegrationOverride(tenant_id=tid, app_name=app, enabled=body.enabled)
                db.add(row)
            row.enabled, row.note, row.updated_by = body.enabled, (body.note or None), session.subject
            row.updated_at = datetime.now(timezone.utc)
        await db.commit()
    integration_policy.invalidate(str(tid))
    await record_admin_action(actor=session.subject, action="integration.workspace_override", resource_type="integration",
                              resource_id=app, tenant_id=tid, payload={"before": before, "after": body.enabled, "note": body.note},
                              request=request)
    return {"tenantId": str(tid), "app": app, "override": body.enabled}
