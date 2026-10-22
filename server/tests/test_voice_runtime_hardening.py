"""Language consistency and missed input-turn boundaries without paid calls."""
from __future__ import annotations

import struct
from unittest.mock import AsyncMock

import pytest
from google.genai import types

from server.brain.agent_script_compiler import _opening_line_is_language_compatible
from server.brain.compiled_brain_artifact import assemble_unified_brain
from server.prompts.agent_voice_rules import LANGUAGE_LOCK, live_realtime_output_rules
from server.realtime.audio_activity import InputAudioActivity
from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter


@pytest.mark.parametrize("language", tuple(LANGUAGE_LOCK))
def test_locale_register_survives_gemini_render(language):
    brain = assemble_unified_brain(language=language, script="--- COMPANY & OFFER ---\nRepair service; inspection costs 500 rupees.")
    rendered = build_gemini_audio_session_instructions(brain, language=language, direction="inbound")
    assert rendered.count(LANGUAGE_LOCK[language]) == 1
    assert "Repair service" in rendered
    assert "SPOKEN GRAMMAR" in rendered
    if not language.startswith("en-"):
        assert "Use natural local number phrasing" in rendered
        assert "English cardinal words + unit" not in live_realtime_output_rules(language)
    assert "natural phone salesperson" not in live_realtime_output_rules(language)


@pytest.mark.parametrize("language,wrong", [("hi-IN", "నమస్కారం"), ("ta-IN", "ನಮಸ್ಕಾರ"), ("te-IN", "नमस्ते")])
def test_generated_greeting_rejects_unrelated_indic_script(language, wrong):
    assert not _opening_line_is_language_compatible(f"Priya {wrong}", language)


def test_long_speech_is_not_finalized_by_elapsed_time_or_short_pause():
    activity = InputAudioActivity()
    speech = struct.pack("<h", 1600) * 320
    quiet = bytes(640)
    starts = 0
    for tick in range(3000):  # one minute, with continuous input
        now = tick * .02
        starts += activity.feed(speech, sample_rate=16000, now=now)
        assert not activity.should_finalize(now)
    assert starts == 1
    for tick in range(40):
        activity.feed(quiet, sample_rate=16000, now=60 + tick * .02)
    assert not activity.should_finalize(60.8)
    for tick in range(60):
        activity.feed(quiet, sample_rate=16000, now=60.8 + tick * .02)
    assert activity.should_finalize(62)


@pytest.mark.asyncio
async def test_missed_native_turn_end_flushes_once_and_resumes(monkeypatch):
    adapter = GeminiLiveVoiceAdapter(api_key="unit-test")
    adapter._session = AsyncMock()
    clock = [10.0]
    monkeypatch.setattr("server.realtime.providers.gemini_voice.time.monotonic", lambda: clock[0])
    speech = struct.pack("<h", 1600) * 480
    for _ in range(12):
        clock[0] += .02
        await adapter.append_pcm16(speech)
    assert await adapter.maybe_finalize_input(clock[0] + 2)
    assert not await adapter.maybe_finalize_input(clock[0] + 20)
    ends = [c for c in adapter._session.send_realtime_input.await_args_list if c.kwargs.get("audio_stream_end")]
    assert len(ends) == 1
    adapter._session.send_client_content.assert_not_awaited()
    for _ in range(12):
        clock[0] += .02
        await adapter.append_pcm16(speech)
    assert await adapter.maybe_finalize_input(clock[0] + 2)


@pytest.mark.asyncio
async def test_provider_response_prevents_duplicate_local_finalization():
    adapter = GeminiLiveVoiceAdapter(api_key="unit-test")
    adapter._session = AsyncMock()
    adapter._sent_realtime_audio = True
    adapter._input_activity.feed(struct.pack("<h", 1600) * 4000, sample_rate=16000, now=1)
    adapter._normalize(types.LiveServerMessage(server_content=types.LiveServerContent(
        model_turn=types.Content(parts=[types.Part(inline_data=types.Blob(data=b"12", mime_type="audio/pcm;rate=24000"))])
    )))
    assert not await adapter.maybe_finalize_input(20)
    adapter._session.send_realtime_input.assert_not_awaited()
