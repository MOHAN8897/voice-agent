"""Stage fallback chains for dev portal — persisted under data/dev_fallback.json."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from server.config.env import get_settings

_DEFAULT_CHAINS: dict[str, list[str]] = {
    "stt": ["sarvam"],
    "llm": ["openai", "gemini", "deepseek"],
    "tts": ["sarvam", "cartesia"],
}


class DevFallbackStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._chains: dict[str, list[str]] = dict(_DEFAULT_CHAINS)
        self._load()

    def _path(self) -> Path:
        return get_settings().data_path / "dev_fallback.json"

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            self._chains = dict(_DEFAULT_CHAINS)
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            chains = raw.get("chains") or raw
            if isinstance(chains, dict):
                self._chains = {
                    stage: list(v) for stage, v in chains.items() if isinstance(v, list)
                }
        except Exception:
            self._chains = dict(_DEFAULT_CHAINS)

    def get_chains(self) -> dict[str, list[str]]:
        with self._lock:
            return {k: list(v) for k, v in self._chains.items()}

    def update_chains(self, patch: dict[str, list[str]]) -> dict[str, list[str]]:
        with self._lock:
            for stage, providers in patch.items():
                if stage in ("stt", "llm", "tts") and isinstance(providers, list):
                    self._chains[stage] = [str(p) for p in providers]
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"chains": self._chains}, indent=2), encoding="utf-8")
            return self.get_chains()


dev_fallback_store = DevFallbackStore()
