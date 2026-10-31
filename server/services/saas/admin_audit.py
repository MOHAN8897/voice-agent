"""Audit log helper for dev admin mutations.

Now a thin shim over `activity_log`, which is the single recorder. Two writers
would be two places for the new context columns to be forgotten, and a log that
sometimes has an outcome and sometimes does not is worse than no log.

Kept as its own module because 19 call sites already import this name.
"""
from __future__ import annotations

import uuid

from server.services.saas.activity_log import record_event

__all__ = ["record_admin_action"]


async def record_admin_action(
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    tenant_id: uuid.UUID | None = None,
    payload: dict | None = None,
    request: object | None = None,
) -> None:
    await record_event(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor=actor,
        tenant_id=tenant_id,
        payload=payload,
        source="admin",
        request=request,
    )