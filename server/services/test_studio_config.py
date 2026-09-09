"""Saved call configuration shared by browser and PSTN Test Studio sessions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from server.services.session_persist import session_persist


def saved_call_config(session_id: str | None) -> dict[str, Any]:
    if not session_id or not session_id.startswith("test-studio"):
        return {}
    value = session_persist.get_ui(session_id).get("callConfig")
    return deepcopy(value) if isinstance(value, dict) else {}


def merge_stack(saved: dict | None, explicit: dict | None) -> dict | None:
    result = deepcopy(saved or {})
    for key, value in (explicit or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_stack(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result or None
