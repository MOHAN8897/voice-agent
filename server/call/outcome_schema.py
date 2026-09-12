"""Post-call outcome schema and disposition enum (locked)."""
from __future__ import annotations

from typing import Any

DISPOSITIONS = frozenset(
    {
        "new_lead",
        "interested",
        "qualified",
        "site_visit_planned",
        "callback_required",
        "not_interested",
        "wrong_number",
        "converted",
        "no_outcome",
    }
)

STATUS_TAGS = frozenset(
    {
        "action:required",
        "contact:name_known",
        "contact:phone_known",
        "followup:callback",
        "followup:site_visit",
        "quality:inconclusive",
        "signal:objection",
        *(f"outcome:{disposition}" for disposition in DISPOSITIONS),
    }
)

# OpenAI strict JSON schema forbids free-form objects (`additionalProperties: {type: string}`).
# Use an array of {key, value}, then normalize back to a dict for disk/API.
_EXTRACTED_FIELD_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["key", "value"],
    "properties": {
        "key": {"type": "string"},
        "value": {"type": "string"},
    },
}

OUTCOME_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "disposition",
        "disposition_confidence",
        "summary_te",
        "summary_en",
        "next_action",
        "extracted_fields",
        "objections",
        "notes",
    ],
    "properties": {
        "disposition": {"type": "string", "enum": sorted(DISPOSITIONS)},
        "disposition_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary_te": {"type": "string"},
        "summary_en": {"type": "string"},
        "next_action": {"type": ["string", "null"]},
        "extracted_fields": {"type": "array", "items": _EXTRACTED_FIELD_ITEM},
        "objections": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": ["string", "null"]},
    },
}


def validate_disposition(value: str | None) -> str:
    if value in DISPOSITIONS:
        return value  # type: ignore[return-value]
    return "no_outcome"


def normalize_extracted_fields(raw: Any) -> dict[str, str]:
    """LLM schema is [{key, value}, ...]; disk/API keep a string map."""
    if isinstance(raw, dict):
        return {str(k): "" if v is None else str(v) for k, v in raw.items()}
    if not isinstance(raw, list):
        return {}
    out: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key is None:
            continue
        value = item.get("value")
        out[str(key)] = "" if value is None else str(value)
    return out


def merge_outcome_facts(
    extracted_fields: Any,
    memory_snapshot: dict[str, Any] | None,
    *,
    caller_id: str | None = None,
) -> dict[str, str]:
    """Merge deterministic memory facts with LLM extraction for owner review."""
    merged: dict[str, str] = {}
    snapshot = memory_snapshot if isinstance(memory_snapshot, dict) else {}
    raw_facts = snapshot.get("facts")
    if isinstance(raw_facts, dict):
        for key, value in raw_facts.items():
            text = str(value or "").strip()
            if text:
                merged[str(key)] = text
    for key, value in normalize_extracted_fields(extracted_fields).items():
        text = str(value or "").strip()
        if text:
            merged[str(key)] = text
    if caller_id and not any(k in merged for k in ("phone", "callback_phone", "contact", "phone_number")):
        merged["phone"] = str(caller_id).strip()
    return dict(sorted(merged.items()))


def derive_status_tags(
    disposition: str | None,
    facts: dict[str, str] | None,
    *,
    next_action: str | None = None,
    objections: list[Any] | None = None,
) -> list[str]:
    """Return a stable, allow-listed set of owner-facing status tags."""
    normalized = validate_disposition(disposition)
    tags = {f"outcome:{normalized}"}
    normalized_facts = {str(k).lower(): str(v).strip() for k, v in (facts or {}).items() if str(v).strip()}
    if any(k in normalized_facts for k in ("name", "caller_name", "customer_name", "full_name")):
        tags.add("contact:name_known")
    if any(k in normalized_facts for k in ("phone", "callback_phone", "contact", "phone_number", "mobile")):
        tags.add("contact:phone_known")
    action = str(next_action or "").lower()
    if normalized == "callback_required" or "callback" in action or "call back" in action:
        tags.add("followup:callback")
    if normalized == "site_visit_planned" or "site visit" in action or "appointment" in action:
        tags.add("followup:site_visit")
    if next_action and str(next_action).strip():
        tags.add("action:required")
    if objections:
        tags.add("signal:objection")
    if normalized == "no_outcome":
        tags.add("quality:inconclusive")
    return sorted(tag for tag in tags if tag in STATUS_TAGS)


def empty_outcome(*, model: str, reason: str = "unavailable") -> dict[str, Any]:
    return {
        "disposition": "no_outcome",
        "disposition_confidence": 0.0,
        "summary_te": "",
        "summary_en": "",
        "next_action": None,
        "extracted_fields": {},
        "facts": {},
        "status_tags": ["outcome:no_outcome", "quality:inconclusive"],
        "objections": [],
        "notes": reason,
        "model": model,
        "prompt_version": "outcome_v1",
    }
