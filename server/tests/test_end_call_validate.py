"""Server hangup validation — LLM proposes, server decides."""
from server.call.end_call_validate import validate_end_call


def test_rejects_when_user_asked_a_question():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Bye"},
        user_text="can you tell me the price?",
        language="en-IN",
    )
    assert d.accepted is False
    assert d.reject_code == "user_asked_question"


def test_rejects_goodbye_without_evidence():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Bye"},
        user_text="I want two plants",
        language="en-IN",
    )
    assert d.accepted is False
    assert d.reject_code == "no_evidence"


def test_accepts_english_goodbye():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Thank you for your time. Goodbye."},
        user_text="ok bye hang up",
        language="en-IN",
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_accepts_telugu_refusal():
    d = validate_end_call(
        {"should_end": True, "reason": "firm_refusal", "farewell": "Sare, good day."},
        user_text="vaddu, not interested",
        language="te-IN",
        completed_turns=2,
    )
    assert d.accepted is True


def test_rejects_firm_refusal_on_first_turn():
    # Clear "not interested" may end immediately — do not require a prior pitch turn.
    d = validate_end_call(
        {"should_end": True, "reason": "firm_refusal", "farewell": "Bye"},
        user_text="not interested",
        language="en-IN",
        completed_turns=0,
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"


def test_infers_firm_refusal_when_model_forgets_end_call():
    d = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text="I'm not interested",
        language="en-IN",
        completed_turns=1,
        spoken_text="Thank you for your time. Goodbye.",
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"


def test_goal_complete_needs_memory():
    d = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Thanks, visit booked."},
        user_text="please wrap up the paperwork",
        language="en-IN",
        completed_turns=2,
    )
    assert d.reject_code == "no_evidence"
    ok = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Thanks, visit booked."},
        user_text="please wrap up the paperwork",
        language="en-IN",
        completed_turns=2,
        memory_snapshot={"facts": {"visit_status": "booked"}},
    )
    assert ok.accepted is True


def test_callback_confirm_can_complete_goal():
    d = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Our team will contact you. Goodbye."},
        user_text="Yes, please have the team call me back",
        language="en-IN",
        completed_turns=2,
    )
    assert d.accepted is True
    assert d.reason == "goal_complete"

def test_keep_calling_infers_hangup():
    d = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text="Why do you people keep calling me?",
        language="en-IN",
        completed_turns=4,
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_thanks_thats_all_for_now_bye_infers_hangup():
    d = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text="Thanks, that's all for now. Bye.",
        language="en-IN",
        completed_turns=10,
        spoken_text="Thank you for your time. Goodbye.",
    )
    assert d.accepted is True
    assert d.should_end is True
    assert d.reason == "goodbye"


def test_thanks_thats_all_infers_hangup():
    d = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text="Thanks, that's all.",
        language="en-IN",
        completed_turns=2,
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_not_looking_stays_on_the_line():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        user_text="I'm not looking right now.",
        language="en-IN",
        completed_turns=2,
    )
    assert d.accepted is False
    assert d.reject_code == "stay_on_line"


def test_policy_overlay_rejects_disallowed_reason():
    d = validate_end_call(
        {"should_end": True, "reason": "abuse", "farewell": "Goodbye."},
        user_text="I will kill you",
        language="en-IN",
        call_end_policy={"allowedReasons": ["goodbye"], "farewell": "Bye"},
    )
    assert d.reject_code == "policy_overlay"


def test_rejects_barge_in_flight():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Bye"},
        user_text="bye",
        language="en-IN",
        barge_in_flight=True,
    )
    assert d.reject_code == "barge_in_flight"


def test_rejects_while_caller_still_talking():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Bye"},
        user_text="bye",
        language="en-IN",
        last_stt_partial_at=10.0,
        now=10.2,
    )
    assert d.reject_code == "caller_still_talking"


