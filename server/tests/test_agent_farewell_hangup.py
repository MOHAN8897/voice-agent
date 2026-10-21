"""Agent-initiated closing on primary Gemini PSTN calls; no live carrier calls."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from server.call.end_call_validate import validate_end_call
from server.call.hangup_judge import agent_spoke_terminal_farewell
from server.prompts.agent_voice_rules import CALL_END_FAREWELLS
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.mark.parametrize("spoken", [
    "Goodbye.", "The details are confirmed. Have a nice day!",
    "Thanks for speaking with me. Have a great evening, sir.",
    "Bye, take care.", "Have a nice day, సార్.", "Bye for now.", "Have a good one!",
    "సరేనండి. ఉంటానండి.", "మళ్లీ మాట్లాడుకుందాం.",
    "మీ రోజు శుభంగా ఉండాలి.", "आपका दिन शुभ हो।", "अलविदा।",
    "உங்கள் நாள் இனிதாக அமையட்டும்.", "விடைபெறுகிறேன்.",
    "ನಿಮ್ಮ ದಿನ ಶುಭವಾಗಲಿ.", "ಮತ್ತೆ ಮಾತನಾಡೋಣ.",
    *CALL_END_FAREWELLS.values(),
])
def test_explicit_agent_closing_phrases(spoken):
    assert agent_spoke_terminal_farewell(spoken)


@pytest.mark.parametrize("spoken", [
    "Thanks.", "Thank you.", "You're welcome.", "ధన్యవాదాలు.",
    "नमस्कार।", "வணக்கம்.", "ನಮಸ್ಕಾರ.",
    "Have a nice day. What time works for you?",
    "Before I let you go, may I have your name? Goodbye.",
    'The phrase is "Have a nice day."', "You can say goodbye.",
    "I will not say goodbye.", "Goodbye is an English farewell.",
])
def test_conversation_and_examples_are_not_terminal_farewells(spoken):
    assert not agent_spoke_terminal_farewell(spoken)


def test_primary_closing_does_not_require_caller_goodbye_even_after_a_question():
    decision = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Have a nice day."},
        user_text="What is the appointment time?", spoken_text="Your appointment is at 4 PM. Have a nice day.",
        tool_sourced=True, agent_farewell_ends_call=True,
    )
    assert decision.accepted


@pytest.mark.parametrize("extra, code", [
    ({"allowed_reasons": frozenset({"goodbye"})}, "policy_overlay"),
    ({"barge_in_flight": True}, "barge_in_flight"),
    ({"call_status": "complete"}, "call_not_active"),
])
def test_agent_closing_keeps_policy_and_active_call_guards(extra, code):
    decision = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Have a nice day."},
        user_text="The appointment time works", spoken_text="Have a nice day.",
        tool_sourced=True, agent_farewell_ends_call=True, **extra,
    )
    assert not decision.accepted
    assert decision.reject_code == code


def test_new_closing_evidence_is_opt_in():
    decision = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text="What time?", spoken_text="At 4 PM. Goodbye.", tool_sourced=True,
    )
    assert not decision.accepted


@pytest.fixture
async def loop():
    adapter = FakeRealtimeVoiceAdapter()
    voice = PstnRealtimeVoiceLoop(
        session_id="agent-farewell", call_id=None, adapter=adapter,
        sample_rate=16000, tts_output_codec="linear16", on_agent_wire=AsyncMock(),
        stack_override={"pipeline": "realtime_voice", "language": "en-IN",
                        "llm": {"provider": "gemini", "model": "gemini-3.8-live"}},
    )
    voice._live_model = "gemini-3.8-live"
    voice._user_partial = voice._last_user_final_text = "What is the appointment time?"
    voice._on_remote_hangup = AsyncMock()
    voice._background_after_fast_hangup = AsyncMock()
    yield voice
    await voice.close()
    voice._cancel_hangup_force_task()
    if voice._background_hangup_task:
        await voice._background_hangup_task


@pytest.mark.asyncio
async def test_completed_agent_farewell_waits_for_playback_then_disconnects_once(loop):
    playing = {"on": True}
    checked = asyncio.Event()
    def is_playing():
        checked.set()
        return playing["on"]
    loop._farewell_still_on_the_line = is_playing
    loop._assistant_text = "Your appointment is at 4 PM. Have a nice day."
    loop._response_had_audio = True
    done = asyncio.create_task(loop._handle_event({"type": "response_done"}))
    try:
        await asyncio.wait_for(checked.wait(), timeout=2)
        assert loop._pending_end_call["reason"] == "goal_complete"
        loop._on_remote_hangup.assert_not_awaited()
        playing["on"] = False
        await asyncio.wait_for(done, timeout=2)
        loop._on_remote_hangup.assert_awaited_once()
        assert loop._closed
        assert not loop._adapter.started_responses  # No repeated goodbye.
        await loop._handle_event({"type": "response_done"})
        loop._on_remote_hangup.assert_awaited_once()
    finally:
        done.cancel()
        await asyncio.gather(done, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["no_audio", "caller_speaking", "interrupted", "browser"])
async def test_incomplete_or_non_pstn_closing_does_not_arm_new_fallback(loop, scenario):
    loop._assistant_text = "Your appointment is at 4 PM. Have a nice day."
    loop._response_had_audio = scenario != "no_audio"
    loop._caller_speaking = scenario == "caller_speaking"
    loop.channel = "browser" if scenario == "browser" else "pstn"
    await loop._maybe_hangup_missed_end_call(response_complete=scenario != "interrupted")
    assert loop._pending_end_call is None
    loop._on_remote_hangup.assert_not_awaited()


@pytest.mark.asyncio
async def test_interrupted_provider_response_does_not_disconnect(loop):
    loop._assistant_text = "Your appointment is at 4 PM. Have a nice day."
    loop._response_had_audio = True
    await loop._handle_event({"type": "response_done", "provider_interrupted": True})
    assert not loop._pending_end_call
    loop._on_remote_hangup.assert_not_awaited()


@pytest.mark.asyncio
async def test_caller_barge_in_during_final_playback_cancels_disconnect(loop):
    playing = {"on": True}
    checked = asyncio.Event()
    def is_playing():
        checked.set()
        return playing["on"]
    loop._farewell_still_on_the_line = is_playing
    loop._assistant_text = "Your appointment is at 4 PM. Goodbye."
    loop._response_had_audio = True
    done = asyncio.create_task(loop._handle_event({"type": "response_done"}))
    try:
        await asyncio.wait_for(checked.wait(), timeout=2)
        loop._aec_barge_open = True
        await loop._commit_local_barge()
        playing["on"] = False
        await asyncio.wait_for(done, timeout=2)
        loop._on_remote_hangup.assert_not_awaited()
        assert not loop._hangup_started
        assert not loop._pending_end_call
    finally:
        done.cancel()
        await asyncio.gather(done, return_exceptions=True)
