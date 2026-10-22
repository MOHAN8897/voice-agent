"""Validate Realtime end_call tool arguments before the hangup gate sees them."""
from __future__ import annotations

import json
from typing import Any

from server.realtime.models import END_CALL_REASONS

_ALLOWED_KEYS = frozenset({"should_end", "reason", "farewell"})


def parse_end_call_tool(raw: Any) -> dict[str, Any] | None:
    """Return a schema-valid end_call payload, or None if arguments are unusable."""
    payload = raw
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    extra = set(payload.keys()) - _ALLOWED_KEYS
    if extra:
        payload = {k: v for k, v in payload.items() if k in _ALLOWED_KEYS}
    if "should_end" not in payload:
        return None
    raw_should = payload.get("should_end")
    if isinstance(raw_should, bool):
        should_end = raw_should
    elif isinstance(raw_should, (int, float)) and raw_should in (0, 1):
        should_end = bool(raw_should)
    elif isinstance(raw_should, str):
        low = raw_should.strip().lower()
        if low in ("true", "1"):
            should_end = True
        elif low in ("false", "0", "no"):
            should_end = False
        else:
            return None
    else:
        return None
    reason = str(payload.get("reason") or "").strip()
    if should_end and reason not in END_CALL_REASONS:
        return None
    if not should_end and reason and reason not in END_CALL_REASONS and reason != "none":
        return None
    farewell = str(payload.get("farewell") or "")[:240]
    return {
        "should_end": should_end,
        "reason": reason if reason in END_CALL_REASONS else ("none" if not should_end else reason),
        "farewell": farewell,
    }
