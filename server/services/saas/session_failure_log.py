"""Ring buffer of web/phone session failures — inspect via admin API only."""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

_LOCK = threading.Lock()
_ENTRIES: deque[dict[str, Any]] = deque(maxlen=200)


def record_session_failure(
    *,
    channel: str,
    code: str,
    message: str,
    agent_id: str | None = None,
    tenant_id: str | None = None,
    call_id: str | None = None,
    detail: str | None = None,
) -> None:
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
        "code": code,
        "message": (message or "")[:500],
        "agentId": agent_id,
        "tenantId": tenant_id,
        "callId": call_id,
        "detail": (detail or "")[:2000] if detail else None,
    }
    with _LOCK:
        _ENTRIES.appendleft(entry)


def list_session_failures(limit: int = 50) -> list[dict[str, Any]]:
    n = max(1, min(int(limit or 50), 200))
    with _LOCK:
        return list(_ENTRIES)[:n]
