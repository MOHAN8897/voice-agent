"""Call file-store paths — data/calls/{call_id}/."""
from __future__ import annotations

import re
from pathlib import Path

from server.config.env import get_settings

_CALL_ID_SAFE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")


def validate_call_id_format(call_id: str) -> str:
    """Validate call_id to prevent directory traversal attacks."""
    cid = (call_id or "").strip()
    if not cid or not _CALL_ID_SAFE.match(cid) or ".." in cid:
        raise ValueError(f"Invalid call_id: {call_id!r}")
    return cid


def calls_root() -> Path:
    root = get_settings().data_path / "calls"
    root.mkdir(parents=True, exist_ok=True)
    return root


def call_dir(call_id: str) -> Path:
    cid = validate_call_id_format(call_id)
    root = calls_root().resolve()
    target = (root / cid).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Path traversal detected: {call_id!r}")
    target.mkdir(parents=True, exist_ok=True)
    return target


def relative_storage_path(call_id: str) -> str:
    cid = validate_call_id_format(call_id)
    return f"data/calls/{cid}/"
