from unittest.mock import AsyncMock

import pytest

from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


def make_loop():
    loop = PstnRealtimeVoiceLoop(
        session_id="false-close", call_id=None, on_agent_wire=AsyncMock(),
        stack_override={"language": "te-IN"},
    )
    loop._adapter = FakeRealtimeVoiceAdapter()
    return loop


@pytest.mark.asyncio
async def test_location_question_false_end_recovers_once():
    loop = make_loop()
    loop._last_user_final_text = loop._user_partial = "ఇప్పుడు లొకేషన్ ఎక్కడ అండి?"
    loop._assistant_text = "This call has ended. Have a great day!"
    await loop._maybe_hangup_missed_end_call()
    assert loop._pending_end_call is None
    assert "answer the caller's last question" in loop._pending_followup_instruction
    loop._pending_followup_instruction = None
    await loop._maybe_hangup_missed_end_call()
    assert loop._pending_followup_instruction is None
    await loop.close()


@pytest.mark.asyncio
async def test_regular_answer_does_not_inject_recovery():
    loop = make_loop()
    loop._last_user_final_text = loop._user_partial = "Where are you?"
    loop._assistant_text = "We are in Boduppal, Hyderabad."
    await loop._maybe_hangup_missed_end_call()
    assert loop._pending_followup_instruction is None
    assert loop._pending_end_call is None
    await loop.close()


@pytest.mark.asyncio
async def test_completed_objective_tool_disconnects_after_audio():
    loop = make_loop()
    loop._last_user_final_text = loop._user_partial = "Please call me tomorrow at eight in the morning."
    hangup = AsyncMock()
    loop.set_hangup_handler(hangup)
    loop._response_had_audio = True
    loop._assistant_text = "ధన్యవాదాలు."
    await loop._handle_event({
        "type": "function_call", "name": "end_call", "call_id": "close-tool",
        "arguments": {"should_end": True, "reason": "goal_complete", "farewell": "ధన్యవాదాలు."},
    })
    assert loop._pending_end_call is not None
    await loop._handle_event({"type": "response_done"})
    hangup.assert_awaited_once()
    assert loop._closed
    await loop.close()
