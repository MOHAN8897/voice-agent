"""Regression tests for sustained speech duration barge-in gating and onset preservation."""
from __future__ import annotations

import struct
from unittest.mock import AsyncMock
import pytest

from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import (
    REALTIME_AEC_ENERGY_MIN,
    REALTIME_AEC_LOUD_OPEN_FRAMES,
    REALTIME_AEC_MIN_SPEECH_MS,
    PstnRealtimeVoiceLoop,
)


@pytest.mark.asyncio
async def test_short_transient_noise_does_not_barge():
    """Impulsive noise (e.g. 1-2 frames / 20-40ms) must NOT interrupt agent speech."""
    barged: list[int] = []

    async def on_barge() -> None:
        barged.append(1)

    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-noise-gate",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_barge_handler(on_barge)
    await loop.start_call(play_greeting=False)
    loop._set_tts_active(True)

    # 1 frame @ 16kHz: 320 samples (640 bytes) = 20ms of loud noise (e.g. click, breath)
    loud = struct.pack("<" + "h" * 320, *([2500] * 320))
    await loop.feed_user_pcm16(loud)
    # A single 20ms transient must not open the barge gate
    assert barged == [], "Single 20ms noise transient must not trigger barge"
    assert loop._aec_barge_open is False
    assert adapter.cancelled == 0
    assert len(loop._barge_pre_buffer) == 1

    # Send a second frame (now 40ms, still below REALTIME_AEC_MIN_SPEECH_MS = 80ms)
    await loop.feed_user_pcm16(loud)
    assert barged == [], "40ms noise transient must not trigger barge"
    assert loop._aec_barge_open is False
    assert adapter.cancelled == 0

    # Noise stops -> quiet frame arrives
    quiet = b"\x00\x00" * 320
    await loop.feed_user_pcm16(quiet)
    assert loop._aec_loud_streak == 0
    assert loop._barge_speech_ms == 0.0
    assert len(loop._barge_pre_buffer) == 0
    assert barged == []

    await loop.close()


@pytest.mark.asyncio
async def test_sustained_speech_commits_barge_and_flushes_prebuffer():
    """Sustained speech (>= 80ms) commits barge-in and flushes held audio onset."""
    barged: list[int] = []

    async def on_barge() -> None:
        barged.append(1)

    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-speech-barge",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_barge_handler(on_barge)
    await loop.start_call(play_greeting=False)
    loop._set_tts_active(True)
    loop.current_generation_id = "gen-1"

    loud = struct.pack("<" + "h" * 320, *([2500] * 320))

    # Feed sustained speech frames up to REALTIME_AEC_LOUD_OPEN_FRAMES (4 frames = 80ms)
    for _ in range(REALTIME_AEC_LOUD_OPEN_FRAMES):
        await loop.feed_user_pcm16(loud)

    assert barged == [1], "Sustained speech must trigger barge exactly once"
    assert loop._aec_barge_open is True
    assert adapter.cancelled >= 1
    # Check that pre-buffered audio onset was flushed to adapter so first word is preserved
    assert len(adapter.appended) >= REALTIME_AEC_LOUD_OPEN_FRAMES

    await loop.close()


def test_gemini_start_sensitivity_valid_enums():
    """Verify that Gemini Live start sensitivity mappings only use valid Google GenAI enums."""
    from google.genai import types
    from server.realtime.providers.gemini_voice import _EAGERNESS_TO_START

    valid_google_sensitivities = {
        types.StartSensitivity.START_SENSITIVITY_HIGH,
        types.StartSensitivity.START_SENSITIVITY_LOW,
        types.StartSensitivity.START_SENSITIVITY_UNSPECIFIED,
    }
    for key, mapped_val in _EAGERNESS_TO_START.items():
        assert mapped_val in valid_google_sensitivities, f"Mapping {key} -> {mapped_val} is not a valid Google enum"

    assert _EAGERNESS_TO_START["low"] == "START_SENSITIVITY_LOW"
    assert _EAGERNESS_TO_START["medium"] == "START_SENSITIVITY_LOW"
    assert _EAGERNESS_TO_START["auto"] == "START_SENSITIVITY_LOW"
    assert _EAGERNESS_TO_START["high"] == "START_SENSITIVITY_HIGH"


