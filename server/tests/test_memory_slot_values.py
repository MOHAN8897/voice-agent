"""Memory slots hold the kind of value their name promises; explicit counts and names are captured."""
from __future__ import annotations

import pytest

from server.call.caller_detail_capture import (
    caller_detail_memory_operations,
    extract_caller_name,
    extract_explicit_name,
    extract_requested_quantity,
)
from server.call.memory_guard import has_number, slot_value_error
from server.call.memory_manager import memory_manager


@pytest.fixture
def call(monkeypatch, tmp_path):
    from server.config.env import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    memory_manager.reset_for_tests()
    memory_manager.init("slot-call")
    yield "slot-call"
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.parametrize("value", [
    "500", "100 visiting cards", "౫౦౦", "ఐదు వందలు", "ఐదువందలు", "five hundred", "a dozen", "दो सौ", "पाँच",
    "நூறு", "ಎರಡು", "നൂറ്", "पाच", "একশো", "સો", "ਸੌ", "ఫైవ్ హండ్రెడ్",
])
def test_a_quantity_needs_a_number_in_any_supported_language(value):
    assert has_number(value)
    assert slot_value_error("quantity", value) is None


@pytest.mark.parametrize("key, value", [
    ("quantity", "బల్క్"), ("quantity", "bulk"), ("quantity", "ఒక బల్క్"), ("qty", "थोक में"),
    ("number_of_guests", "many"), ("card_count", "కొన్ని"),
    ("caller_name", "ఓకే"), ("caller_name", "हाँ जी"), ("caller_name", "the recording"),
    ("caller_name", "call me 9876543210"), ("name", "can you tell me the price?"),
    ("callback_phone", "tomorrow"), ("email", "yes"),
])
def test_values_that_do_not_fit_the_slot_are_rejected(key, value):
    assert slot_value_error(key, value) is not None


@pytest.mark.parametrize("key, value", [
    ("caller_name", "Saikiran"), ("caller_name", "రాము"), ("caller_name", "Sai Kiran"),
    ("callback_phone", "8897908470"), ("email", "a@b.co"), ("email", "ravi at gmail dot com"),
    ("product", "బల్క్"), ("delivery_address", "ఇంటి నంబర్ 4, విజయవాడ"), ("budget", "not decided"),
])
def test_values_that_fit_or_free_form_slots_are_kept(key, value):
    assert slot_value_error(key, value) is None


def test_memory_write_rejects_bulk_as_a_quantity(call):
    result = memory_manager.apply_proposals(
        call, [{"op": "set_fact", "key": "quantity", "value": "బల్క్"},
               {"op": "set_fact", "key": "caller_name", "value": "Saikiran"}], turn_seq=16)
    assert result["snapshot"]["facts"] == {"caller_name": "Saikiran"}
    assert result["event"]["validation_errors"] == ["not_a_number: quantity"]
    later = memory_manager.apply_proposals(call, [{"op": "set_fact", "key": "quantity", "value": "500"}], turn_seq=40)
    assert later["snapshot"]["facts"]["quantity"] == "500"


def test_an_operator_correction_is_trusted(call):
    result = memory_manager.manual_correction(
        call, [{"op": "set_fact", "key": "quantity", "value": "bulk order"}], actor="ops", reason="test")
    assert result["snapshot"]["facts"]["quantity"] == "bulk order"


@pytest.mark.parametrize("text, expected", [
    ("ఓకే నాకు ఒక 100 విజిటింగ్ కార్స్ కావాలి. ఇది చెప్పండి, మీ మేనేజర్ కి చెప్పండి. నా పేరు Saikiran", "100"),
    ("ఒక 500 కావాలి. ఫైవ్ హండ్రెడ్", "500"),
    ("100 కాదు, 300 కావాలి", "300"),
    ("मुझे 250 कार्ड चाहिए", "250"),
    ("எனக்கு 40 cards வேணும்", "40"),
    ("I need 1,000 cards", "1000"),
    ("ನನಗೆ 60 ಬೇಕು", "60"),
])
def test_a_stated_quantity_is_captured(text, expected):
    assert extract_requested_quantity(text) == expected


@pytest.mark.parametrize("text", [
    "the price is ₹25 I want to know", "call me at 5 pm, I need that", "I need 2 minutes",
    "నాకు 10:30 కి కావాలి", "my number is 9876543210 I want a callback", "రేపు 6 గంటలకు కావాలి",
    "I have 100 questions",
])
def test_prices_times_durations_and_phones_are_not_quantities(text):
    assert extract_requested_quantity(text) is None


def test_a_bare_number_is_a_quantity_only_after_the_agent_asked_how_many():
    assert extract_requested_quantity("500") is None
    assert extract_requested_quantity("500", quantity_asked=True) == "500"
    ops = caller_detail_memory_operations("ఒక 500 కావాలి")
    assert ops == [{"op": "set_fact", "key": "quantity", "value": "500"}]


def test_names_in_more_languages_and_explicit_latin_names():
    assert extract_caller_name("என் பெயர் ராஜா") == "ராஜா"
    assert extract_caller_name("আমার নাম রাহুল") == "রাহুল"
    assert extract_explicit_name("నా పేరు Saikiran") == "Saikiran"
    assert extract_explicit_name("मेरा नाम Rahul Sharma है") == "Rahul Sharma"
    # A refusal in the local script, or "not ...", is never captured.
    assert extract_explicit_name("నా పేరు చెప్పను") is None
    assert extract_explicit_name("my name is not important") is None
    assert extract_explicit_name("my name is private") is None
