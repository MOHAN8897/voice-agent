"""Live transcript chunks must preserve words used by callback close detection."""
from unittest.mock import AsyncMock

import pytest

from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks, expected", [
    (["Spandana Private", " Limited ", "lo servicing", " chestamu."],
     "Spandana Private Limited lo servicing chestamu."),
    (["Thank", " ", "you. Good", "bye!"], "Thank you. Goodbye!"),
    (["ధన్యవాదాలు.", " ", "నమస్కారం."], "ధన్యవాదాలు. నమస్కారం."),
    (["Spandana Pri", "vate Limited."], "Spandana Private Limited."),
])
async def test_streaming_boundaries_survive_turn_completion(chunks, expected):
    loop = PstnRealtimeVoiceLoop(
        session_id="boundaries", call_id=None, on_agent_wire=AsyncMock(),
        stack_override={"language": "te-IN"},
    )
    for chunk in chunks:
        await loop._handle_event({"type": "assistant_transcript_delta", "delta": chunk})
    await loop._handle_event({"type": "response_done"})
    assert loop._assistant_text == expected
    await loop.close()


@pytest.mark.asyncio
async def test_split_farewell_closes_existing_callback_after_ack():
    loop = PstnRealtimeVoiceLoop(
        session_id="callback-boundaries", call_id=None, on_agent_wire=AsyncMock(),
        stack_override={"language": "en-IN"},
    )
    loop._callback_request_text = "Please call me tomorrow"
    loop._user_partial = loop._last_user_final_text = "OK"
    loop._gate_end_call_payload = AsyncMock(return_value={
        "should_end": True, "reason": "goal_complete", "farewell": "Thank you. Goodbye!",
    })
    loop._finalize_hangup_after_farewell = AsyncMock()
    for chunk in ["Thank", " you. ", "Good", "bye!"]:
        await loop._handle_event({"type": "assistant_transcript_delta", "delta": chunk})
    await loop._handle_event({"type": "response_done"})
    loop._gate_end_call_payload.assert_awaited_once()
    assert loop._pending_end_call["reason"] == "goal_complete"
    assert loop._pending_followup_instruction is None
    await loop.close()
