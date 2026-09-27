"""Live API hangup + language tools (Gemini / OpenAI realtime)."""
from __future__ import annotations

import json
from typing import Any

from server.realtime.end_call_tool import parse_end_call_tool
from server.realtime.models import END_CALL_REASONS, END_CALL_TOOL

REQUEST_END_CALL_REASONS: tuple[str, ...] = (
    "customer_declined",
    "caller_goodbye",
    "goal_complete",
    "abuse",
    "out_of_scope",
)

_REQUEST_TO_INTERNAL: dict[str, str] = {
    "customer_declined": "firm_refusal",
    "caller_goodbye": "goodbye",
    "goal_complete": "goal_complete",
    "abuse": "abuse",
    "out_of_scope": "out_of_scope",
    # allow internal names if the model mirrors legacy schema
    "firm_refusal": "firm_refusal",
    "goodbye": "goodbye",
}

REQUEST_END_CALL_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "request_end_call",
    "description": (
        "Request the platform to end the call after you finish speaking. "
        "Call in the SAME turn as a short farewell when the caller clearly declined, "
        "said goodbye, or confirmed the next step (callback/visit). "
        "Use customer_declined for not interested / no need / don't call. "
        "Use caller_goodbye for bye, hang up, that's all. "
        "Use goal_complete only after callback or handoff details are captured and confirmed. "
        "Never call for bare okay/thanks, busy without ending, or an open question."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reason": {"type": "string", "enum": list(REQUEST_END_CALL_REASONS)},
            "farewell_required": {"type": "boolean"},
            "farewell_text": {"type": "string", "maxLength": 240},
        },
        "required": ["reason"],
    },
}

REQUEST_LANGUAGE_CALLBACK_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "request_language_callback",
    "description": (
        "Caller is speaking a language you cannot continue the call in. "
        "Call once to play the configured language-mismatch line, then wait. "
        "Do not hang up and do not pitch."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "caller_language": {
                "type": "string",
                "description": "Best guess: en, hi, te, ta, unknown, etc.",
            },
        },
    },
}

LIVE_HANGUP_TOOL_NAMES = frozenset({"end_call", "request_end_call"})


def realtime_hangup_tool_declarations() -> list[dict[str, Any]]:
    """Tools registered on Live sessions (hangup + legacy alias)."""
    return [REQUEST_END_CALL_TOOL, END_CALL_TOOL]


def parse_request_end_call_tool(raw: Any) -> dict[str, Any] | None:
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
    reason_key = str(payload.get("reason") or "").strip().lower()
    internal = _REQUEST_TO_INTERNAL.get(reason_key)
    if not internal or internal not in END_CALL_REASONS:
        return None
    farewell = str(payload.get("farewell_text") or payload.get("farewell") or "")[:240]
    farewell_required = payload.get("farewell_required")
    if farewell_required is None:
        farewell_required = True
    return {
        "should_end": True,
        "reason": internal,
        "farewell": farewell,
        "farewell_required": bool(farewell_required),
    }


def parse_live_hangup_tool(name: str, raw: Any) -> dict[str, Any] | None:
    tool = str(name or "").strip()
    if tool == "request_end_call":
        return parse_request_end_call_tool(raw)
    if tool == "end_call":
        parsed = parse_end_call_tool(raw)
        if parsed is None:
            return None
        parsed = dict(parsed)
        parsed.setdefault("farewell_required", True)
        return parsed
    return None
