"""Dev portal audit log — promotions, platform brain, config versions."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.db.connection import get_session_factory
from server.db.models.entities import ConfigVersion
from server.db.models.phase5_models import AuditLog

router = APIRouter()


@router.get("/api/dev/audit-log")
async def dev_audit_log(
    limit: int = Query(50, ge=1, le=200),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.promote")
    entries: list[dict[str, Any]] = []
    factory = get_session_factory()
    if factory is None:
        return {"entries": entries, "source": "memory"}

    async with factory() as db:
        cv = await db.execute(select(ConfigVersion).order_by(desc(ConfigVersion.created_at)).limit(limit))
        for row in cv.scalars():
            entries.append(
                {
                    "id": str(row.id),
                    "actor": (row.payload or {}).get("actor", "system"),
                    "action": row.resource_type,
                    "resource_type": row.resource_type,
                    "resource_id": row.resource_id,
                    "payload": row.payload,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        try:
            al = await db.execute(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit))
            for row in al.scalars():
                entries.append(
                    {
                        "id": str(row.id),
                        "actor": row.actor,
                        "action": row.action,
                        "resource_type": row.resource_type,
                        "resource_id": row.resource_id,
                        "payload": row.payload,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                )
        except Exception:
            pass

    entries.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    return {"entries": entries[:limit]}
