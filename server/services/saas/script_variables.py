"""Runtime script tags ({{key}}) for SaaS agent onboarding."""
from __future__ import annotations

import re
from typing import Any

_TAG_RE = re.compile(r"\{\{\s*([a-z][a-z0-9_]{1,48})\s*\}\}", re.IGNORECASE)

STANDARD_VARIABLES: list[dict[str, str]] = [
    {
        "key": "caller_name",
        "label": "Caller name",
        "description": "Name the caller gives on the call",
        "source": "caller",
        "example": "Priya",
    },
    {
        "key": "callback_phone",
        "label": "Callback number",
        "description": "Phone number to call or text back",
        "source": "caller",
        "example": "+91 98765 43210",
    },
    {
        "key": "business_name",
        "label": "Business name",
        "description": "Your company or clinic name from the brief",
        "source": "business",
        "example": "Suvidha Dental",
    },
]

SAAS_SCRIPT_VARIABLES_TITLE = "saas_script_variables"


def normalize_variable_key(raw: str) -> str:
    key = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    key = re.sub(r"[^a-z0-9_]", "", key)
    if not key:
        return "field_value"
    if key[0].isdigit():
        key = f"v_{key}"
    return key[:50]


def normalize_variables(rows: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = normalize_variable_key(str(row.get("key") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "key": key,
                "label": str(row.get("label") or key.replace("_", " ").title())[:80],
                "description": str(row.get("description") or "")[:300],
                "source": str(row.get("source") or "runtime")[:20],
                "example": str(row.get("example") or "")[:120],
            }
        )
    return out


def variables_from_text(greeting: str, script: str) -> list[dict[str, str]]:
    keys: list[str] = []
    for text in (greeting, script):
        for m in _TAG_RE.finditer(text or ""):
            k = normalize_variable_key(m.group(1))
            if k not in keys:
                keys.append(k)
    known = {v["key"]: v for v in STANDARD_VARIABLES}
    out: list[dict[str, str]] = []
    for k in keys:
        if k in known:
            out.append(dict(known[k]))
        else:
            out.append(
                {
                    "key": k,
                    "label": k.replace("_", " ").title(),
                    "description": f"Value for {{{{{k}}}}}",
                    "source": "runtime",
                    "example": "",
                }
            )
    if not out:
        return [dict(v) for v in STANDARD_VARIABLES[:2]]
    return out


def merge_variables(
    llm_vars: list[dict[str, Any]] | None,
    greeting: str,
    script: str,
) -> list[dict[str, str]]:
    from_text = variables_from_text(greeting, script)
    normalized = normalize_variables(llm_vars)
    by_key = {v["key"]: v for v in from_text}
    for v in normalized:
        by_key[v["key"]] = {**by_key.get(v["key"], {}), **v}
    return list(by_key.values())
