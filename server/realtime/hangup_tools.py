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
        "Handle a genuine communication barrier, not simply a different caller language. "
        "If the meaning is understood, answer in the configured language without this tool. "
        "First use remind, politely ask for the configured language and wait. Only after a later "
        "caller turn still needs another language use request_callback. On success confirm the "
        "request (not a scheduled booking), say farewell in configured language, then end_call. "
        "Do not use for loanwords, transliteration, unclear audio, or opt-outs."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "action": {"type": "string", "enum": ["remind", "request_callback"]},
            "communication_blocked": {"type": "boolean", "description": "True only when a genuine language barrier prevents progress. False for understood mixed-language speech, names, short replies or garbled audio."},
            "caller_language": {"type": "string", "description": "BCP-47 language code, e.g. hi-IN; unknown if unclear."},
            "summary": {"type": "string", "maxLength": 1200, "description": "English handoff: caller need, known details, requested language. No invented booking or time."},
        },
        "required": ["action", "caller_language", "summary", "communication_blocked"],
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
    raw_end = payload.get("should_end")
    if raw_end is False or (isinstance(raw_end, str) and raw_end.strip().lower() in ("false", "0", "no")):
        return {"should_end": False, "reason": "none", "farewell": ""}
    reason_key = str(payload.get("reason") or "").strip().lower()
    if reason_key in ("", "none", "null"):
        return None
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
