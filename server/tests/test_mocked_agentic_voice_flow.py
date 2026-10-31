"""Offline voice-loop integration checks. These tests never open a DB or provider."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.mark.asyncio
async def test_mocked_agent_tool_dispatch_streams_filler_and_returns_result():
    adapter = FakeRealtimeVoiceAdapter()
    wire_frames: list[bytes] = []

    async def on_wire(data: bytes) -> None:
        wire_frames.append(data)

    loop = PstnRealtimeVoiceLoop(
        session_id="mock-session",
        call_id=None,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id="tenant-test",
        agent_id="agent-test",
        agent_tools={"googlecalendar_find_free_slots"},
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    result = {"status": "success", "slots": [{"start": "14:00", "end": "15:00"}]}

    try:
        with patch(
            "server.services.tool_router.tool_router.route_and_execute",
            new_callable=AsyncMock,
            return_value=result,
        ) as route:
            await loop._handle_event(
                {
                    "type": "function_call",
                    "name": "googlecalendar_find_free_slots",
                    "call_id": "mock-tool-call",
                    "arguments": json.dumps({"date": "2030-01-02"}),
                }
            )

        route.assert_awaited_once_with(
            tenant_id="tenant-test",
            agent_id="agent-test",
            call_id="",
            tool_name="googlecalendar_find_free_slots",
            arguments={"date": "2030-01-02"},
        )
        assert wire_frames, "tool latency should emit the silent acoustic filler frame"
        assert all(frame and not any(frame) for frame in wire_frames)
        assert any(
            "mock-tool-call" in response and json.dumps(result) in response
            for response in adapter.started_responses
        ), "the mocked integration result should return to the voice adapter"
    finally:
        await loop.close()
