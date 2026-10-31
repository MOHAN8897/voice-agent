"""Small boundaries shared by integration proxy adapters."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

_SECRET_KEY = re.compile(r"(?:token|secret|password|credential|authorization|api[_-]?key)", re.I)


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
