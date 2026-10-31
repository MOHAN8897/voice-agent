"""Close contract regressions: meaning + evidence decide; phrases only repair.

Reproduces the false reject (Telugu semantic refusals) and false closes
("keep calling me with updates", negated refusal) from the hangup audit.
"""
from __future__ import annotations

import pytest

from server.call.close_decision import opt_out_evidence
from server.call.end_call_validate import caller_firm_refusal, validate_end_call
from server.call.hangup_judge import caller_wants_to_continue


def _close(
    user: str,
    *,
    language: str = "te-IN",
    reason: str = "firm_refusal",
    evidence: str = "",
    remaining: str = "",
    preference: str = "",
    tool_sourced: bool = False,
    **kwargs,
):
    return validate_end_call(
        {
            "decision": "close",
            "should_end": True,
            "reason": reason,
            "evidence": evidence,
            "remaining_request": remaining,
            "contact_preference": preference,
            "farewell": "Thank you. Goodbye.",
        },
        user_text=user,
        language=language,
        completed_turns=kwargs.pop("completed_turns", 2),
        tool_sourced=tool_sourced,
        **kwargs,
    )


@pytest.mark.parametrize(
    "user",
    ["నాకు ఇవేమీ అక్కర్లేదండి", "ippudu em avasaram ledandi"],
)
def test_semantic_refusal_closes_without_a_phrase_list_match(user):
    decision = _close(user, evidence=user, preference="end_call")

    assert decision.accepted is True
    assert decision.reason == "not_interested"
    # Ending this call is not a permanent opt-out.
    assert decision.contact_preference == "end_call"


def test_keep_calling_with_updates_is_continuation_not_goodbye():
    user = "Please keep calling me with updates."
    assert caller_wants_to_continue(user) is True

    decision = _close(user, language="en-IN", reason="goodbye", evidence=user)

    assert decision.accepted is False
    assert decision.reject_code == "caller_engaged"


def test_negated_refusal_with_continue_request_stays_on_the_line():
    user = "I never said I am not interested, please tell me more."
    assert caller_firm_refusal(user) is False

    decision = _close(user, language="en-IN", evidence="not interested")

    assert decision.accepted is False
    assert decision.reject_code == "caller_engaged"


def test_plain_refusal_never_becomes_a_permanent_opt_out():
    decision = _close(
        "I'm not interested.",
        language="en-IN",
        evidence="I'm not interested",
        preference="do_not_call",
    )

    assert decision.accepted is True
    assert decision.reason == "not_interested"
    assert decision.contact_preference == "end_call"


def test_explicit_opt_out_is_recorded_separately_from_ending_this_call():
    user = "Don't call me again."
    assert opt_out_evidence(user) is True

    decision = _close(
        user,
        language="en-IN",
        reason="goodbye",
        evidence=user,
        preference="do_not_call",
    )

    assert decision.accepted is True
    assert decision.reason == "firm_refusal"
    assert decision.contact_preference == "do_not_call"


def test_unlisted_language_opt_out_needs_evidence_from_the_callers_words():
    user = "ఇక కాల్ చేయకండి"
    decision = _close(user, evidence=user, preference="do_not_call")

    assert decision.accepted is True
    assert decision.contact_preference == "do_not_call"


def test_soft_dont_call_with_a_callback_is_not_a_permanent_opt_out():
    user = "Don't call me at night, call me tomorrow."
    assert opt_out_evidence(user) is False

    decision = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text=user,
        language="en-IN",
        completed_turns=2,
    )

    assert not (decision.accepted and decision.contact_preference == "do_not_call")


def test_remaining_question_blocks_close():
    decision = _close(
        "I don't need this, but what is the price?",
        language="en-IN",
        evidence="I don't need this",
        remaining="what is the price?",
    )

    assert decision.accepted is False
    assert decision.reject_code == "remaining_request"


def test_conflicting_decision_and_should_end_are_rejected():
    decision = validate_end_call(
        {
            "decision": "close",
            "should_end": False,
            "reason": "goodbye",
            "farewell": "Bye",
        },
        user_text="I want two plants",
        language="en-IN",
    )

    assert decision.accepted is False
    assert decision.reject_code == "decision_conflict"


def test_evidence_span_must_come_from_the_callers_current_turn():
    decision = _close("నాకు ఇవేమీ అక్కర్లేదండి", evidence="not interested")

    assert decision.accepted is False
    assert decision.reject_code == "evidence_not_quoted"
    assert decision.evidence_valid is False


def test_callback_is_a_contact_preference_not_an_opt_out():
    decision = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text="I am busy, contact me tomorrow",
        language="en-IN",
        completed_turns=2,
    )

    assert decision.accepted is True
    assert decision.reason == "goal_complete"
    assert decision.contact_preference == "callback"
