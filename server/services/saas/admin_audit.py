"""Audit log helper for dev admin mutations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from server.db.connection import get_session_factory
from server.db.models.phase5_models import AuditLog


async def record_admin_action(
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    tenant_id: uuid.UUID | None = None,
    payload: dict | None = None,
) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=payload or {},
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