def test_goal_complete_rejected_on_frustration():
    d = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Thanks."},
        user_text="I've already explained this twice.",
        language="en-IN",
        completed_turns=4,
        memory_snapshot={"facts": {"visit_status": "booked"}},
    )
    assert d.accepted is False
    assert d.reject_code == "stay_on_line"


def test_dont_call_overrides_wrong_goal_complete_reason():
    d = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Bye"},
        user_text="Don't call me again.",
        language="en-IN",
        completed_turns=3,
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_false_should_end_is_noop_without_goodbye():
    d = validate_end_call(
        {"should_end": False, "reason": "goodbye", "farewell": ""},
        user_text="I want two plants",
        language="en-IN",
    )
    assert d.accepted is False
    assert d.reject_code is None


def test_infers_hangup_when_llm_omits_end_call():
    d = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text="ok bye hang up",
        language="en-IN",
        completed_turns=2,
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_rejects_second_hangup():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Bye"},
        user_text="bye",
        language="en-IN",
        already_armed=True,
    )
    assert d.reject_code == "already_armed"


def test_explicitly_completed_information_goal_can_end():
    d = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text="Okay, I know the closing time now.",
        language="en-IN",
        completed_turns=3,
    )
    assert d.accepted is True
    assert d.reason == "goal_complete"


def test_out_of_scope_is_not_a_default_hangup_reason():
    from server.call.call_end_policy import default_call_end_policy

    assert "out_of_scope" not in default_call_end_policy("en-IN")["allowedReasons"]


def test_contact_me_tomorrow_is_callback_not_a_question():
    from server.call.end_call_validate import caller_requested_callback, caller_asked_to_record_details

    phrase = "record my name and phone number and contact me tomorrow"
    assert caller_requested_callback(phrase)
    assert caller_asked_to_record_details(phrase)
    assert caller_requested_callback("Can you record my name and phone number and contact me tomorrow?")
    assert caller_requested_callback("please get back to me tomorrow")
    assert not caller_requested_callback("how can I contact you?")
    assert not caller_requested_callback("don't contact me")


def test_record_details_callback_does_not_hangup_until_name_and_phone_exist():
    phrase = "record my name and phone number and contact me tomorrow"
    blocked = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text=phrase,
        language="en-IN",
        completed_turns=2,
        callback_close_phase="collecting_name",
    )
    assert blocked.accepted is False
    assert blocked.reject_code == "lead_details_missing"

    ready = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text=phrase,
        language="en-IN",
        completed_turns=3,
        spoken_text="Thank you, Subhash. Our team will contact you tomorrow. Goodbye.",
        memory_snapshot={"facts": {"caller_name": "Subhash", "callback_phone": "8897908470"}},
    )
    assert ready.accepted is True
    assert ready.reason == "goal_complete"


def test_busy_plus_contact_tomorrow_is_callback_not_stay_on_line():
    d = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text="I am busy, contact me tomorrow",
        language="en-IN",
        completed_turns=2,
    )
    assert d.accepted is True
    assert d.reason == "goal_complete"


def test_polite_cut_the_call_hangs_up():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        user_text="Can you cut the call please for me?",
        language="en-IN",
        completed_turns=3,
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_asr_call_this_call_hangs_up():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        user_text="Okay, understood. Can you call this call please for me?",
        language="en-IN",
        completed_turns=4,
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_sleeping_now_hangs_up():
    d = validate_end_call(
        {"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        user_text="I'm sleeping now.",
        language="en-IN",
        completed_turns=4,
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_have_to_go_hangs_up():
    d = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text="I have to go now",
        language="en-IN",
        completed_turns=3,
    )
    assert d.accepted is True
    assert d.reason == "goodbye"


def test_sleeping_with_callback_is_not_forced_goodbye():
    d = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text="I'm sleeping now, call me tomorrow",
        language="en-IN",
        completed_turns=2,
    )
    assert d.accepted is True
    assert d.reason == "goal_complete"
