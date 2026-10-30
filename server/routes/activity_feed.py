"""Console home: the tenant activity feed and the "now" rail.

Both endpoints are read-only and tenant-scoped through the subscriber JWT. They
aggregate rows other modules already write; see
``server/services/saas/activity_feed_service.py`` for the item vocabulary.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import OperationalError, ProgrammingError

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.services.saas import activity_feed_service as feed
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)

router = APIRouter()


@router.get("/api/activity/feed")
async def activity_feed(
    cursor: str | None = Query(None, max_length=120),
    limit: int = Query(feed.DEFAULT_LIMIT, ge=1, le=feed.MAX_LIMIT),
    filter: str = Query("all", pattern="^(all|needs_action|calls|leads|campaigns|system)$"),  # noqa: A002
    agentId: str | None = Query(None, max_length=64),
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),  # noqa: B008 -- FastAPI auth dependency.
):
    require_subscriber_permission(principal, "app.calls.read")
    try:
        return await feed.build_feed(subscriber_workspace_tenant_id(principal), cursor=cursor, limit=limit,
                                     filter_=filter, agent_id=agentId)
    except (ProgrammingError, OperationalError):
        # A table from a pending migration must not take the console home down.
        return {"items": [], "pinned": [], "nextCursor": None, "needsActionCount": 0, "filter": filter,
                "unavailable": True}


@router.get("/api/activity/live")
async def activity_live(
    since: datetime | None = Query(None, description="Start of the viewer's day, for today's counts"),
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),  # noqa: B008
):
    require_subscriber_permission(principal, "app.calls.read")
    try:
        return await feed.live_snapshot(subscriber_workspace_tenant_id(principal), since=since)
    except (ProgrammingError, OperationalError):
        return {"calls": [], "ringing": 0, "today": None, "unavailable": True}


@router.get("/api/activity/item")
async def activity_item(
    id: str = Query(..., min_length=3, max_length=160),  # noqa: A002 -- the feed item id.
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),  # noqa: B008
):
    """One feed item in full, for the console's detail panel. Read-only and tenant-scoped."""
    require_subscriber_permission(principal, "app.calls.read")
    try:
        detail = await feed.item_detail(subscriber_workspace_tenant_id(principal), id)
    except (ProgrammingError, OperationalError):
        detail = None
    if detail is None:
        raise HTTPException(status_code=404, detail={"error": {
            "code": "not_found", "message": "This activity is no longer available."}})
    return detail
