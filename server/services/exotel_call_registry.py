"""In-memory Exotel call events for Test Studio (dev)."""
from __future__ import annotations

import threading
import time
from typing import Any

_MAX = 100


class ExotelCallRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._calls: dict[str, dict[str, Any]] = {}

    def upsert(self, call_sid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            row = dict(self._calls.get(call_sid) or {})
            row.update(patch)
            row["call_sid"] = call_sid
            row["updated_at"] = time.time()
            if "created_at" not in row:
                row["created_at"] = row["updated_at"]
            self._calls[call_sid] = row
            if len(self._calls) > _MAX:
                oldest = sorted(self._calls.items(), key=lambda kv: kv[1].get("updated_at", 0))[: len(self._calls) - _MAX]
                for sid, _ in oldest:
                    self._calls.pop(sid, None)
            return dict(row)

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._calls.values())
        rows.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
        return rows[:limit]

    def get(self, call_sid: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._calls.get(call_sid)
            return dict(row) if row else None


exotel_call_registry = ExotelCallRegistry()
