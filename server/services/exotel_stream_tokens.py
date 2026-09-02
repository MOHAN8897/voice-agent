"""Short-lived tokens binding Exotel WSS sessions to agent/tier metadata."""
from __future__ import annotations

import threading
import time
from typing import Any

_TTL_SEC = 3600


class ExotelStreamTokens:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tokens: dict[str, dict[str, Any]] = {}

    def put(self, token: str, *, agent_id: str | None = None, tier: str | None = None) -> None:
        with self._lock:
            self._tokens[token] = {
                "agent_id": agent_id,
                "tier": tier,
                "created_at": time.time(),
            }

    def get(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._tokens.get(token)
            if not row:
                return None
            if time.time() - float(row.get("created_at", 0)) > _TTL_SEC:
                self._tokens.pop(token, None)
                return None
            return dict(row)

    def consume(self, token: str) -> dict[str, Any] | None:
        row = self.get(token)
        if row:
            with self._lock:
                self._tokens.pop(token, None)
        return row


exotel_stream_tokens = ExotelStreamTokens()
