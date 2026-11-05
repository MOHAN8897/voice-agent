"""WhatsApp/SMS only reach the caller's own number, or a number the caller said and confirmed."""
from __future__ import annotations

from server.services import phone_recipient_guard as guard


def _turns(monkeypatch, turns):
    monkeypatch.setattr("server.services.recipient_guard.caller_turns", lambda _call: list(turns))
    guard.reset_for_tests()


def test_callers_own_number_goes_straight_through(monkeypatch):
    _turns(monkeypatch, ["Send me the brochure on WhatsApp"])
    assert guard.check("c1", "WHATSAPP_SEND_MESSAGE", {"to": "+919876543210"}, caller_phone="919876543210") is None


def test_a_number_the_caller_never_said_is_refused(monkeypatch):
    _turns(monkeypatch, ["Send it to my friend please"])
    result = guard.check("c1", "WHATSAPP_SEND_MESSAGE", {"to": "+919000000001"}, caller_phone="919876543210")
    assert result["status"] == "error" and "Nothing was sent" in result["message"]


def test_another_spoken_number_is_read_back_once(monkeypatch):
    turns = ["Please send it to 9000000001 instead"]
    _turns(monkeypatch, turns)
    first = guard.check("c1", "TWILIO_SMS_SEND_MESSAGE", {"to": "+919000000001"}, caller_phone="919876543210")
    assert first["status"] == "needs_confirmation" and "9 0 0 0 0 0 0 0 0 1" in first["message"]
    turns.append("Yes, that's right")
    assert guard.check("c1", "TWILIO_SMS_SEND_MESSAGE", {"to": "+919000000001"}, caller_phone="919876543210") is None


def test_other_actions_are_untouched(monkeypatch):
    _turns(monkeypatch, [])
    assert guard.check("c1", "GMAIL_SEND_EMAIL", {"to": "a@b.co"}) is None
