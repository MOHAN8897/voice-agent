"""A caller's request that a person from the business contacts them.

A voice agent cannot transfer the call, but every agent can pass the request on,
whatever its script says. The request is saved like a callback request (same
table, same console list) and marked as a human handoff, so the business sees it
as its own task rather than an objection, and the agent never answers it with
only "I can't connect you" (call 35002575 issue 3).
"""
from __future__ import annotations

from typing import Any

HANDOFF_ACTION = "REQUEST_HUMAN_HANDOFF"
HANDOFF_KEY_PREFIX = "handoff:"
HANDOFF_ROLES = ("manager", "owner", "team", "named_person", "any_person")

REQUEST_HUMAN_HANDOFF_TOOL: dict[str, Any] = {
    "type": "function", "name": HANDOFF_ACTION,
    "description": (
        "Pass on the caller's request that a person from the business (a manager, the owner, the team "
        "or a named person) contacts them. Available on every call, without integrations. Use it when the "
        "caller asks to speak to, be connected to, or be called back by such a person. It does not transfer "
        "this call or fix a time. After status ok, say you will pass it to the manager or team; never answer "
        "the request with only that you cannot connect them."
    ),
    "parameters": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "contact_role": {"type": "string", "enum": list(HANDOFF_ROLES)},
            "contact_name": {"type": "string", "maxLength": 120},
            "reason": {"type": "string", "maxLength": 600},
            "requested_time": {"type": "string", "maxLength": 200},
            "caller_words": {"type": "string", "maxLength": 800},
        },
        "required": ["contact_role", "caller_words"],
    },
}

# Argument name -> the camelCase key stored on the call and shown in the console.
_STORED = {"contact_role": "contactRole", "contact_name": "contactName", "reason": "reason",
           "requested_time": "requestedTime", "caller_words": "callerWords"}


def handoff_details(arguments: Any) -> dict[str, str] | None:
    """Validated, trimmed handoff fields, or None when the request is unusable."""
    if not isinstance(arguments, dict) or set(arguments) - set(_STORED):
        return None
    props = REQUEST_HUMAN_HANDOFF_TOOL["parameters"]["properties"]
    details: dict[str, str] = {}
    for key, stored in _STORED.items():
        value = arguments.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            return None
        text = value.strip()[:props[key].get("maxLength", 40)]
        if text:
            details[stored] = text
    if details.get("contactRole") not in HANDOFF_ROLES or not details.get("callerWords"):
        return None
    if details["contactRole"] == "named_person" and not details.get("contactName"):
        # A named person needs the name; otherwise it is a request for anyone.
        details["contactRole"] = "any_person"
    return details


def merge_handoff(previous: Any, update: dict[str, str]) -> dict[str, str]:
    """A later mention in the same call adds detail; it never erases an earlier one."""
    merged = {k: str(v) for k, v in (previous or {}).items() if k in _STORED.values() and str(v or "").strip()}
    merged.update({k: v for k, v in update.items() if v})
    return merged


def _language(ctx: Any) -> str:
    stack = getattr(ctx, "resolved_stack", None)
    return str(getattr(stack, "language", "") or getattr(ctx, "language", "") or "en-IN")


async def save_human_handoff(*, ctx: Any, arguments: dict) -> dict[str, Any]:
    """Durably save the handoff before the agent says it will pass it on."""
    from server.call.call_end_policy import handoff_acknowledgement_for
    from server.services.saas.callback_request_service import record_callback_request

    details = handoff_details(arguments)
    if details is None:
        return {"status": "error", "message": "Who should contact the caller and the caller's words are required."}
    if not details.get("requestedTime") and str(getattr(ctx, "callback_when", "") or "").strip():
        details["requestedTime"] = str(ctx.callback_when).strip()[:200]
    details = merge_handoff(getattr(ctx, "human_handoff", None), details)
    saved = await record_callback_request(ctx, details["callerWords"], handoff=details)
    if not saved:
        return {"status": "error", "message": "The request could not be saved. Do not say it was passed on."}
    ctx.human_handoff = details
    ctx.human_handoff_id = saved["id"]
    return {"status": "ok", "request_saved": True, "handoff_saved": True,
            "say": handoff_acknowledgement_for(_language(ctx))}


def is_handoff_key(dial_request_id: Any) -> bool:
    return str(dial_request_id or "").startswith(HANDOFF_KEY_PREFIX)


_ROLE_LABELS = {"manager": "Manager", "owner": "Owner", "team": "Someone from the team",
                "named_person": "", "any_person": "A person from the business"}


def handoff_contact_label(details: dict[str, Any]) -> str:
    """'Manager', 'Owner', or the named person, for console text."""
    role = str(details.get("contactRole") or "")
    if role == "named_person" and details.get("contactName"):
        return str(details["contactName"])
    label = _ROLE_LABELS.get(role) or _ROLE_LABELS["any_person"]
    name = str(details.get("contactName") or "").strip()
    return f"{label} ({name})" if name and role != "named_person" else label


def handoff_facts(meta: dict[str, Any]) -> dict[str, str]:
    """Activity-detail facts for a saved handoff, from the call's metadata."""
    details = meta.get("human_handoff") if isinstance(meta.get("human_handoff"), dict) else {}
    if not details:
        return {}
    return {
        "kindLabel": "Asked for a person from the business",
        "handoffTo": handoff_contact_label(details),
        "handoffReason": str(details.get("reason") or ""),
        "requestedWhen": str(details.get("requestedTime") or ""),
        "requestText": str(details.get("callerWords") or ""),
    }


def handoff_facts_for_call(call_id: Any, tenant_id: Any) -> dict[str, str]:
    """``handoff_facts`` for one of this tenant's calls; empty when it is not theirs."""
    from server.call.call_ledger import call_ledger

    try:
        meta = call_ledger.read_meta(str(call_id)) or {}
    except Exception:  # noqa: BLE001 -- a detail label must never break the panel.
        return {}
    if str(meta.get("tenant_id") or "") != str(tenant_id):
        return {}
    return handoff_facts(meta)
