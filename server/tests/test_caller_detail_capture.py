"""Deterministic caller detail capture for working memory."""
from server.call.caller_detail_capture import (
    caller_detail_memory_operations,
    extract_caller_email,
    extract_caller_name,
    extract_caller_phone,
)


def test_extracts_indian_mobile_with_cue():
    assert extract_caller_phone("my phone number is 8897908470") == "8897908470"
    assert extract_caller_phone("please record +91 88979 08470") == "8897908470"


def test_extracts_indian_mobile_bare():
    assert extract_caller_phone("8897908470") == "8897908470"


def test_ignores_non_mobile_without_cue():
    assert extract_caller_phone("the price is 5000000000") is None


def test_extracts_email_and_name():
    assert extract_caller_email("email me at arun.test@example.com please") == "arun.test@example.com"
    assert extract_caller_name("Hi, my name is Arun") == "Arun"
    assert extract_caller_name("Hi, my name is the recording") is None
    assert extract_caller_name("my name is looking") is None


def test_rejects_outbound_did_as_lead_phone():
    from server.call.caller_detail_capture import is_usable_lead_phone, unclear_name_phrase

    assert is_usable_lead_phone("+13526146416") is False
    assert is_usable_lead_phone("8897908470") is True
    assert unclear_name_phrase("Hi, my name is the recording") is True
    assert unclear_name_phrase("I am busy, contact me tomorrow") is False


def test_memory_ops_include_phone_and_context():
    ops = caller_detail_memory_operations("Can you record my phone number 8897908470")
    keys = {op.get("key") for op in ops if op.get("op") == "set_fact"}
    assert "callback_phone" in keys
    assert "phone" in keys
    assert any(op.get("op") == "append_context" for op in ops)