@pytest.mark.asyncio
async def test_provider_interrupted_once_per_generation():
    """Provider interrupted event should not trigger multiple carrier clear events on the same generation."""
    clears: list[int] = []

    async def on_barge() -> None:
        clears.append(1)

    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-provider-interrupted",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_barge_handler(on_barge)
    await loop.start_call(play_greeting=False)
    loop.current_generation_id = "gen-abc"

    # Simulate provider_interrupted arriving from Gemini Live
    await loop._handle_event({"type": "response_done", "provider_interrupted": True})
    assert clears == [1]

    # Second provider_interrupted on same generation
    await loop._handle_event({"type": "response_done", "provider_interrupted": True})
    assert clears == [1], "Second provider_interrupted must not trigger redundant clearAudio"

    await loop.close()


@pytest.mark.asyncio
async def test_impulsive_cracker_noise_rejected_by_crest_factor():
    """Cracker pops and mic thumps have high peak / RMS (C > 4.5) and must NOT trip the barge gate."""
    from server.services.audio_transcode import pcm16_crest_factor, pcm16_rms

    barged: list[int] = []

    async def on_barge() -> None:
        barged.append(1)

    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-cracker-gate",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_barge_handler(on_barge)
    await loop.start_call(play_greeting=False)
    loop._set_tts_active(True)
    loop.current_generation_id = "gen-cracker"

    # Construct an impulsive frame: single 25,000 peak with 2,000 background (320 samples)
    # RMS ~ 2,437 (> 1600), Peak = 25,000 -> Crest factor ~ 10.25 (> 4.5)
    samples = [25000] + [2000] * 319
    cracker_frame = struct.pack("<" + "h" * 320, *samples)

    rms = pcm16_rms(cracker_frame)
    crest = pcm16_crest_factor(cracker_frame, rms)
    assert rms >= REALTIME_AEC_ENERGY_MIN, f"RMS {rms} must exceed threshold to test crest factor"
    assert crest > 4.5, f"Crest factor {crest} must exceed 4.5"

    # Feed cracker noise frames repeatedly (e.g. 15 frames)
    for _ in range(15):
        await loop.feed_user_pcm16(cracker_frame)

    assert barged == [], "Cracker noise with C > 4.5 must NEVER trigger barge-in"
    assert loop._aec_barge_open is False
    assert adapter.cancelled == 0
    await loop.close()


@pytest.mark.asyncio
async def test_cough_burst_under_240ms_rejected_by_syllabic_gate():
    """Coughs and throat clears lasting < 240ms must be absorbed without interrupting agent speech."""
    barged: list[int] = []

    async def on_barge() -> None:
        barged.append(1)

    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="c-cough-gate",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_barge_handler(on_barge)
    await loop.start_call(play_greeting=False)
    loop._set_tts_active(True)
    loop.current_generation_id = "gen-cough"

    loud = struct.pack("<" + "h" * 320, *([2200] * 320))

    # Feed 8 frames of 20ms = 160ms (typical cough duration, below 240ms minimum)
    for _ in range(8):
        await loop.feed_user_pcm16(loud)

    assert barged == [], "160ms cough burst must not trigger barge"
    assert loop._aec_barge_open is False
    assert adapter.cancelled == 0

    # Cough finishes -> caller goes quiet
    quiet = b"\x00\x00" * 320
    for _ in range(4):
        await loop.feed_user_pcm16(quiet)

    assert barged == [], "After cough ends, agent speech must remain completely uninterrupted"
    assert loop._aec_loud_streak == 0
    assert len(loop._barge_pre_buffer) == 0
    await loop.close()
