"""Activity log API for the admin panel.

One place that answers "what happened, and did any of it fail" across admins,
subscribers, webhooks and background jobs.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.services.saas.activity_log import (
    OUTCOMES,
    SEVERITIES,
    SOURCES,
    list_events,
    record_event,
)

router = APIRouter()


@router.get("/api/dev/admin/activity-log")
async def get_activity_log(
    source: str | None = Query(None),
    outcome: str | None = Query(None),
    severity: str | None = Query(None),
    action: str | None = Query(None, max_length=100),
    actor: str | None = Query(None, max_length=255),
    resourceType: str | None = Query(None, alias="resourceType", max_length=50),
    tenantId: str | None = Query(None, alias="tenantId", max_length=36),
    since: str | None = Query(None),
    until: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: SessionData = Depends(require_dev_session),
) -> dict[str, Any]:
    """Filtered activity rows, a total for pagination, and filter facets.

    Read-only and permissioned like the other billing-scoped admin views, so an
    administrator can read the log without holding promotion rights.
    """
    require_permission(session, "dev.admin.billing")
    return await list_events(
        source=source,
        outcome=outcome,
        severity=severity,
        action=action,
        actor=actor,
        resource_type=resourceType,
        tenant_id=tenantId,
        since=since,
        until=until,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/api/dev/admin/activity-log/summary")
async def get_activity_summary(
    since: str | None = Query(None, description="ISO timestamp; defaults to 24h ago"),
    session: SessionData = Depends(require_dev_session),
) -> dict[str, Any]:
    """Counts by outcome/severity/source for the header, plus the newest failures.

    The failure list is the point: an operator opening this page wants the
    problems first, not a wall of successful rows to scan.
    """
    require_permission(session, "dev.admin.billing")
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from server.db.connection import get_session_factory
    from server.db.models.phase5_models import AuditLog

    factory = get_session_factory()
    if factory is None:
        return {"counts": {}, "recentFailures": [], "total": 0}

    start = since or (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        since_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    except ValueError:
        since_dt = datetime.now(timezone.utc) - timedelta(hours=24)
    if since_dt.tzinfo is None:
        since_dt = since_dt.replace(tzinfo=timezone.utc)

    async with factory() as session:
        scoped = [AuditLog.created_at >= since_dt]
        total = (await session.execute(select(func.count()).select_from(AuditLog).where(*scoped))).scalar_one()
        by_outcome = dict(
            (
                await session.execute(
                    select(AuditLog.outcome, func.count()).where(*scoped).group_by(AuditLog.outcome)
                )
            ).all()
        )
        by_severity = dict(
            (
                await session.execute(
                    select(AuditLog.severity, func.count()).where(*scoped).group_by(AuditLog.severity)
                )
            ).all()
        )
        by_source = dict(
            (
                await session.execute(
                    select(AuditLog.source, func.count()).where(*scoped).group_by(AuditLog.source)
                )
            ).all()
        )
        failures = (
            await session.execute(
                select(AuditLog)
                .where(*scoped, AuditLog.outcome != "ok")
                .order_by(AuditLog.created_at.desc())
                .limit(20)
            )
        ).scalars().all()

    return {
        "since": since_dt.isoformat(),
        "total": int(total),
        "counts": {
            "outcome": by_outcome,
            "severity": by_severity,
            "source": by_source,
        },
        "vocabularies": {"sources": list(SOURCES), "outcomes": list(OUTCOMES), "severities": list(SEVERITIES)},
        "recentFailures": [
            {
                "id": str(f.id),
                "action": f.action,
                "actor": f.actor,
                "source": f.source,
                "severity": f.severity,
                "resourceType": f.resource_type,
                "resourceId": f.resource_id,
                "error": (f.payload or {}).get("error"),
                "createdAt": f.created_at.isoformat() if f.created_at else None,
            }
            for f in failures
        ],
    }


class NoteBody(BaseModel):
    """A free-text operator note, for anything worth writing down in the log."""

    text: str = Field(..., min_length=1, max_length=2000)
    resourceType: str = Field("note", max_length=50)
    resourceId: str = Field("", max_length=255)


@router.post("/api/dev/admin/activity-log")
async def post_activity_note(
    body: NoteBody, session: SessionData = Depends(require_dev_session)
) -> dict[str, Any]:
    """Write a note into the log itself.

    Not a substitute for the structured rows above, but an operator investigating
    something needs somewhere to record what they concluded — otherwise the next
    person repeats the work.
    """
    require_permission(session, "dev.admin.billing")
    await record_event(
        action="admin.note",
        resource_type=body.resourceType,
        resource_id=body.resourceId,
        actor=session.subject,
        payload={"text": body.text},
        source="admin",
    )
    return {"ok": True}