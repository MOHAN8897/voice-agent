"""Tests for PSTN text chunking and greeting extraction."""
from server.services.pstn_text_chunker import (
    drain_complete_sentences,
    extract_opening_greeting,
    resolve_stream_tts_tail,
)


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


def test_resolve_stream_tts_tail_skips_full_text_after_streaming():
    full = "First sentence. Second sentence."
    assert resolve_stream_tts_tail("", full, spoke_from_stream=True) is None


def test_resolve_stream_tts_tail_keeps_pending_remainder():
    assert resolve_stream_tts_tail(" trailing bit", "ignored", spoke_from_stream=True) == "trailing bit"


def test_resolve_stream_tts_tail_uses_full_text_when_no_stream_chunks():
    full = "Only done chunk."
    assert resolve_stream_tts_tail("", full, spoke_from_stream=False) == "Only done chunk."


def test_pstn_call_options_ignores_test_studio_session():
    from server.services.pstn_voice_core import pstn_call_options

    opts = pstn_call_options(
        {
            "source_session_id": "test-studio",
            "language": "te-IN",
            "stack_override": None,
        }
    )
    assert opts["tts_session_id"] is None
    assert opts["language"] == "te-IN"


def test_pstn_call_options_keeps_custom_source_session():
    from server.services.pstn_voice_core import pstn_call_options

    opts = pstn_call_options({"source_session_id": "campaign-42"})
    assert opts["tts_session_id"] == "campaign-42"
