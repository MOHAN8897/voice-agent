"""Pass 3 hangup contract — TEST 1–5 from TELNYX_PSTN_FULL_FLOW_AUDIT.md."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from server.call.end_call_validate import caller_backup_end_intent, caller_firm_refusal, validate_end_call
from server.call.call_controller import CallState
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


TELUGU_NO_CALL = "కాల్ అవసరం లేదు"
TELUGU_INCIDENT = "నాకైతే ప్రస్తుతానికి ఏం కాల్ అవసరం లేదు."
HINDI_NO_NEED = "मुझे इसकी जरूरत नहीं है"


def _loop() -> PstnRealtimeVoiceLoop:
    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "language": "te-IN"},
    )
    loop._adapter = adapter
    return loop


def test_backup_golden_telugu_and_hindi():
    assert caller_backup_end_intent(TELUGU_NO_CALL)
    assert caller_backup_end_intent(TELUGU_INCIDENT)
    assert caller_firm_refusal(TELUGU_NO_CALL)
    assert caller_backup_end_intent(HINDI_NO_NEED)
    assert not caller_backup_end_intent("నాకు బైక్ బాగానే ఉంది ప్రస్తుతానికి")
    assert not caller_backup_end_intent("tell me more about the plots")


def test_backup_does_not_need_tool_for_validate():
    d = validate_end_call(
        {"should_end": False, "reason": "none", "farewell": ""},
        user_text=TELUGU_NO_CALL,
        language="te-IN",
        completed_turns=1,
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"


@pytest.mark.asyncio
async def test_1_backup_telugu_refusal_no_tool():
    loop = _loop()
    timeouts: list[str] = []
    orig = loop._runtime_end

    async def _spy(reason: str) -> None:
        timeouts.append(reason)
        await orig(reason)

    loop._runtime_end = _spy
    await loop._handle_event({"type": "user_transcript", "text": TELUGU_NO_CALL, "final": True})
    await asyncio.sleep(0.28)
    assert loop._pending_end_call is not None
    assert loop._pending_end_call.get("reason") == "firm_refusal"
    assert loop._firm_refusal_close is True
    assert loop._hangup_arm_source == "backup"
    joined = " ".join(loop._adapter.started_responses).lower()
    assert "noted in records" not in joined
    assert "callback" not in joined
    assert "farewell" in joined or loop._hangup_farewell_inject_tried
    now = time.monotonic()
    loop._response_open = True
    loop._response_activity_at = now - 31
    await loop._check_runtime(now)
    assert "response_timeout" not in timeouts
    assert loop._hangup_started or loop._closed or loop.controller.state == CallState.ENDED


def test_2_primary_hindi_tool_no_english_regex():
    d = validate_end_call(
        {"should_end": True, "reason": "firm_refusal", "farewell": "धन्यवाद।"},
        user_text=HINDI_NO_NEED,
        language="hi-IN",
        completed_turns=2,
        tool_sourced=True,
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"


@pytest.mark.asyncio
async def test_3_tool_without_stt_final_arms_immediately():
    loop = _loop()
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "request_end_call",
            "call_id": "fn-race",
            "arguments": '{"reason": "customer_declined", "farewell_required": true}',
        }
    )
    assert loop._pending_end_call is not None
    assert loop._pending_end_call.get("reason") == "firm_refusal"
    assert loop._hangup_arm_source == "tool"


@pytest.mark.asyncio
async def test_3b_tool_before_stt_final_still_ok_when_stt_arrives():
    loop = _loop()
    user = "I've heard enough of this"
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "request_end_call",
            "call_id": "fn-race",
            "arguments": '{"reason": "customer_declined", "farewell_required": true}',
        }
    )
    assert loop._pending_end_call is not None
    await loop._handle_event({"type": "user_transcript", "text": user, "final": True})
    assert loop._last_user_final_text == user


@pytest.mark.asyncio
async def test_4_stuck_response_after_refusal_is_clean_hangup():
    loop = _loop()
    timeouts: list[str] = []
    orig = loop._runtime_end

    async def _spy(reason: str) -> None:
        timeouts.append(reason)
        await orig(reason)

    loop._runtime_end = _spy
    adapter = loop._adapter
    await loop._handle_event({"type": "user_transcript", "text": TELUGU_NO_CALL, "final": True})
    await asyncio.sleep(0.28)
    now = time.monotonic()
    loop._response_open = True
    loop._response_activity_at = now - 31
    loop._ending_at = now
    await loop._check_runtime(now)
    assert "response_timeout" not in timeouts
    assert adapter.cancelled >= 1
    assert loop._hangup_started or loop._closed
    assert loop.controller.reason != "response_timeout"


@pytest.mark.asyncio
async def test_5_hello_during_farewell_fast_ack_not_reopen():
    loop = _loop()
    await loop._handle_event({"type": "user_transcript", "text": TELUGU_NO_CALL, "final": True})
    await asyncio.sleep(0.28)
    assert loop._pending_end_call is not None
    loop._farewell_response_active = True
    loop._response_had_audio = True
    loop._farewell_complete = True
    await loop._handle_event({"type": "speech_started"})
    assert loop._resume_after_close is False
    assert loop._pending_end_call is not None
    await loop._handle_event({"type": "user_transcript", "text": "hello", "final": True})
    assert loop._resume_after_close is False
    assert loop._hangup_started or loop._closed
