"""Small boundaries shared by integration proxy adapters."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

_SECRET_KEY = re.compile(r"(?:token|secret|password|credential|authorization|api[_-]?key)", re.I)


#: Results reach the model through bounded_tool_data, which keeps 10 list items.
SLOT_SAMPLE = 10


def spread(items: list[Any], limit: int = SLOT_SAMPLE) -> list[Any]:
    """At most ``limit`` items picked evenly from first to last.

    A day's slots cut to the first few hid every afternoon: a caller asking for
    3 PM was told it was taken while it was free.
    """
    if len(items) <= limit:
        return list(items)
    last = len(items) - 1
    return [items[round(i * last / (limit - 1))] for i in range(limit)]


def start_ranges(starts: list[Any]) -> list[str]:
    """Bookable start times as "HH:MM-HH:MM" runs at the slots' own step."""
    times = sorted(set(starts))
    if not times:
        return []
    gaps = [b - a for a, b in zip(times, times[1:])]
    step = min(gaps) if gaps else None
    runs = [[times[0], times[0]]]
    for moment in times[1:]:
        if step is not None and moment - runs[-1][1] == step:
            runs[-1][1] = moment
        else:
            runs.append([moment, moment])
    return [f"{a:%H:%M}" if a == b else f"{a:%H:%M}-{b:%H:%M}" for a, b in runs]


def path_segment(value: Any) -> str:
    text = str(value).strip()
    if not text or text in {".", ".."} or len(text) > 512:
        raise ValueError("Invalid resource identifier")
    return quote(text, safe="")


def bounded_tool_data(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(value, dict):
        return {str(k)[:128]: bounded_tool_data(v, depth + 1) for k, v in list(value.items())[:40] if not _SECRET_KEY.search(str(k))}
    if isinstance(value, list):
        return [bounded_tool_data(v, depth + 1) for v in value[:10]]
    if isinstance(value, str):
        return value[:2000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return None


def soql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
