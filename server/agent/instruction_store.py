"""
Instruction store — server/agent/instruction_store.py
Per-session dual-channel prompting persistence (MVP: in-memory with TTL):
  • behaviour — HOW the agent should respond (tone/style/personality)
  • business  — client's business knowledge (products, policies, domain facts)
Thread-safe, 24h TTL, sanitized on save.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from server.agent.instruction_builder import sanitize_behaviour, sanitize_business

_TTL_SECONDS = 60 * 60 * 24  # 24h


class InstructionStore:
    def __init__(self):
        self._store: Dict[str, dict] = {}
        self._lock = threading.RLock()

    def _entry(self, session_id: str) -> Optional[dict]:
        entry = self._store.get(session_id)
        if entry and time.time() - entry["updatedAt"] > _TTL_SECONDS:
            self._store.pop(session_id, None)
            return None
        return entry

    def save(
        self,
        session_id: str,
        behaviour: str = "",
        business: str = "",
        style: str | None = None,
    ) -> dict:
        b = sanitize_behaviour(behaviour or "")
        z = sanitize_business(business or "")
        with self._lock:
            prev = self._store.get(session_id, {})
            self._store[session_id] = {
                "text": b,          # back-compat alias of behaviour
                "behaviour": b,
                "business": z,
                "style": (style or prev.get("style") or "concise, conversational")[:100],
                "updatedAt": time.time(),
            }
            e = self._store[session_id]
            return {"text": b, "behaviour": b, "business": z, "style": e["style"], "updatedAt": e["updatedAt"]}

    def get_behaviour(self, session_id: str) -> str:
        with self._lock:
            e = self._entry(session_id)
            return e["behaviour"] if e else ""

    def get_business(self, session_id: str) -> str:
        with self._lock:
            e = self._entry(session_id)
            return e["business"] if e else ""

    def get_style(self, session_id: str) -> str | None:
        with self._lock:
            e = self._entry(session_id)
            return e.get("style") if e else None

    # Back-compat: old callers asked for single "text"
    def get(self, session_id: str) -> str:
        return self.get_behaviour(session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)

    def get_with_meta(self, session_id: str) -> dict:
        with self._lock:
            e = self._entry(session_id)
            if not e:
                return {"text": "", "behaviour": "", "business": "", "updatedAt": None, "present": False, "style": None}
            return {
                "text": e["behaviour"],
                "behaviour": e["behaviour"],
                "business": e["business"],
                "updatedAt": e["updatedAt"],
                "present": bool(e["behaviour"] or e["business"]),
                "style": e.get("style"),
            }

    def stats(self) -> dict:
        with self._lock:
            return {"sessions": len(self._store)}


instruction_store = InstructionStore()
