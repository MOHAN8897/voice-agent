"""Five multi-intent PSTN hangup conversations (synthetic loop, no live API)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from server.call.call_controller import CallState
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop

TELUGU_NO_CALL = "కాల్ అవసరం లేదు"
HINDI_NO_NEED = "मुझे इसकी जरूरत नहीं है"


def _loop(lang: str = "en-IN") -> PstnRealtimeVoiceLoop:
    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="matrix",
        call_id="matrix-call",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "language": lang},
    )
    loop._adapter = adapter
    loop.set_hangup_handler(AsyncMock())
    return loop


async def _user(loop: PstnRealtimeVoiceLoop, text: str) -> None:
    await loop._handle_event({"type": "user_transcript", "text": text, "final": True})


async def _agent_done(loop: PstnRealtimeVoiceLoop, text: str, *, audio: bool = True) -> None:
    loop._response_had_audio = audio
    loop._assistant_text = text
    await loop._handle_event({"type": "response_done"})


async def _finish_if_armed(loop: PstnRealtimeVoiceLoop, text: str) -> AsyncMock:
    hangup = AsyncMock()
    loop.set_hangup_handler(hangup)
    loop._response_had_audio = True
    loop._assistant_text = text
    await loop._handle_event({"type": "response_done"})
    return hangup


async def _hangup_tool(
    loop: PstnRealtimeVoiceLoop,
    *,
    reason: str = "goal_complete",
    farewell: str = "Thank you. Goodbye.",
) -> None:
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "request_end_call",
            "call_id": "tool-1",
            "arguments": {
                "should_end": True,
                "reason": reason,
                "farewell": farewell,
            },
        }
    )


@pytest.mark.asyncio
async def test_conv1_en_callback_thanks_closing_repairs_hangup():
    """Callback yes → thanks → agent 'have a great day' without tool → server repair."""
    loop = _loop("en-IN")
    loop._callback_request_text = "Yes, yes, schedule a callback."
    await _user(loop, "Yeah, thank you.")
    await _agent_done(loop, "You're welcome. Have a great day.")
    assert loop._closed or loop._pending_end_call is not None
    if loop._pending_end_call:
        assert loop._pending_end_call.get("reason") == "goal_complete"
    await loop.close()


@pytest.mark.asyncio
async def test_conv2_en_disqualify_no_vehicle_repairs_hangup():
    loop = _loop("en-IN")
    await _user(loop, "Can you service my friend's BMW? I don't own a car.")
    spoken = (
        "Thank you. Since you don't have a vehicle yourself, "
        "I will thank you for your time today."
    )
    await _agent_done(loop, spoken)
    assert loop._pending_end_call is not None
    assert loop._pending_end_call.get("reason") == "goal_complete"
    await loop.close()


@pytest.mark.asyncio
async def test_conv3_te_firm_refusal_backup_arms_without_tool():
    loop = _loop("te-IN")
    await _user(loop, TELUGU_NO_CALL)
    await asyncio.sleep(0.28)
    assert loop._pending_end_call is not None
    assert loop._pending_end_call.get("reason") == "firm_refusal"
    assert loop._hangup_arm_source == "backup"
    await loop.close()


@pytest.mark.asyncio
async def test_conv4_hi_tool_firm_refusal_arms_and_finishes_on_response_done():
    loop = _loop("hi-IN")
    await _hangup_tool(loop, reason="firm_refusal", farewell="धन्यवाद। अलविदा।")
    await _user(loop, HINDI_NO_NEED)
    assert loop._pending_end_call is not None
    assert loop._pending_end_call.get("reason") == "firm_refusal"
    assert loop._hangup_arm_source in {"tool", "backup"}
    hangup = await _finish_if_armed(loop, "धन्यवाद। अलविदा।")
    hangup.assert_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_conv5_en_explicit_bye_tool_primary_path():
    loop = _loop("en-IN")
    await _user(loop, "Okay that's all, please hang up.")
    await _hangup_tool(loop, reason="goodbye", farewell="Thank you for your time. Goodbye.")
    assert loop._pending_end_call is not None
    assert loop._pending_end_call.get("reason") == "goodbye"
    assert loop.controller.state == CallState.ENDING
    hangup = await _finish_if_armed(loop, "Thank you for your time. Goodbye.")
    hangup.assert_awaited()
    await loop.close()
