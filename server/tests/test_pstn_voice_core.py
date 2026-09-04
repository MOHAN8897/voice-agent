"""Tests for PSTN text chunking and greeting extraction."""
from server.services.pstn_text_chunker import drain_complete_sentences, extract_opening_greeting


def test_drain_complete_sentences():
    sents, rem = drain_complete_sentences("Hello there. How are you")
    assert sents == ["Hello there."]
    assert rem == "How are you"


def test_drain_long_clause_without_punctuation():
    sents, rem = drain_complete_sentences("a" * 80)
    assert len(sents) == 1
    assert rem == ""


def test_extract_opening_greeting_from_brain():
    brain = "--- OPENING ---\nనమస్కారం! నేను మీ సహాయకుడు.\n--- VOICE STYLE ---"
    assert "నమస్కారం" in (extract_opening_greeting(brain) or "")


def test_default_greeting():
    assert extract_opening_greeting(None, "te-IN")
