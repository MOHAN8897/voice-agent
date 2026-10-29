"""Post-call outcome schema, disposition enum and tag taxonomy (locked)."""
from __future__ import annotations

import re
import unicodedata
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

#: Controlled tag vocabulary. Deterministic categories (outcome/contact/
#: compliance/quality) are derived by the server; the model may only choose the
#: conversational categories below. Custom tags are namespaced and sanitised so
#: tenant-facing surfaces never render model-invented markup or vendor names.
TAG_VOCABULARY: dict[str, tuple[str, ...]] = {
    "outcome": tuple(sorted(DISPOSITIONS)),
    "intent": (
        "booking",
        "cancellation",
        "complaint",
        "demo",
        "information",
        "job_application",
        "partnership",
        "pricing",
        "purchase",
        "quote",
        "renewal",
        "reschedule",
        "support",
    ),
    "sentiment": ("frustrated", "negative", "neutral", "positive"),
    "signal": (
        "budget_confirmed",
        "competitor_mentioned",
        "decision_maker",
        "do_not_call",
        "needs_approval",
        "objection",
        "price_sensitive",
        "ready_to_buy",
        "repeat_customer",
        "urgent",
    ),
    "followup": ("callback", "schedule_pending", "send_info", "send_quote", "site_visit"),
    "contact": ("email_known", "name_known", "phone_known", "preferred_language"),
    "compliance": ("disclosure_delivered", "disclosure_missing", "recording_objected"),
    "quality": (
        "agent_failure",
        "inconclusive",
        "language_mismatch",
        "poor_audio",
        "short_call",
        "tts_failure",
    ),
    "action": ("required", "urgent"),
}

STATUS_TAGS = frozenset(f"{category}:{value}" for category, values in TAG_VOCABULARY.items() for value in values)

#: Categories the model may choose from. Everything else is server-derived so a
#: hallucinated compliance or outcome tag can never overwrite the truth.
MODEL_TAG_CATEGORIES = frozenset({"intent", "sentiment", "signal", "followup", "action"})
MODEL_STATUS_TAGS = frozenset(
    tag for tag in STATUS_TAGS if tag.split(":", 1)[0] in MODEL_TAG_CATEGORIES
)

CUSTOM_TAG_PREFIX = "custom:"
CUSTOM_TAG_LIMIT = 3
STATUS_TAG_LIMIT = 12
_CUSTOM_TAG_BLOCKED = frozenset(
    {
        "composio",
        "exotel",
        "gemini",
        "nango",
        "openai",
        "plivo",
        "razorpay",
        "sarvam",
        "telnyx",
        "vobiz",
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
        "tags",
        "custom_tags",
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
        "tags": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(MODEL_STATUS_TAGS)},
        },
        "custom_tags": {"type": "array", "items": {"type": "string"}},
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
    callee_e164: str | None = None,
    direction: str | None = None,
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
    dir_norm = str(direction or "").strip().lower()
    outbound = dir_norm in ("outbound", "outgoing", "outbound-api")
    if not any(k in merged for k in ("phone", "callback_phone", "contact", "phone_number")):
        if outbound and callee_e164:
            merged["phone"] = str(callee_e164).strip()
        elif not outbound and caller_id:
            merged["phone"] = str(caller_id).strip()
    return dict(sorted(merged.items()))


def normalize_model_tags(raw: Any) -> list[str]:
    """Keep only allow-listed conversational tags; order preserved, deduped."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return []
    out: list[str] = []
    for item in raw:
        tag = str(item or "").strip().lower()
        if tag in MODEL_STATUS_TAGS and tag not in out:
            out.append(tag)
    return out


def _slug(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = "".join(char if unicodedata.category(char)[0] in {"L", "M", "N"} else "-" for char in normalized)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:28].strip("-")


def normalize_custom_tags(raw: Any) -> list[str]:
    """Sanitise free-form model tags into ``custom:<slug>`` values."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or re.search(r"@|https?://|[<>]|(?:\d[\s+().-]*){7,}", item, re.IGNORECASE):
            continue
        item = item.removeprefix(CUSTOM_TAG_PREFIX)
        slug = _slug(item)
        if len(slug) < 2 or any(blocked in slug for blocked in _CUSTOM_TAG_BLOCKED):
            continue
        tag = f"{CUSTOM_TAG_PREFIX}{slug}"
        if tag not in out:
            out.append(tag)
        if len(out) >= CUSTOM_TAG_LIMIT:
            break
    return out


