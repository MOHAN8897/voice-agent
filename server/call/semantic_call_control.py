"""Grounded conversational proposals; deterministic transport/policy gates only."""
from __future__ import annotations

import time
from typing import Any

from server.call.close_decision import evidence_matches
from server.call.call_end_policy import allowed_reasons_for, server_farewell_for


def gate(proposal: Any, *, ctx: Any, transcript: str, language: str) -> dict:
    raw = proposal if isinstance(proposal, dict) else {}
    def reject(code: str) -> dict:
        return dict(should_end=False, reason="none", farewell="", contact_preference="none", reject_code=code)

    contact = raw.get("contact_intent", "none") if raw.get("contact_verified") is True else "none"
    contact_quote = str(raw.get("contact_evidence") or "")
    if contact != "none" and not evidence_matches(contact_quote, transcript):
        contact = "none"
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
    if raw.get("decision") != "close":
        return reject("semantic_continue")
    if raw.get("close_verified") is not True:
        return reject("close_not_verified")
    if not evidence_matches(str(raw.get("evidence") or ""), transcript):
        return reject("missing_evidence")
    if raw.get("remaining_request"):
        return reject("remaining_request")
    reason = raw.get("reason")
    if reason == "firm_refusal" and contact != "do_not_call":
        return reject("contact_scope_missing")
    if reason not in allowed_reasons_for(getattr(ctx, "call_end_policy", None)):
        return reject("policy_overlay")
    if getattr(ctx, "status", "active") != "active":
        return reject("call_not_active")
    if getattr(ctx, "agent_hangup_armed", False):
        return reject("already_armed")
    if getattr(ctx, "barge_in_flight", False):
        return reject("barge_in_flight")
    partial = getattr(ctx, "last_stt_partial_at", None)
    if partial and time.monotonic() - partial < .4:
        return reject("caller_still_talking")
    if getattr(ctx, "pending_tool_result", False):
        return reject("tool_result_pending")
    preference = "do_not_call" if contact == "do_not_call" or getattr(ctx, "contact_preference", "none") == "do_not_call" else (
        "callback" if getattr(ctx, "callback_request_text", "") else "end_call")
    ctx.agent_hangup_armed = True
    return dict(should_end=True, reason=reason, contact_preference=preference,
                farewell=server_farewell_for(language, policy=getattr(ctx, "call_end_policy", None),
                                             contact_preference=preference))
