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
        "extracted_fields": {"type": "object", "additionalProperties": {"type": "string"}},
        "objections": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": ["string", "null"]},
    },
}


def validate_disposition(value: str | None) -> str:
    if value in DISPOSITIONS:
        return value  # type: ignore[return-value]
    return "no_outcome"


def empty_outcome(*, model: str, reason: str = "unavailable") -> dict[str, Any]:
    return {
        "disposition": "no_outcome",
        "disposition_confidence": 0.0,
        "summary_te": "",
        "summary_en": "",
        "next_action": None,
        "extracted_fields": {},
        "objections": [],
        "notes": reason,
        "model": model,
        "prompt_version": "outcome_v1",
    }
