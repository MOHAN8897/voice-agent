"""Mocked calendar collisions; these cases never write to a real calendar."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, call, patch

import pytest

from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "requested_slot,alternative",
    [
        ("14:00", "16:30"),
        ("10:00", "11:30"),
        ("09:00", "13:00"),
    ],
)
async def test_collision_result_is_returned_before_one_alternative_booking(
    requested_slot: str, alternative: str
) -> None:
    adapter = FakeRealtimeVoiceAdapter()
    wire_frames: list[bytes] = []

    async def on_wire(data: bytes) -> None:
        wire_frames.append(data)

    loop = PstnRealtimeVoiceLoop(
        session_id="dental-conflict-mock",
        call_id=None,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id="tenant-test",
        agent_id="agent-test",
        agent_tools={"googlecalendar_find_free_slots", "googlecalendar_create_event"},
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    conflict = {"status": "conflict", "requested": requested_slot, "alternatives": [alternative]}
    booking = {"status": "confirmed", "event_id": "event-test", "start": alternative}

    try:
        with patch(
            "server.services.tool_router.tool_router.route_and_execute",
            new_callable=AsyncMock,
            side_effect=[conflict, booking],
        ) as route:
            await loop._handle_event(
                {
                    "type": "function_call",
                    "name": "googlecalendar_find_free_slots",
                    "call_id": "availability",
                    "arguments": json.dumps({"date": "2030-01-02", "requested_time": requested_slot}),
                }
            )
            assert any("availability" in item and json.dumps(conflict) in item for item in adapter.started_responses)

            await loop._handle_event(
                {
                    "type": "function_call",
                    "name": "googlecalendar_create_event",
                    "call_id": "alternative-booking",
                    "arguments": json.dumps({"date": "2030-01-02", "start": alternative}),
                }
            )

        assert route.await_args_list == [
            call(
                tenant_id="tenant-test",
                agent_id="agent-test",
                call_id="",
                tool_name="googlecalendar_find_free_slots",
                arguments={"date": "2030-01-02", "requested_time": requested_slot},
            ),
            call(
                tenant_id="tenant-test",
                agent_id="agent-test",
                call_id="",
                tool_name="googlecalendar_create_event",
                arguments={"date": "2030-01-02", "start": alternative},
            ),
        ]
        assert len(route.await_args_list) == 2, "only the alternative slot may be booked after a conflict"
        assert any(
            "alternative-booking" in item and json.dumps(booking) in item
            for item in adapter.started_responses
        )
        assert wire_frames, "mock integration latency must emit silent filler frames"
    finally:
        await loop.close()
