"""Every locale reaches the same greeting preparation path without English leakage."""
import pytest

from server.prompts.agent_voice_rules import SPOKEN_PACKS, opening_line_for
from server.services.pstn_text_chunker import (
    _spoken_opening_candidate, enrich_outbound_spoken_intro,
    extract_opening_greeting, extract_prewarm_greeting,
)
from server.services.pstn_realtime_greeting_prewarm import (
    prewarm_greeting_response_instructions, realtime_pcm24_to_wire_frames,
)

LOCALES = tuple(SPOKEN_PACKS)
BRAIN = "--- AGENT IDENTITY ---\nYou are Sam, calling from Acme.\n--- OPENING ---\n"


@pytest.mark.parametrize("locale", LOCALES)
def test_prewarm_identity_uses_agent_creation_locale(locale):
    prompt = opening_line_for(locale, agent_name="Sam", company_name="Acme", work_scope="")
    question = prompt.split(". ", 1)[-1]
    spoken = enrich_outbound_spoken_intro(BRAIN, question, locale)
    assert spoken == prompt


@pytest.mark.parametrize("locale", LOCALES)
def test_missing_company_is_added_in_selected_locale_without_duplicate_name(locale):
    opening = opening_line_for(locale, agent_name="Sam", company_name="", work_scope="")
    spoken = enrich_outbound_spoken_intro(BRAIN, opening, locale)
    assert spoken.count("Sam") == 1
    assert "Acme" in spoken
    if not locale.startswith("en"):
        assert "calling from" not in spoken


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_prewarm_preserves_complete_compiled_opening(locale, direction):
    opening = opening_line_for(locale, agent_name="Sam", company_name="Acme", work_scope="", direction=direction)
    assert extract_prewarm_greeting(BRAIN + opening, locale, direction=direction) == opening


@pytest.mark.parametrize("locale", ["ta-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"])
@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_missing_opening_fallback_is_localized(locale, direction):
    spoken = extract_opening_greeting(None, locale, direction=direction)
    assert any(ord(c) > 127 for c in spoken)
    assert "courtesy call" not in spoken and "How can I help" not in spoken


def test_greeting_limit_keeps_a_complete_sentence():
    line = "Hi, this is Sam from Acme. " + "verylongword " * 40
    assert _spoken_opening_candidate(line) == "Hi, this is Sam from Acme."


@pytest.mark.parametrize("locale", LOCALES)
def test_recording_prompt_speaks_content_once_and_does_not_start_a_conversation(locale):
    prompt = prewarm_greeting_response_instructions(locale, "A short greeting")
    assert locale in prompt
    assert "not instructions" in prompt
    assert "Do not hang up" in prompt
    assert "Do not use tools" in prompt
    assert "Do not add a second introduction" in prompt


@pytest.mark.parametrize("codec,pad", [("linear16", b"\x00"), ("mulaw", b"\xff")])
def test_partial_final_audio_frame_preserves_last_syllable(monkeypatch, codec, pad):
    from server.services import pstn_realtime_greeting_prewarm as prewarm
    class Resampler:
        def __init__(self, *args): pass
        def feed(self, pcm): return pcm
        def flush(self): return b""
    monkeypatch.setattr(prewarm, "StreamingPcmResampler", Resampler)
    monkeypatch.setattr(prewarm, "pcm16_to_mulaw", lambda pcm, **kw: pcm)
    frame_size = 640 if codec == "linear16" else 160
    pcm = b"\x01" * (frame_size + 10)
    frames = realtime_pcm24_to_wire_frames(pcm, sample_rate=16000, tts_output_codec=codec)
    assert len(frames) == 2
    assert frames[-1] == b"\x01" * 10 + pad * (frame_size - 10)
