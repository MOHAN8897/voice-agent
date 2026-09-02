"""Dev/test mapping of phone numbers to agents for inbound routing tests."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from server.config.env import get_settings


class PhoneAssignmentsStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._map: dict[str, str] = {}
        self._load()

    def _path(self) -> Path:
        return get_settings().data_path / "phone_assignments.json"

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            self._map = {}
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._map = raw if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, OSError):
            self._map = {}

    def assign(self, e164: str, agent_id: str) -> dict[str, str]:
        clean = e164.strip()
        with self._lock:
            self._map[clean] = agent_id.strip()
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._map, indent=2), encoding="utf-8")
            return dict(self._map)

    def unassign(self, e164: str) -> dict[str, str]:
        clean = e164.strip()
        with self._lock:
            self._map.pop(clean, None)
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._map, indent=2), encoding="utf-8")
            return dict(self._map)

    def get(self, e164: str) -> str | None:
        with self._lock:
            return self._map.get(e164.strip())

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._map)


phone_assignments_store = PhoneAssignmentsStore()
