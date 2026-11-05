"""A cancellation during a call needs the caller's answer first; moving a booking never cancels it."""
from __future__ import annotations

from server.services import cancellation_guard


def test_first_cancel_asks_the_caller_and_the_answer_lets_it_through(monkeypatch):
    turns = ["Please move my visit to 12."]
    monkeypatch.setattr("server.services.recipient_guard.caller_turns", lambda _call: list(turns))
    cancellation_guard.reset_for_tests()
    first = cancellation_guard.check("call-1", "GOOGLECALENDAR_CANCEL_EVENT", {"event_id": "evt-1"})
    assert first and first["status"] == "needs_confirmation"
    assert "Nothing was cancelled" in first["message"] and "reschedule" in first["message"]
    # Same turn, no answer yet: still blocked.
    assert cancellation_guard.check("call-1", "GOOGLECALENDAR_CANCEL_EVENT", {"event_id": "evt-1"})["status"] == "needs_confirmation"
    turns.append("Yes, cancel it completely.")
    assert cancellation_guard.check("call-1", "GOOGLECALENDAR_CANCEL_EVENT", {"event_id": "evt-1"}) is None


def test_other_actions_are_untouched():
    assert cancellation_guard.check("call-1", "GOOGLECALENDAR_RESCHEDULE_EVENT", {"event_id": "evt-1"}) is None
    assert cancellation_guard.check("call-1", "GOOGLECALENDAR_CREATE_EVENT", {}) is None
