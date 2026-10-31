"""Grounded conversational proposals; deterministic transport/policy gates only."""
from __future__ import annotations

import time
from typing import Any

from server.call.close_decision import evidence_matches
from server.call.call_end_policy import allowed_reasons_for, server_farewell_for


def _verified_contact(raw: dict, transcript: str) -> str:
    contact = raw.get("contact_intent", "none") if raw.get("contact_verified") is True else "none"
    if contact != "none" and not evidence_matches(str(raw.get("contact_evidence") or ""), transcript):
        return "none"
    return contact


def close_rejection(proposal: Any, *, ctx: Any, transcript: str) -> str | None:
    """Why ``gate`` would refuse this close, or None when it would close. No side effects.

    The reply stage skips generation for a verified close; it must use the same rules,
    or a refused close leaves the caller in silence with the call still open.
    """
    raw = proposal if isinstance(proposal, dict) else {}
    if raw.get("decision") != "close":
        return "semantic_continue"
    if raw.get("close_verified") is not True:
        return "close_not_verified"
    if not evidence_matches(str(raw.get("evidence") or ""), transcript):
        return "missing_evidence"
    if raw.get("remaining_request"):
        return "remaining_request"
    reason = raw.get("reason")
    if reason == "firm_refusal" and _verified_contact(raw, transcript) != "do_not_call":
        return "contact_scope_missing"
    if reason not in allowed_reasons_for(getattr(ctx, "call_end_policy", None)):
        return "policy_overlay"
    if getattr(ctx, "status", "active") != "active":
        return "call_not_active"
    if getattr(ctx, "agent_hangup_armed", False):
        return "already_armed"
    if getattr(ctx, "barge_in_flight", False):
        return "barge_in_flight"
    partial = getattr(ctx, "last_stt_partial_at", None)
    if partial and time.monotonic() - partial < .4:
        return "caller_still_talking"
    if getattr(ctx, "pending_tool_result", False):
        return "tool_result_pending"
    return None


def gate(proposal: Any, *, ctx: Any, transcript: str, language: str) -> dict:
    raw = proposal if isinstance(proposal, dict) else {}
    def reject(code: str) -> dict:
        return dict(should_end=False, reason="none", farewell="", contact_preference="none", reject_code=code)

    contact = _verified_contact(raw, transcript)
    if contact in {"decline_callback", "self_callback", "do_not_call"}:
        ctx.callback_request_text = ""
        ctx.callback_close_phase = "idle"
        ctx.callback_when = ""
    elif contact == "callback":
        ctx.callback_request_text = transcript
        ctx.callback_close_phase = "semantic_pending"
        when = str(raw.get("callback_time") or "")
        if when and when in transcript:
            ctx.callback_when = when
    refused = close_rejection(raw, ctx=ctx, transcript=transcript)
    if refused:
        return reject(refused)
    reason = raw.get("reason")
    preference = "do_not_call" if contact == "do_not_call" or getattr(ctx, "contact_preference", "none") == "do_not_call" else (
        "callback" if getattr(ctx, "callback_request_text", "") else "end_call")
    ctx.agent_hangup_armed = True
    return dict(should_end=True, reason=reason, contact_preference=preference,
                farewell=server_farewell_for(language, policy=getattr(ctx, "call_end_policy", None),
                                             contact_preference=preference))
