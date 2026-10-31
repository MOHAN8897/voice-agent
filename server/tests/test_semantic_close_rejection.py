"""The reply stage may skip generation only when the close gate will really close."""
from types import SimpleNamespace

from server.call.semantic_call_control import close_rejection, gate


def _ctx(**kw):
    return SimpleNamespace(status="active", agent_hangup_armed=False, barge_in_flight=False, last_stt_partial_at=None,
                           pending_tool_result=False, call_end_policy=None, contact_preference="none",
                           callback_request_text="", callback_close_phase="idle", callback_when="", **kw)


SAID = "Okay, I will think about it after talking to my doctor."


def test_evidence_not_in_turn_is_refused_by_both_stages():
    proposal = {"decision": "close", "close_verified": True, "reason": "goodbye", "evidence": "bye then",
                "remaining_request": ""}
    assert close_rejection(proposal, ctx=_ctx(), transcript=SAID) == "missing_evidence"
    assert gate(proposal, ctx=_ctx(), transcript=SAID, language="en-IN")["should_end"] is False


def test_refusal_without_opt_out_scope_is_refused_by_both_stages():
    proposal = {"decision": "close", "close_verified": True, "reason": "firm_refusal", "evidence": SAID,
                "remaining_request": "", "contact_intent": "none"}
    assert close_rejection(proposal, ctx=_ctx(), transcript=SAID) == "contact_scope_missing"
    assert gate(proposal, ctx=_ctx(), transcript=SAID, language="en-IN")["should_end"] is False


def test_accepted_close_agrees():
    proposal = {"decision": "close", "close_verified": True, "reason": "goodbye", "evidence": SAID,
                "remaining_request": ""}
    assert close_rejection(proposal, ctx=_ctx(), transcript=SAID) is None
    assert gate(proposal, ctx=_ctx(), transcript=SAID, language="en-IN")["should_end"] is True
