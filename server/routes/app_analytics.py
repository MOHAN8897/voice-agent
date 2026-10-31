"""Workspace analytics and data exports — tenant-scoped, read-only."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.services.saas import workspace_exports as exports
from server.services.saas.tenant_guard import (
    SubscriberPrincipal, require_subscriber_permission, subscriber_workspace_tenant_id,
)
from server.services.saas.workspace_analytics import workspace_analytics

router = APIRouter()
Principal = Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)]


@router.get("/api/app/analytics")
async def analytics(
    principal: Principal,
    range: Annotated[Literal["today", "7d", "30d", "custom"], Query()] = "7d",
    since: Annotated[str | None, Query(max_length=32)] = None,
    until: Annotated[str | None, Query(max_length=32)] = None,
    agentId: Annotated[str | None, Query(max_length=36)] = None,
):
    """Calls, leads, callbacks, follow-ups, DND, spend and tags for one period (IST days)."""
    require_subscriber_permission(principal, "app.calls.read")
    return await workspace_analytics(subscriber_workspace_tenant_id(principal), agent_id=agentId or None,
                                     range_key=range, since=since, until=until)


def _filters(range, since, until, agentId, status, outcome, direction, tags, tagMatch, stage, source, language, kind):
    return exports.Filters(range=range, since=since, until=until, agentId=agentId or None, status=status,
                           outcome=outcome, direction=direction, tags=tags, tagMatch=tagMatch, stage=stage,
                           source=source, language=language, kind=kind)


def _tenant(principal: SubscriberPrincipal, dataset: str):
    if dataset not in exports.DATASETS:
        raise HTTPException(404, "Unknown export")
    require_subscriber_permission(principal, exports.PERMISSIONS.get(dataset, "app.calls.read"))
    # Wallet history belongs to the billing tenant; call data to the workspace.
    return principal.tenant_id if dataset == "wallet" else subscriber_workspace_tenant_id(principal)


FilterQuery = Annotated[str | None, Query(max_length=500)]


@router.get("/api/app/exports/{dataset}/count")
async def export_count(
    dataset: str, principal: Principal,
    range: Annotated[Literal["today", "7d", "30d", "custom"] | None, Query()] = None,
    since: FilterQuery = None, until: FilterQuery = None, agentId: FilterQuery = None,
    status: FilterQuery = None, outcome: FilterQuery = None, direction: FilterQuery = None,
    tags: FilterQuery = None, tagMatch: Literal["any", "all"] = "any", stage: FilterQuery = None,
    source: FilterQuery = None, language: FilterQuery = None, kind: FilterQuery = None,
):
    """How many rows the export would hold, before downloading it."""
    tenant = _tenant(principal, dataset)
    data = await exports.collect(dataset, tenant, _filters(range, since, until, agentId, status, outcome, direction,
                                                           tags, tagMatch, stage, source, language, kind), details=False)
    return {"dataset": dataset, "count": data["total"], "limit": exports.MAX_ROWS, "capped": data["capped"]}


@router.get("/api/app/exports/{dataset}")
async def export_download(
    dataset: str, principal: Principal,
    format: Literal["csv", "xlsx"] = "csv",
    range: Annotated[Literal["today", "7d", "30d", "custom"] | None, Query()] = None,
    since: FilterQuery = None, until: FilterQuery = None, agentId: FilterQuery = None,
    status: FilterQuery = None, outcome: FilterQuery = None, direction: FilterQuery = None,
    tags: FilterQuery = None, tagMatch: Literal["any", "all"] = "any", stage: FilterQuery = None,
    source: FilterQuery = None, language: FilterQuery = None, kind: FilterQuery = None,
):
    """CSV (streamed) or Excel download of one dataset, at most ``MAX_ROWS`` rows."""
    tenant = _tenant(principal, dataset)
    data = await exports.collect(dataset, tenant, _filters(range, since, until, agentId, status, outcome, direction,
                                                           tags, tagMatch, stage, source, language, kind))
    name = exports.filename(dataset, format)
    headers = {"Content-Disposition": f'attachment; filename="{name}"', "X-Export-Rows": str(len(data["rows"])),
               "X-Export-Capped": "true" if data["capped"] else "false",
               "Access-Control-Expose-Headers": "Content-Disposition, X-Export-Rows, X-Export-Capped"}
    if format == "xlsx":
        import asyncio
        body = await asyncio.to_thread(exports.xlsx_bytes, data["columns"], data["rows"], dataset.replace("_", " ").title())
        return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)
    return StreamingResponse(exports.csv_chunks(data["columns"], data["rows"]), media_type="text/csv; charset=utf-8",
                             headers=headers)
