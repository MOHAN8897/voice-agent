"""Hangup tool contract — malformed args, ordering, duplicates, no-audio finalize."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from server.realtime.end_call_tool import parse_end_call_tool
from server.realtime.hangup_tools import parse_live_hangup_tool, parse_request_end_call_tool
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


def _loop() -> PstnRealtimeVoiceLoop:
    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="tool-contract",
        call_id="tool-contract-call",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    loop._adapter = adapter
    hangup = AsyncMock()
    loop.set_hangup_handler(hangup)
    loop._hangup_mock = hangup
    return loop


def _tool_event(
    *,
    name: str = "request_end_call",
    arguments: dict | str,
    call_id: str = "fn-1",
) -> dict:
    return {
        "type": "function_call",
        "name": name,
        "call_id": call_id,
        "arguments": arguments,
    }


@pytest.mark.asyncio
async def test_end_call_should_end_false_does_not_arm():
    loop = _loop()
    await loop._handle_event(
        _tool_event(
            name="end_call",
            arguments={"should_end": False, "reason": "none", "farewell": ""},
        )
    )
    assert loop._pending_end_call is None
    assert not loop._hangup_started
    loop._hangup_mock.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_request_end_call_should_end_false_does_not_arm():
    loop = _loop()
    parsed = parse_request_end_call_tool({"should_end": False, "reason": "caller_goodbye"})
    assert parsed is not None and parsed.get("should_end") is False
    await loop._handle_event(
        _tool_event(arguments={"should_end": False, "reason": "caller_goodbye"})
    )
    assert loop._pending_end_call is None
    loop._hangup_mock.assert_not_awaited()
    await loop.close()


@pytest.mark.asyncio
async def test_request_end_call_missing_farewell_arms_without_crash():
    loop = _loop()
    await loop._handle_event(
        {
            "type": "user_transcript",
            "text": "That's all, goodbye.",
            "final": True,
        }
    )
    await loop._handle_event(
        _tool_event(
            arguments={"reason": "caller_goodbye"},
        )
    )
    assert loop._pending_end_call is not None
    assert loop._pending_farewell_text
    await loop.close()


@pytest.mark.asyncio
async def test_invalid_tool_arguments_do_not_arm():
    loop = _loop()
    await loop._handle_event({"type": "user_transcript", "text": "hello", "final": True})
    for bad in (
        {"should_end": "yes", "reason": "goodbye"},
        {"should_end": True, "reason": None},
        {"should_end": True, "reason": "not_a_real_reason"},
        "not-json{{{",
    ):
        await loop._handle_event(_tool_event(name="end_call", arguments=bad, call_id="bad"))
        assert loop._pending_end_call is None
    loop._hangup_mock.assert_not_awaited()
    await loop.close()


def test_parse_layers_reject_malformed_payloads():
    assert parse_end_call_tool({"should_end": "yes", "reason": "goodbye"}) is None
    assert parse_end_call_tool({"should_end": True, "reason": "bogus"}) is None
    assert parse_end_call_tool("not-json") is None
    assert parse_request_end_call_tool({"reason": None}) is None
    declined = parse_live_hangup_tool("end_call", {"should_end": False, "reason": "none"})
    assert declined is not None
    assert declined["should_end"] is False
    assert declined.get("reason") == "none"


@pytest.mark.asyncio
async def test_response_done_without_audio_defers_disconnect_until_farewell():
    """Contract: no Telnyx hangup until farewell audio path completes or is injected."""
    loop = _loop()
    await loop._handle_event({"type": "user_transcript", "text": "hello", "final": True})
    await loop._handle_event(
        _tool_event(
            name="end_call",
            arguments={"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        )
    )
    assert loop._pending_end_call is not None
    loop._assistant_text = "Goodbye."
    loop._response_had_audio = False
    await loop._handle_event({"type": "response_done"})
    loop._hangup_mock.assert_not_awaited()
    assert loop._hangup_farewell_inject_tried or loop._farewell_response_active
    loop._response_had_audio = True
    await loop._handle_event({"type": "response_done"})
    loop._hangup_mock.assert_awaited_once()
    await loop.close()


@pytest.mark.asyncio
async def test_duplicate_request_end_call_hangs_up_once():
    loop = _loop()
    await loop._handle_event({"type": "user_transcript", "text": "bye", "final": True})
    args = {"reason": "caller_goodbye", "farewell_text": "Goodbye."}
    await loop._handle_event(_tool_event(arguments=args, call_id="a"))
    await loop._handle_event(_tool_event(arguments=args, call_id="b"))
    assert loop._pending_end_call is not None
    loop._response_had_audio = True
    loop._assistant_text = "Goodbye."
    await loop._handle_event({"type": "response_done"})
    assert loop._hangup_mock.await_count == 1
    await loop.close()


@pytest.mark.asyncio
async def test_response_done_before_tool_then_tool_then_done():
    loop = _loop()
    loop._callback_request_text = "Please call me back tomorrow."
    await loop._handle_event({"type": "user_transcript", "text": "Yes, that works.", "final": True})
    loop._assistant_text = "Great, we have you down for a callback."
    loop._response_had_audio = True
    await loop._handle_event({"type": "response_done"})
    assert loop._pending_end_call is None
    await loop._handle_event(
        _tool_event(
            name="request_end_call",
            arguments={"reason": "goal_complete", "farewell_text": "Thank you. Goodbye."},
        )
    )
    assert loop._pending_end_call is not None
    loop._assistant_text = "Thank you. Goodbye."
    await loop._handle_event({"type": "response_done"})
    loop._hangup_mock.assert_awaited_once()
    await loop.close()


@pytest.mark.asyncio
async def test_tool_before_response_done_normal_path():
    loop = _loop()
    await loop._handle_event({"type": "user_transcript", "text": "hang up please", "final": True})
    await loop._handle_event(
        _tool_event(
            name="end_call",
            arguments={"should_end": True, "reason": "goodbye", "farewell": "Goodbye."},
        )
    )
    loop._response_had_audio = True
    loop._assistant_text = "Goodbye."
    await loop._handle_event({"type": "response_done"})
    loop._hangup_mock.assert_awaited_once()
    await loop.close()


def test_llm_judgment_layer_refusal_expects_firm_refusal_not_premature_goal_complete():
    """Policy layer: interested caller must not be closed as goal_complete without tool+evidence."""
    from server.call.end_call_validate import validate_end_call

    d = validate_end_call(
        {"should_end": True, "reason": "goal_complete", "farewell": "Goodbye."},
        user_text="Tell me more about pricing",
        language="en-IN",
        completed_turns=2,
        spoken_text="Goodbye.",
        tool_sourced=True,
    )
    assert d.accepted is False
    assert d.reject_code in {"caller_engaged", "user_asked_question", "no_evidence"}


def test_llm_judgment_layer_firm_refusal_accepts_customer_declined_tool():
    from server.call.end_call_validate import validate_end_call

    raw = parse_request_end_call_tool({"reason": "customer_declined", "farewell_text": "Thanks."})
    assert raw is not None
    d = validate_end_call(
        raw,
        user_text="मुझे इसकी जरूरत नहीं है",
        language="en-IN",
        completed_turns=2,
        tool_sourced=True,
    )
    assert d.accepted is True
    assert d.reason == "firm_refusal"
