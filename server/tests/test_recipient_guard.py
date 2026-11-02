from unittest.mock import patch

import pytest

from server.services import recipient_guard


@pytest.fixture(autouse=True)
def _fresh():
    recipient_guard.reset_for_tests()
    yield
    recipient_guard.reset_for_tests()


def _said(*turns):
    return patch.object(recipient_guard, "caller_turns", return_value=list(turns))


def test_spoken_address_matches_what_the_model_wrote():
    assert recipient_guard.spoken_form("it's mohan sai teja dot nine nine at gmail dot com").endswith("mohansaiteja.99@gmail.com")
    with _said("my email is mohan sai teja dot nine nine at gmail dot com"):
        assert recipient_guard.check("c1", "GMAIL_SEND_EMAIL", {"to": "mohansaiteja.99@gmail.com"}) is None


def test_misheard_address_is_read_back_before_anything_is_sent():
    args = {"to": "mohansaitesja.99@gmail.com"}
    with _said("my email is mohansaiteja.99@gmail.com"):
        held = recipient_guard.check("c1", "GMAIL_SEND_EMAIL", args)
        assert held["status"] == "needs_confirmation"
        assert "m o h a n s a i t e s j a dot 9 9, at gmail dot com" in held["message"]
        # Repeating it straight away, before the caller answers, is still held.
        assert recipient_guard.check("c1", "GMAIL_SEND_EMAIL", args)["status"] == "needs_confirmation"
    with _said("my email is mohansaiteja.99@gmail.com", "yes that's right"):
        assert recipient_guard.check("c1", "GMAIL_SEND_EMAIL", args) is None


def test_booking_invites_are_guarded_and_drafts_are_not():
    with _said("book me at 3"):
        assert recipient_guard.check("c1", "GOOGLECALENDAR_CREATE_EVENT", {"attendee_email": "x@y.com"})["status"] == "needs_confirmation"
        assert recipient_guard.check("c1", "GOOGLECALENDAR_CREATE_EVENT", {"summary": "no invite"}) is None
        assert recipient_guard.check("c1", "GMAIL_CREATE_DRAFT", {"to": "x@y.com"}) is None


def test_confirmation_is_per_call():
    with _said("hello"):
        recipient_guard.check("c1", "GMAIL_SEND_EMAIL", {"to": "a@b.com"})
    with _said("hello", "yes"):
        assert recipient_guard.check("c2", "GMAIL_SEND_EMAIL", {"to": "a@b.com"})["status"] == "needs_confirmation"


def test_spoken_words_are_not_accepted_as_an_email_address():
    from server.services.tool_schema_registry import validate_tool_arguments

    error = validate_tool_arguments("GMAIL_SEND_EMAIL", {"to": "mohan sai teja point nine nine at g mail", "subject": "Timings", "body": "Hi"})
    assert error and "spell it slowly" in error
    assert validate_tool_arguments("GMAIL_SEND_EMAIL", {"to": "mohansaiteja.99@gmail.com", "subject": "Timings", "body": "Hi"}) is None
    assert validate_tool_arguments("TWILIO_SMS_SEND_MESSAGE", {"to": "+919999000111", "body": "Our address is 12 MG Road"}) is None


def test_drafts_are_not_offered_during_a_call():
    from server.services.tool_schema_registry import POST_CALL_ONLY

    assert "GMAIL_CREATE_DRAFT" in POST_CALL_ONLY


def test_spoken_address_is_written_out_and_always_read_back():
    assert recipient_guard.written_address("mohan sai teja dot ninety nine at gmail dot com") == "mohansaiteja.99@gmail.com"
    assert recipient_guard.written_address("ravi underscore k at the rate yahoo dot co dot in") == "ravi_k@yahoo.co.in"
    assert recipient_guard.written_address("s i t a double seven at gmail dot com") == "sita77@gmail.com"
    assert recipient_guard.written_address("mohan at gmail") == ""  # not a whole address: the caller spells it
    args = {"to": "mohansaiteja.99@gmail.com"}
    with _said("my email is mohan sai teja dot ninety nine at gmail dot com"):
        assert recipient_guard.check("c1", "GMAIL_SEND_EMAIL", args, converted=True)["status"] == "needs_confirmation"
    with _said("my email is mohan sai teja dot ninety nine at gmail dot com", "yes"):
        assert recipient_guard.check("c1", "GMAIL_SEND_EMAIL", args, converted=True) is None
