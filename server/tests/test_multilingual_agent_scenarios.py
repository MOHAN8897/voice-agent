"""Deterministic caller intent, callback, prompt, and disconnect checks for core locales."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from server.agent.brain_prompt_composer import compose_brain_prompt
from server.call.end_call_validate import caller_requested_callback, validate_end_call
from server.prompts.agent_voice_rules import LANGUAGE_LOCK


SCENARIOS = (
    (
        "te-IN",
        "దీని ధర ఎంత?",
        "రేపు మళ్లీ కాల్ చేయండి",
        "నాకు ఇంట్రెస్ట్ లేదు",
    ),
    (
        "hi-IN",
        "इसकी कीमत क्या है?",
        "कल फिर से कॉल कीजिए",
        "मुझे दिलचस्पी नहीं है",
    ),
    (
        "ta-IN",
        "இதன் விலை என்ன?",
        "நாளை மீண்டும் அழைக்கவும்",
        "எனக்கு விருப்பமில்லை",
    ),
    (
        "en-IN",
        "What is the price?",
        "Call me again tomorrow.",
        "I'm not interested.",
    ),
)


@pytest.mark.parametrize("language,question,_,__", SCENARIOS)
def test_real_questions_keep_the_call_open(language, question, _, __):
    decision = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text=question,
        language=language,
        completed_turns=2,
        tool_sourced=True,
    )

    assert decision.accepted is False
    assert decision.reject_code == "user_asked_question"


@pytest.mark.parametrize("language,_,callback,__", SCENARIOS)
def test_callback_waits_for_required_details(language, _, callback, __):
    assert caller_requested_callback(callback) is True

    decision = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text=callback,
        language=language,
        callback_close_phase="collecting_name",
        completed_turns=2,
        tool_sourced=True,
    )

    assert decision.accepted is False
    assert decision.reject_code == "lead_details_missing"


@pytest.mark.asyncio
@pytest.mark.parametrize("language,_,__,refusal", SCENARIOS)
async def test_refusal_transcript_arms_backup_and_keeps_farewell_pending(language, _, __, refusal):
    from server.realtime.testing import FakeRealtimeVoiceAdapter
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

    loop = PstnRealtimeVoiceLoop(
        session_id=f"scenario-{language}",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=FakeRealtimeVoiceAdapter(),
        stack_override={"pipeline": "realtime_voice", "language": language},
    )
    await loop._handle_event({"type": "user_transcript", "text": refusal, "final": True})

    assert loop._pending_end_call is not None
    assert loop._pending_end_call["reason"] == "firm_refusal"
    assert loop._hangup_arm_source == "backup"
    assert loop._farewell_response_active is True
    assert loop._farewell_complete is False
    assert loop._hangup_started is False
    assert loop._closed is False


@pytest.mark.parametrize("language,_,__,___", SCENARIOS)
def test_compiled_brain_keeps_language_lock_and_shared_hangup_policy(language, _, __, ___):
    prompt = compose_brain_prompt(language=language)

    assert LANGUAGE_LOCK[language] in prompt
    assert "request_end_call" in prompt or "end_call" in prompt
    if language == "ta-IN":
        assert "விருப்பமில்லை" in prompt
        assert "நாளை மீண்டும் அழைக்கவும்" in prompt
