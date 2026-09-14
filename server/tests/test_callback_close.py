"""Callback close state machine — collect details before hangup when asked."""
from server.call.callback_close import (
    PHASE_CLOSING_ALLOWED,
    PHASE_COLLECTING_NAME,
    PHASE_COLLECTING_PHONE,
    PHASE_IDLE,
    advance_callback_close,
    hint_for_phase,
)


def test_idle_when_caller_is_just_talking():
    state = advance_callback_close(None, "what is the price?")
    assert state.phase == PHASE_IDLE
    assert state.hint is None


def test_simple_callback_is_ready_to_close():
    state = advance_callback_close(None, "I am busy, contact me tomorrow")
    assert state.phase == PHASE_CLOSING_ALLOWED
    assert state.missing is None
    assert state.when.lower() == "tomorrow"
    assert "end_call" in (state.hint or "")


def test_record_details_collects_name_then_phone():
    phrase = "record my name and phone number and contact me tomorrow"
    first = advance_callback_close(None, phrase, request_text=phrase)
    assert first.phase == PHASE_COLLECTING_NAME
    assert first.missing == "name"
    assert "ask ONLY for their name" in (first.hint or "")

    second = advance_callback_close(
        None,
        "Subhash",
        extra_slots={"name": "Subhash"},
        request_text=phrase,
    )
    assert second.phase == PHASE_COLLECTING_PHONE
    assert second.missing == "phone"
    assert second.name == "Subhash"

    third = advance_callback_close(
        None,
        "8897908470",
        extra_slots={"name": "Subhash", "phone": "8897908470"},
        request_text=phrase,
        memory_snapshot={"facts": {"caller_name": "Subhash", "callback_phone": "8897908470"}},
    )
    assert third.phase == PHASE_CLOSING_ALLOWED
    assert third.missing is None
    assert third.phone == "8897908470"


def test_hint_for_closing_does_not_ask_for_more_fields():
    hint = hint_for_phase(PHASE_CLOSING_ALLOWED)
    assert hint is not None
    assert "Do not pitch" in hint