def derive_status_tags(
    disposition: str | None,
    facts: dict[str, str] | None,
    *,
    next_action: str | None = None,
    objections: list[Any] | None = None,
    model_tags: Any = None,
    custom_tags: Any = None,
    disclosure_status: str | None = None,
    agent_failure: bool = False,
    contact_preference: str | None = None,
) -> list[str]:
    """Merge server-derived truth with the model's bounded tag choices.

    Deterministic tags are added first so the cap can never drop the outcome or
    compliance signal. Model tags can only come from the conversational
    categories, and custom tags are sanitised slugs.
    """
    normalized = validate_disposition(disposition)
    tags = {f"outcome:{normalized}"}
    if contact_preference == "do_not_call":
        tags.add("signal:do_not_call")
    normalized_facts = {str(k).lower(): str(v).strip() for k, v in (facts or {}).items() if str(v).strip()}
    if any(k in normalized_facts for k in ("name", "caller_name", "customer_name", "full_name")):
        tags.add("contact:name_known")
    if any(k in normalized_facts for k in ("phone", "callback_phone", "contact", "phone_number", "mobile")):
        tags.add("contact:phone_known")
    if any(k in normalized_facts for k in ("email", "mail", "email_address")):
        tags.add("contact:email_known")
    if any(k in normalized_facts for k in ("language", "preferred_language", "caller_language")):
        tags.add("contact:preferred_language")
    action = str(next_action or "").lower()
    if contact_preference == "callback" or normalized == "callback_required" or "callback" in action or "call back" in action:
        tags.add("followup:callback")
    if normalized == "site_visit_planned" or "site visit" in action or "appointment" in action:
        tags.add("followup:site_visit")
    if next_action and str(next_action).strip():
        tags.add("action:required")
    if objections:
        tags.add("signal:objection")
    if normalized == "no_outcome":
        tags.add("quality:inconclusive")
    if agent_failure:
        tags.add("quality:agent_failure")
    if disclosure_status == "delivered":
        tags.add("compliance:disclosure_delivered")
    elif disclosure_status == "missing":
        tags.add("compliance:disclosure_missing")

    ordered = [tag for tag in sorted(tags) if tag in STATUS_TAGS]
    model_choices = [tag for tag in normalize_model_tags(model_tags) if tag != "signal:do_not_call"]
    sentiments = {tag for tag in model_choices if tag.startswith("sentiment:")}
    if len(sentiments) > 1:
        model_choices = [tag for tag in model_choices if not tag.startswith("sentiment:")]
    if normalized in {"not_interested", "wrong_number", "no_outcome"} or contact_preference == "do_not_call":
        model_choices = [tag for tag in model_choices if tag != "signal:ready_to_buy"]
    for tag in model_choices:
        if len(ordered) >= STATUS_TAG_LIMIT:
            break
        if tag not in ordered:
            ordered.append(tag)
    for tag in normalize_custom_tags(custom_tags):
        if len(ordered) >= STATUS_TAG_LIMIT:
            break
        if tag not in ordered:
            ordered.append(tag)
    if "signal:do_not_call" in ordered or normalized == "wrong_number":
        ordered = [tag for tag in ordered if not tag.startswith(("followup:", "action:"))]
    return sorted(ordered)


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
        "tags": [],
        "custom_tags": [],
        "objections": [],
        "notes": reason,
        "model": model,
        "prompt_version": "outcome_v4",
    }
