"""An email the caller says in this very turn counts, even before the transcript row is saved."""
from __future__ import annotations

from types import SimpleNamespace

from server.services import recipient_guard


def test_current_turn_counts_before_the_transcript_is_written(monkeypatch):
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_lines", lambda _call: [])
    ctx = SimpleNamespace(pending_caller_turn="Book 11 AM, my email is ravi.test@example.com")
    monkeypatch.setattr("server.call.call_context.get", lambda _call: ctx)
    recipient_guard.reset_for_tests()
    assert recipient_guard.check("c1", "GOOGLECALENDAR_CREATE_EVENT", {"attendee_email": "ravi.test@example.com"}) is None


def test_the_current_turn_is_not_counted_twice(monkeypatch):
    monkeypatch.setattr("server.call.call_ledger.call_ledger.read_lines",
                        lambda _call: [{"role": "user", "text": "yes"}])
    monkeypatch.setattr("server.call.call_context.get", lambda _call: SimpleNamespace(pending_caller_turn="yes"))
    assert recipient_guard.caller_turns("c1") == ["yes"]
