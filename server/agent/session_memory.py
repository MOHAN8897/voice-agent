"""
Session memory — DEPRECATED. Replaced by call/memory_manager.py (object B).
Kept for ENABLE_SESSION_SUMMARY tests and sessions without call_id.
Canonical flag: ENABLE_WORKING_MEMORY.
"""
from __future__ import annotations

import threading
import time

Message = dict


class SessionMemoryStore:
    def __init__(self, ttl_seconds: int = 30 * 60):
        self._store: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._ttl_seconds = ttl_seconds

    def _purge_stale_unlocked(self, now: float) -> None:
        stale = [k for k, v in self._store.items() if now - v["updatedAt"] > self._ttl_seconds]
        for k in stale:
            del self._store[k]

    def _ensure_unlocked(self, session_id: str) -> dict:
        """Caller must hold self._lock."""
        now = time.time()
        self._purge_stale_unlocked(now)
        if session_id not in self._store:
            self._store[session_id] = {
                "summary": "",
                "turn_count": 0,
                "updatedAt": now,
            }
        return self._store[session_id]

    def _ensure(self, session_id: str) -> dict:
        with self._lock:
            return self._ensure_unlocked(session_id)

    def get_summary(self, session_id: str) -> str:
        with self._lock:
            entry = self._store.get(session_id)
            if not entry or time.time() - entry["updatedAt"] > self._ttl_seconds:
                return ""
            return entry.get("summary") or ""

    def record_turn(self, session_id: str) -> int:
        with self._lock:
            entry = self._ensure_unlocked(session_id)
            entry["turn_count"] = int(entry.get("turn_count", 0)) + 1
            entry["updatedAt"] = time.time()
            return entry["turn_count"]

    def set_summary(self, session_id: str, summary: str) -> None:
        with self._lock:
            entry = self._ensure_unlocked(session_id)
            entry["summary"] = (summary or "").strip()[:400]
            entry["updatedAt"] = time.time()

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)

    def stats(self) -> dict:
        with self._lock:
            return {"sessions": len(self._store)}


session_memory = SessionMemoryStore()
