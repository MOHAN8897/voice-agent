"""Critical hangup judgment — interested continue, not-interested end, objective complete."""
from __future__ import annotations

from server.call.end_call_validate import validate_end_call
from server.call.hangup_judge import (
    HANGUP_JUDGMENT_RULES,
    agent_spoke_closing,
    caller_wants_to_continue,
    memory_has_lead_handoff,
    user_short_close_ack,
)
from server.prompts.agent_voice_rules import live_realtime_output_rules
from server.realtime.models import END_CALL_TOOL


def _end(
    raw,
    *,
    user: str,
    spoken: str = "",
    turns: int = 2,
    memory: dict | None = None,
):
    return validate_end_call(
        raw,
        user_text=user,
        language="en-IN",
        completed_turns=turns,
        spoken_text=spoken,
        memory_snapshot=memory,
    )


def test_hangup_judgment_rules_in_realtime_instructions():
    rules = live_realtime_output_rules("en-IN")
    assert "HANGUP JUDGMENT" in rules
    assert "goal_complete" in rules
    assert "firm_refusal" in END_CALL_TOOL["description"]
    assert "goal_complete" in END_CALL_TOOL["description"]
    assert "interested" in HANGUP_JUDGMENT_RULES.lower()


def test_not_interested_hangs_even_without_model_tool():
    d = _end(
        {"should_end": False, "reason": "none", "farewell": ""},
        user="I'm not interested",
        spoken="",
        turns=0,
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"
    assert d.farewell


def test_not_interested_with_model_tool():
    d = _end(
        {
            "should_end": True,
            "reason": "firm_refusal",
            "farewell": "Thank you for your time. Goodbye.",
        },
        user="No thanks, not interested",
        spoken="Thank you for your time. Goodbye.",
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"


def test_interested_caller_continues_despite_premature_goal_complete():
    d = _end(
        {
            "should_end": True,
            "reason": "goal_complete",
            "farewell": "Goodbye.",
        },
        user="Yes I'm interested, tell me more about the plots",
        spoken="Goodbye.",
    )
    assert d.accepted is False
    assert d.reject_code == "caller_engaged"


def test_soft_maybe_stays_on_line():
    d = _end(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        user="Maybe later, I'll think about it",
    )
    assert d.accepted is False
    assert d.reject_code == "stay_on_line"


def test_objective_complete_callback_confirmed():
    d = _end(
        {
            "should_end": True,
            "reason": "goal_complete",
            "farewell": "Perfect — our team will contact you. Goodbye.",
        },
        user="Yes, please have the team call me back",
        spoken="Perfect — our team will contact you. Goodbye.",
    )
    assert d.accepted is True
    assert d.reason == "goal_complete"


def test_objective_complete_repairs_missed_tool_with_lead_memory():
    d = _end(
        {"should_end": False, "reason": "none", "farewell": ""},
        user="Okay",
        spoken="Noted — our team will contact you. Goodbye.",
        memory={"facts": {"callback_phone": "8897908470"}},
    )
    assert d.accepted is True
    assert d.reason == "goal_complete"


def test_objective_complete_short_ack_after_closing():
    d = _end(
        {"should_end": False, "reason": "none", "farewell": ""},
        user="Thanks",
        spoken="Our team will reach out shortly. Goodbye.",
        turns=3,
    )
    assert d.accepted is True
    assert d.reason == "goal_complete"


def test_price_question_does_not_hang_on_closing_speech():
    d = _end(
        {
            "should_end": True,
            "reason": "goal_complete",
            "farewell": "Our team will contact you. Goodbye.",
        },
        user="How much does a plot cost?",
        spoken="Our team will contact you. Goodbye.",
        memory={"facts": {"callback_phone": "8897908470"}},
    )
    assert d.accepted is False
    assert d.reject_code in {"user_asked_question", "caller_engaged"}


def test_goodbye_hangs():
    d = _end(
        {"should_end": False, "reason": "none", "farewell": ""},
        user="Ok bye, please hang up",
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_helpers_detect_closing_and_lead():
    assert agent_spoke_closing("Noted — our team will contact you. Goodbye.")
    assert agent_spoke_closing("All set, thanks for confirming — we'll take it from here.")
    assert not agent_spoke_closing(
        "Got it, I’m passing that along. I just need your name and a good phone number. "
        "Once I have that, our team will contact you tomorrow."
    )
    assert user_short_close_ack("Okay")
    assert user_short_close_ack("Ja, danke.")
    assert caller_wants_to_continue("I'm interested, tell me more")
    assert memory_has_lead_handoff({"facts": {"callback_phone": "8897908470"}})
    assert not memory_has_lead_handoff({"facts": {"phone": "+13526146416"}})


def test_thanks_after_handoff_repairs_missed_end_call():
    d = _end(
        {"should_end": False, "reason": "none", "farewell": ""},
        user="Ja, danke.",
        spoken="All set, thanks for confirming — we'll take it from here.",
        turns=6,
        memory={"facts": {"caller_name": "Mohan"}},
    )
    assert d.accepted is True
    assert d.reason == "goal_complete"


def test_garbled_close_fragment_does_not_block_handoff_hangup():
    d = _end(
        {"should_end": False, "reason": "none", "farewell": ""},
        user="Ja, kann das?",
        spoken="All set, thanks for confirming — we'll take it from here.",
        turns=8,
        memory={"facts": {"caller_name": "Mohan"}},
    )
    assert d.accepted is True
    assert d.reason == "goal_complete"


def test_callback_name_request_does_not_hangup():
    d = _end(
        {"should_end": False, "reason": "none", "farewell": ""},
        user="I'm busy right now. Can you call me tomorrow?",
        spoken=(
            "Got it, I’m passing that along. Since you asked to be called tomorrow, "
            "I just need your name and a good phone number to reach you on. "
            "Once I have that, our team will contact you tomorrow."
        ),
        turns=4,
    )
    assert d.accepted is False
    assert d.reject_code == "lead_details_missing"


def test_record_name_phone_contact_tomorrow_waits_for_details():
    d = _end(
        {
            "should_end": True,
            "reason": "goal_complete",
            "farewell": "Our team will contact you. Goodbye.",
        },
        user="record my name and phone number and contact me tomorrow",
        spoken="Our team will contact you. Goodbye.",
    )
    assert d.accepted is False
    assert d.reject_code == "lead_details_missing"

    ok = _end(
        {
            "should_end": True,
            "reason": "goal_complete",
            "farewell": "Thank you, Subhash. Our team will contact you tomorrow. Goodbye.",
        },
        user="record my name and phone number and contact me tomorrow",
        spoken="Thank you, Subhash. Our team will contact you tomorrow. Goodbye.",
        memory={"facts": {"caller_name": "Subhash", "callback_phone": "8897908470"}},
    )
    assert ok.accepted is True
    assert ok.reason == "goal_complete"
