"""Call file-store paths — data/calls/{call_id}/."""
from __future__ import annotations

from pathlib import Path

from server.config.env import get_settings


def calls_root() -> Path:
    root = get_settings().data_path / "calls"
    root.mkdir(parents=True, exist_ok=True)
    return root


def call_dir(call_id: str) -> Path:
    path = calls_root() / call_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def relative_storage_path(call_id: str) -> str:
    return f"data/calls/{call_id}/"
