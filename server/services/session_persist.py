"""Disk persistence for per-session Test Studio overrides (instructions + runtime)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from server.config.env import get_settings


class SessionPersist:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, Any] = {"instructions": {}, "runtime": {}, "ui": {}}
        self._load()

    def _path(self) -> Path:
        return get_settings().data_path / "session_overrides.json"

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._cache = {
                    "instructions": raw.get("instructions") if isinstance(raw.get("instructions"), dict) else {},
                    "runtime": raw.get("runtime") if isinstance(raw.get("runtime"), dict) else {},
                    "ui": raw.get("ui") if isinstance(raw.get("ui"), dict) else {},
                }
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_instructions(self, session_id: str) -> dict | None:
        with self._lock:
            entry = self._cache["instructions"].get(session_id)
            return dict(entry) if isinstance(entry, dict) else None

    def set_instructions(self, session_id: str, entry: dict) -> None:
        with self._lock:
            self._cache["instructions"][session_id] = dict(entry)
            self._save()

    def delete_instructions(self, session_id: str) -> None:
        with self._lock:
            self._cache["instructions"].pop(session_id, None)
            self._save()

    def get_runtime(self, session_id: str) -> dict | None:
        with self._lock:
            entry = self._cache["runtime"].get(session_id)
            return dict(entry) if isinstance(entry, dict) else None

    def set_runtime(self, session_id: str, entry: dict) -> None:
        with self._lock:
            self._cache["runtime"][session_id] = dict(entry)
            self._save()

    def all_instructions(self) -> dict[str, dict]:
        with self._lock:
            return {
                k: dict(v)
                for k, v in self._cache.get("instructions", {}).items()
                if isinstance(v, dict)
            }

    def all_runtime(self) -> dict[str, dict]:
        with self._lock:
            return {
                k: dict(v)
                for k, v in self._cache.get("runtime", {}).items()
                if isinstance(v, dict)
            }


    def delete_runtime(self, session_id: str) -> None:
        with self._lock:
            self._cache["runtime"].pop(session_id, None)
            self._save()

    def get_ui(self, session_id: str) -> dict:
        with self._lock:
            entry = self._cache.get("ui", {}).get(session_id)
            return dict(entry) if isinstance(entry, dict) else {}

    def set_ui(self, session_id: str, entry: dict) -> None:
        with self._lock:
            if "ui" not in self._cache:
                self._cache["ui"] = {}
            self._cache["ui"][session_id] = dict(entry)
            self._save()

    def delete_ui(self, session_id: str) -> None:
        with self._lock:
            self._cache.get("ui", {}).pop(session_id, None)
            self._save()


session_persist = SessionPersist()
