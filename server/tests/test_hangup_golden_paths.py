"""Golden-path hangup scenarios — judgment + callback phase + executor order."""
from __future__ import annotations

import pytest

from server.call.callback_close import (
    PHASE_CLOSING_ALLOWED,
    PHASE_COLLECTING_NAME,
    advance_callback_close,
)
from server.call.close_call_executor import canonical_lifecycle_reason
from server.call.end_call_validate import validate_end_call


def _end(
    user: str,
    *,
    spoken: str = "",
    memory=None,
    should_end: bool = True,
    phase: str | None = None,
    reason: str = "goal_complete",
):
    return validate_end_call(
        {"should_end": should_end, "reason": reason, "farewell": spoken or "Goodbye."},
        user_text=user,
        language="en-IN",
        completed_turns=2,
        spoken_text=spoken,
        memory_snapshot=memory,
        callback_close_phase=phase,
    )


def test_not_interested_hangs_up():
    d = _end("I'm not interested", spoken="Thank you for your time. Goodbye.")
    assert d.accepted is True
    assert d.reason == "firm_refusal"
    assert canonical_lifecycle_reason(d.reason) == "firm_refusal"


def test_bye_hangs_up():
    d = _end("ok bye hang up", spoken="Thank you. Goodbye.")
    assert d.accepted is True
    assert d.reason == "goodbye"
    assert canonical_lifecycle_reason(d.reason) == "goodbye"


def test_call_me_tomorrow_hangs_up():
    phrase = "call me tomorrow"
    state = advance_callback_close(None, phrase)
    assert state.phase == PHASE_CLOSING_ALLOWED
    d = _end(phrase, spoken="We will call you tomorrow. Goodbye.", phase=state.phase)
    assert d.accepted is True
    assert d.reason == "goal_complete"


def test_record_details_stays_open_until_name_and_phone():
    phrase = "record my name and phone number and contact me tomorrow"
    state = advance_callback_close(None, phrase, request_text=phrase)
    assert state.phase == PHASE_COLLECTING_NAME
    blocked = _end(phrase, spoken="Great, we have several plot options.", phase=state.phase)
    assert blocked.accepted is False
    assert blocked.reject_code == "lead_details_missing"

    ready_state = advance_callback_close(
        None,
        "8897908470",
        extra_slots={"name": "Subhash", "phone": "8897908470"},
        request_text=phrase,
        memory_snapshot={"facts": {"caller_name": "Subhash", "callback_phone": "8897908470"}},
    )
    assert ready_state.phase == PHASE_CLOSING_ALLOWED
    ready = _end(
        phrase,
        spoken="Thank you, Subhash. Our team will contact you tomorrow. Goodbye.",
        memory={"facts": {"caller_name": "Subhash", "callback_phone": "8897908470"}},
        phase=ready_state.phase,
    )
    assert ready.accepted is True
    assert ready.reason == "goal_complete"


def test_price_question_does_not_hang_up():
    d = _end("can you tell me the price?", spoken="Goodbye.", reason="goodbye")
    assert d.accepted is False
    assert d.reject_code == "user_asked_question"


@pytest.mark.asyncio
async def test_natural_hangup_test_module_still_covers_playback():
    """Sanity: golden suite depends on natural hangup wait+pause remaining the executor core."""
    from server.call.natural_hangup import pause_before_disconnect

    await pause_before_disconnect(should_pause=False, trail_sec=1.0)
