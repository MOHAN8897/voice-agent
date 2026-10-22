"""Mocked dental booking voice flow; no database, calendar, mail, or carrier access."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, call, patch

import pytest

from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.mark.asyncio
async def test_booking_tools_return_mocked_results_and_farewell_precedes_hangup() -> None:
    adapter = FakeRealtimeVoiceAdapter()
    wire_frames: list[bytes] = []

    async def on_wire(data: bytes) -> None:
        wire_frames.append(data)

    loop = PstnRealtimeVoiceLoop(
        session_id="dental-mock-session",
        call_id=None,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id="tenant-test",
        agent_id="agent-test",
        agent_tools={
            "googlecalendar_find_free_slots",
            "googlecalendar_create_event",
            "gmail_send_email",
        },
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    finish_hangup = AsyncMock()
    loop._finish_hangup = finish_hangup
    tool_results = [
        {"status": "available", "slots": [{"start": "14:00", "end": "14:30"}]},
        {"status": "confirmed", "event_id": "event-test"},
        {"status": "sent", "message_id": "message-test"},
    ]
    tool_events = [
        ("googlecalendar_find_free_slots", "slots", {"date": "2030-01-02"}),
        ("googlecalendar_create_event", "booking", {"start": "14:00", "attendee": "caller-test"}),
        ("gmail_send_email", "email", {"to": "caller-test", "subject": "Appointment details"}),
    ]

    try:
        with patch(
            "server.services.tool_router.tool_router.route_and_execute",
            new_callable=AsyncMock,
            side_effect=tool_results,
        ) as route:
            for tool_name, call_id, arguments in tool_events:
                await loop._handle_event(
                    {
                        "type": "function_call",
                        "name": tool_name,
                        "call_id": call_id,
                        "arguments": json.dumps(arguments),
                    }
                )

        assert route.await_args_list == [
            call(
                tenant_id="tenant-test",
                agent_id="agent-test",
                call_id="",
                tool_name=tool_name,
                arguments=arguments,
            )
            for tool_name, _call_id, arguments in tool_events
        ]
        for (_tool_name, call_id, _arguments), result in zip(tool_events, tool_results, strict=True):
            assert any(call_id in item and json.dumps(result) in item for item in adapter.started_responses)
        assert wire_frames, "mock integration latency must emit silent filler frames"

        await loop._handle_event({"type": "audio_delta", "pcm": b"\x01\x00" * 2400})
        await loop._handle_event({"type": "assistant_transcript_delta", "delta": "Thank you. Goodbye."})
        await loop._handle_event(
            {
                "type": "function_call",
                "name": "request_end_call",
                "call_id": "hangup",
                "arguments": json.dumps(
                    {"should_end": True, "reason": "goodbye", "farewell": "Thank you. Goodbye."}
                ),
            }
        )
        assert loop._pending_end_call is not None
        finish_hangup.assert_not_awaited()

        await loop._handle_event({"type": "response_done"})
        assert loop._farewell_complete is True
        finish_hangup.assert_awaited_once()
    finally:
        await loop.close()
