"""Tests for PSTN text chunking and greeting extraction."""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from server.services.pstn_text_chunker import (
    drain_complete_sentences,
    extract_opening_greeting,
    join_speakable_chunks,
    resolve_stream_tts_tail,
)


def test_drain_complete_sentences():
    sents, rem = drain_complete_sentences("Hello there friend. How are you")
    assert sents == ["Hello there friend."]
    assert rem == "How are you"


def test_join_speakable_chunks_makes_one_utterance():
    sents, rem = drain_complete_sentences("Hello there friend. How are you today?")
    assert rem == ""
    assert join_speakable_chunks(sents) == "Hello there friend. How are you today?"


def test_drain_holds_unpunctuated_text_until_sentence_or_cap():
    text = "a" * 80
    sents, rem = drain_complete_sentences(text)
    assert sents == []
    assert rem == text


def test_drain_does_not_split_on_comma_clauses():
    text = "This is a longer clause without period, and more text here"
    sents, rem = drain_complete_sentences(text)
    assert sents == []
    assert rem == text


def test_first_chunk_waits_for_a_prosody_boundary():
    text = "Sure I can help you with that property today"
    sents, rem = drain_complete_sentences(text, allow_first_fast=True)
    assert sents == []
    assert rem == text


def test_first_fast_chunk_waits_for_complete_phrase():
    sents, rem = drain_complete_sentences("Hello, good to", allow_first_fast=True)
    assert sents == []
    assert rem == "Hello, good to"

    sents, rem = drain_complete_sentences(
        "Hello, good to speak with you today",
        allow_first_fast=True,
    )
    assert sents == []
    assert rem == "Hello, good to speak with you today"


def test_realtime_delta_boundaries_are_not_tts_boundaries():
    pending = ""
    spoken = []
    for delta in ("We currently offer", " periodic car", " service plans."):
        pending += delta
        ready, pending = drain_complete_sentences(pending, allow_first_fast=True)
        spoken.extend(ready)

    assert spoken == ["We currently offer periodic car service plans."]
    assert pending == ""


def test_drain_force_flush_only_at_reply_ceiling():
    text = "word " * 60  # unpunctuated, above FORCE_FLUSH_AT (280)
    sents, rem = drain_complete_sentences(text)
    assert sents
    assert all(len(s) >= 14 for s in sents)


def test_extract_opening_greeting_from_brain():
    brain = "--- OPENING ---\nనమస్కారం! నేను మీ సహాయకుడు.\n--- VOICE STYLE ---"
    assert "నమస్కారం" in (extract_opening_greeting(brain) or "")


def test_default_greeting():
    assert extract_opening_greeting(None, "te-IN")


def test_extract_opening_greeting_skips_policy_lines():
    """OPENING section mixes example line + instructions — speak only the example."""
    brain = (
        "--- OPENING ---\n"
        "Example opening: Hi, this is Priya calling from Acme. How can I help you today?\n"
        "ONE spoken reply per turn — never paste a greeting then restart with a second greeting.\n"
        "If you speak first (PSTN/outbound connect): say that opening once (intro + offer help).\n"
        "--- WORK SCOPE ---\n"
    )
    greet = extract_opening_greeting(brain, "en-IN") or ""
    assert greet.startswith("Hi, this is Priya")
    assert "Example opening" not in greet
    assert "ONE spoken" not in greet
    assert "never paste" not in greet


def test_extract_opening_greeting_single_utterance_only():
    brain = (
        "--- OPENING ---\n"
        "Hi, this is Priya from Acme Homes. How can I help you today?\n"
        "May I know your name please?\n"
        "What budget are you looking at?\n"
        "--- WORK SCOPE ---\n"
    )
    greet = extract_opening_greeting(brain, "en-IN") or ""
    assert "Priya" in greet
    assert "name" not in greet.lower()
    assert "budget" not in greet.lower()


def test_resolve_stream_tts_tail_skips_full_text_after_streaming():
    full = "First sentence. Second sentence."
    assert resolve_stream_tts_tail("", full, spoke_from_stream=True) is None


def test_resolve_stream_tts_tail_keeps_pending_remainder():
    assert resolve_stream_tts_tail(" trailing bit", "ignored", spoke_from_stream=True) == "trailing bit"


def test_resolve_stream_tts_tail_uses_full_text_when_no_stream_chunks():
    full = "Only done chunk."
    assert resolve_stream_tts_tail("", full, spoke_from_stream=False) == "Only done chunk."


def test_extract_opening_greeting_from_opening_line_te():
    brain = (
        "AGENT IDENTITY\nPriya\nOPENING\n"
        'opening_line_te: "Namaste! Broski Company nundi, nenu Priya matladutunnanu."\n'
        "VOICE STYLE\n"
    )
    greet = extract_opening_greeting(brain, "te-IN")
    assert greet and "Broski" in greet
    assert "opening_line" not in (greet or "").lower()

@pytest.mark.asyncio
async def test_tts_text_pacing_aborts_when_generation_is_cancelled():
    from server.services.pstn_voice_core import PstnVoiceLoop

    session = AsyncMock()
    voice = PstnVoiceLoop(session_id="pace", call_id=None, on_agent_wire=AsyncMock())
    voice.playback = SimpleNamespace(wait_for_capacity=AsyncMock(return_value=False))
    await voice._send_tts_text(session, "Hello there friend.")
    session.send_text.assert_not_awaited()


def test_pstn_call_options_uses_test_studio_when_source_set():
    from server.services.pstn_voice_core import pstn_call_options

    opts = pstn_call_options(
        {
            "source_session_id": "test-studio",
            "language": "te-IN",
            "stack_override": None,
        }
    )
    assert opts["tts_session_id"] == "test-studio"
    assert opts["config_session_id"] == "test-studio"
    assert opts["language"] == "te-IN"


def test_pstn_call_options_inherit_defaults_test_studio():
    from server.services.pstn_voice_core import pstn_call_options

    opts = pstn_call_options({"inherit_test_studio_config": True, "language": "te-IN"})
    assert opts["config_session_id"] == "test-studio"


def test_pstn_call_options_tier_only_has_no_session():
    from server.services.pstn_voice_core import pstn_call_options

    opts = pstn_call_options({"language": "te-IN", "stack_override": None})
    assert opts["tts_session_id"] is None
    assert opts.get("config_session_id") is None


def test_pstn_call_options_keeps_custom_source_session():
    from server.services.pstn_voice_core import pstn_call_options

    opts = pstn_call_options({"source_session_id": "campaign-42"})
    assert opts["tts_session_id"] == "campaign-42"


def test_pstn_turn_runtime_reads_config_session():
    from server.services.pstn_voice_core import pstn_turn_runtime
    from server.services.runtime_settings import runtime_settings

    runtime_settings.update(
        "test-studio-llm",
        {"openaiTemperature": 0.42, "openaiModel": "gpt-5.6-luna", "openaiMaxTokens": 180},
    )
    kw = pstn_turn_runtime("test-studio-llm", "pstn-telnyx-xyz")
    assert kw["temperature"] == 0.42
    assert kw["openai_model"] == "gpt-5.6-luna"
    assert kw["max_output_tokens"] == 180
    runtime_settings.clear("test-studio-llm")
