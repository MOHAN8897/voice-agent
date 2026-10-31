"""Record and query the platform activity log.

Two rules shape this module.

**Writing must never break the thing being logged.** Every failure here is
swallowed. A full disk or a schema mismatch should cost you a log line, never a
customer's number purchase or a paid wallet top-up.

**Reading must be filterable.** An operator debugging "did that purchase go
through?" should not have to page through an unfiltered stream to find the one
failure, so listing supports source/outcome/severity/action/actor/tenant filters,
a text search, real pagination with a total, and the distinct actions available
to filter on.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from server.db.connection import get_session_factory
from server.db.models.phase5_models import AuditLog

logger = logging.getLogger(__name__)

#: `outcome` values. Anything not `ok` should be investigated.
OUTCOMES = ("ok", "error")
#: `severity` values, least to most urgent. `error` is what an operator opens on.
SEVERITIES = ("info", "warning", "error")
#: `source` values: which part of the platform wrote the row.
SOURCES = ("admin", "subscriber", "webhook", "system")

#: Payloads are user- and config-shaped, so they can be large. Truncate rather than
#: let one verbose row bloat the table and slow every log query.
_MAX_PAYLOAD_CHARS = 8000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clip_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict) or not payload:
        return {}
    clipped: dict[str, Any] = {}
    for key, value in payload.items():
        try:
            text = repr(value)
        except Exception:
            text = "<unrepresentable>"
        if len(text) > 2000:
            text = text[:2000] + "…(truncated)"
        clipped[str(key)[:100]] = value if len(text) <= 2000 else text
    try:
        dumped = len(str(clipped))
    except Exception:
        return {}
    if dumped <= _MAX_PAYLOAD_CHARS:
        return clipped
    return {"_truncated": True, "_note": "payload exceeded the log size limit"}


async def record_event(
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    actor: str = "system",
    tenant_id: uuid.UUID | None = None,
    payload: dict | None = None,
    source: str = "admin",
    outcome: str = "ok",
    severity: str | None = None,
    request: Any = None,
) -> None:
    """Append one activity row. Never raises.

    `request` is an optional Starlette/FastAPI Request, from which the IP, user
    agent and request id are read so one user action can be traced across every
    row written while handling it.
    """
    factory = get_session_factory()
    if factory is None:
        return
    severity = severity or ("error" if outcome != "ok" else "info")

    # Prefer an explicitly passed request; otherwise fall back to the one the
    # middleware has in flight, so every row gets its caller's context without
    # each call site having to thread a Request through.
    from server.services.saas.request_context import request_context

    if request is not None:
        try:
            headers = getattr(request, "headers", None)
            ip = getattr(getattr(request, "client", None), "host", None)
            user_agent = headers.get("user-agent") if headers is not None else None
            request_id = headers.get("x-request-id") if headers is not None else None
        except Exception:
            ip = user_agent = request_id = None
    else:
        ip, user_agent, request_id = (
            request_context()["ip"],
            request_context()["user_agent"],
            request_context()["request_id"],
        )
    try:
        async with factory() as session:
            session.add(
                AuditLog(
                    tenant_id=tenant_id,
                    actor=str(actor or "system")[:255],
                    action=str(action)[:100],
                    resource_type=str(resource_type)[:50],
                    resource_id=str(resource_id)[:255],
                    payload=_clip_payload(payload),
                    source=str(source)[:20] if source in SOURCES else "system",
                    outcome=str(outcome)[:20] if outcome in OUTCOMES else "ok",
                    severity=str(severity)[:20] if severity in SEVERITIES else "info",
                    request_id=str(request_id)[:64] if request_id else None,
                    ip=str(ip)[:64] if ip else None,
                    user_agent=str(user_agent)[:400] if user_agent else None,
                    created_at=_utcnow(),
                )
            )
            await session.commit()
    except Exception:
        # Losing a log line is acceptable; failing the purchase that produced it
        # is not.
        logger.warning(
            "[ACTIVITY] could not record %s (%s)", action, resource_type, exc_info=True
        )


def _parse_since(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def list_events(
    *,
    source: str | None = None,
    outcome: str | None = None,
    severity: str | None = None,
    action: str | None = None,
    action_prefix: str | None = None,
    actor: str | None = None,
    resource_type: str | None = None,
    tenant_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Filtered, paginated activity rows plus the distinct actions for the filter UI."""
    factory = get_session_factory()
    if factory is None:
        return {"entries": [], "total": 0, "facets": {"actions": [], "actors": []}}

    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))

    filters = []
    if source:
        filters.append(AuditLog.source == source)
    if outcome:
        filters.append(AuditLog.outcome == outcome)
    if severity:
        filters.append(AuditLog.severity == severity)
    if action:
        filters.append(AuditLog.action == action)
    if action_prefix:
        filters.append(AuditLog.action.like(f"{action_prefix}%"))
    if actor:
        filters.append(AuditLog.actor == actor)
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    if tenant_id:
        try:
            filters.append(AuditLog.tenant_id == uuid.UUID(str(tenant_id)))
        except (TypeError, ValueError):
            filters.append(AuditLog.tenant_id.is_(None))
    start = _parse_since(since)
    if start:
        filters.append(AuditLog.created_at >= start)
    stop = _parse_since(until)
    if stop:
        filters.append(AuditLog.created_at <= stop)
    if search and search.strip():
        # ILIKE across the human-readable columns. Payload is JSONB, so it is
        # searched as text rather than with a JSON operator that would miss
        # nested values.
        needle = f"%{search.strip()}%"
        filters.append(
            AuditLog.actor.ilike(needle)
            | AuditLog.action.ilike(needle)
            | AuditLog.resource_type.ilike(needle)
            | AuditLog.resource_id.ilike(needle)
            | AuditLog.payload.cast(sa_text_type()).ilike(needle)
        )

    async with factory() as session:
        total = (
            await session.execute(select(func.count()).select_from(AuditLog).where(*filters))
        ).scalar_one()
        rows = (
            await session.execute(
                select(AuditLog)
                .where(*filters)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        # Facets are computed without the search/date filters so the filter
        # dropdowns keep offering every action the system knows about.
        actions = (
            await session.execute(
                select(AuditLog.action, func.count())
                .group_by(AuditLog.action)
                .order_by(func.count().desc())
                .limit(200)
            )
        ).all()
        actors = (
            await session.execute(
                select(AuditLog.actor, func.count())
                .group_by(AuditLog.actor)
                .order_by(func.count().desc())
                .limit(50)
            )
        ).all()

    return {
        "entries": [
            {
                "id": str(r.id),
                "actor": r.actor,
                "action": r.action,
                "resourceType": r.resource_type,
                "resourceId": r.resource_id,
                "payload": r.payload or {},
                "source": r.source,
                "outcome": r.outcome,
                "severity": r.severity,
                "requestId": r.request_id,
                "ip": r.ip,
                "userAgent": r.user_agent,
                "tenantId": str(r.tenant_id) if r.tenant_id else None,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "facets": {
            "actions": [{"value": a, "count": int(c)} for a, c in actions],
            "actors": [{"value": a, "count": int(c)} for a, c in actors],
        },
    }


def sa_text_type():
    """JSONB -> text for ILIKE, imported lazily so this module stays cheap."""
    from sqlalchemy import Text

    return Text()