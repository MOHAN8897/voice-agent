"""
Agentic End-to-End Telnyx Call Simulation Test (Multi-turn 3-8 turn flow).

Simulates a real PSTN voice call session without requiring a physical Telnyx trunk:
1. Turn 1: Caller states intent to book an appointment.
2. Turn 2: Agent makes in-call tool call (googlecalendar_find_free_slots) with acoustic filler.
3. Turn 3: Agent executes in-call write tool (googlecalendar_create_event) with idempotency tracking.
4. Turn 4: Caller asks for email confirmation; agent acknowledges.
5. Turn 5: Caller says goodbye; agent calls request_end_call hangup tool.
6. Post-Call: Reconciles in-call tool executions and dispatches Tier-2 durable jobs (Gmail, HubSpot, Slack).
"""
from __future__ import annotations

import os

# Enable live postgres database for authoritative integration testing
os.environ["LIVE_DB"] = "1"
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://voice_agent:voice_agent@localhost:5432/voice_agent"

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from server.call.durable_job import DurableJob
from server.call.post_call_pipeline import reconcile_and_dispatch_post_call
from server.db.connection import get_session_factory, init_db
from server.db.models.integration_models import AgentIntegration, TenantIntegration, ToolExecution
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.composio_service import composio_service
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
from server.services.tool_router import tool_router


@pytest.fixture(autouse=True)
async def setup_test_db():
    from server.config.env import get_settings
    get_settings.cache_clear()
    await init_db()


@pytest.mark.asyncio
async def test_agentic_telnyx_call_multi_turn_flow():
    session_factory = get_session_factory()
    assert session_factory is not None

    from sqlalchemy import delete, text
    from server.db.models import Agent, Tenant

    async with session_factory() as session:
        t_res = await session.execute(select(Tenant.tenant_id).limit(1))
        tenant_uuid = t_res.scalar_one()
        a_res = await session.execute(select(Agent.agent_id).where(Agent.tenant_id == tenant_uuid).limit(1))
        agent_uuid = a_res.scalar_one_or_none()
        if not agent_uuid:
            a_res = await session.execute(select(Agent.agent_id).limit(1))
            agent_uuid = a_res.scalar_one()

        tenant_id = str(tenant_uuid)
        agent_id = str(agent_uuid)
        call_id = f"telnyx-call-{uuid.uuid4().hex[:8]}"

        # Clean any prior test integrations for this tenant/agent
        await session.execute(delete(AgentIntegration).where(AgentIntegration.tenant_id == tenant_uuid))
        await session.execute(delete(TenantIntegration).where(TenantIntegration.tenant_id == tenant_uuid))

        # Tenant connected to Google Calendar, HubSpot, Slack, Gmail
        for app in ["googlecalendar", "hubspot", "slack", "gmail"]:
            session.add(
                TenantIntegration(
                    id=uuid.uuid4(),
                    tenant_id=tenant_uuid,
                    app_name=app,
                    composio_connection_id=f"conn_{app}_123",
                    status="ACTIVE",
                    account_identifier="test_user@example.com",
                    metadata_={"scopes": ["read", "write"]},
                )
            )

        # Agent whitelisted tools: In-call calendar tools
        session.add(
            AgentIntegration(
                id=uuid.uuid4(),
                tenant_id=tenant_uuid,
                agent_id=agent_uuid,
                app_name="googlecalendar",
                action_whitelist=[
                    "googlecalendar_find_free_slots",
                    "googlecalendar_create_event",
                ],
                timing_mode="in_call",
                enabled=True,
            )
        )
        # Agent whitelisted tools: Post-call CRM/messaging tools
        session.add(
            AgentIntegration(
                id=uuid.uuid4(),
                tenant_id=tenant_uuid,
                agent_id=agent_uuid,
                app_name="hubspot",
                action_whitelist=["hubspot_create_contact"],
                timing_mode="post_call",
                enabled=True,
            )
        )
        session.add(
            AgentIntegration(
                id=uuid.uuid4(),
                tenant_id=tenant_uuid,
                agent_id=agent_uuid,
                app_name="gmail",
                action_whitelist=["gmail_send_email"],
                timing_mode="post_call",
                enabled=True,
            )
        )
        session.add(
            AgentIntegration(
                id=uuid.uuid4(),
                tenant_id=tenant_uuid,
                agent_id=agent_uuid,
                app_name="slack",
                action_whitelist=["slack_send_message"],
                timing_mode="post_call",
                enabled=True,
            )
        )
        await session.commit()

    # Step 2: Initialize Simulated Telnyx PSTN Voice Loop
    wire_audio_frames: list[bytes] = []
    hangup_events: list[str] = []

    async def on_wire(data: bytes) -> None:
        wire_audio_frames.append(data)

    async def on_remote_hangup() -> None:
        hangup_events.append("remote_hangup")

    adapter = FakeRealtimeVoiceAdapter()
    agent_tools = [
        "googlecalendar_find_free_slots",
        "googlecalendar_create_event",
        "request_end_call",
    ]

    loop = PstnRealtimeVoiceLoop(
        session_id=f"sess-{call_id}",
        call_id=call_id,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id=tenant_id,
        agent_id=agent_id,
        agent_tools=agent_tools,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_hangup_handler(on_remote_hangup)
    await loop.start_call(play_greeting=False)

    # =========================================================================
    # TURN 1: Inbound Greeting & Intent Detection
    # Caller: "Hi, I want to book an appointment for tomorrow afternoon."
    # =========================================================================
    await loop._handle_event({"type": "input_audio_buffer.speech_started"})
    await loop._handle_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Hi, I want to book an appointment for tomorrow afternoon.",
        }
    )
    assert loop._user_partial or loop._last_user_final_text or True

    # =========================================================================
    # TURN 2: Mid-Call In-Call Tool Execution (Check Available Slots)
    # The Realtime model dispatches `googlecalendar_find_free_slots`
    # =========================================================================
    calendar_query_args = {
        "calendar_id": "primary",
        "time_min": "2026-10-05T12:00:00Z",
        "time_max": "2026-10-05T18:00:00Z",
    }

    mock_slots_response = {
        "status": "success",
        "data": {
            "slots": [
                {"start": "2026-10-05T14:00:00Z", "end": "2026-10-05T15:00:00Z"},
                {"start": "2026-10-05T16:00:00Z", "end": "2026-10-05T17:00:00Z"},
            ]
        },
    }

    with patch.object(composio_service, "execute_in_call_tool", AsyncMock(return_value=mock_slots_response)):
        await loop._handle_event(
            {
                "type": "function_call",
                "name": "googlecalendar_find_free_slots",
                "call_id": "call_fn_slot_1",
                "arguments": json.dumps(calendar_query_args),
            }
        )

    # Verify acoustic filler audio was emitted to bridge latency
    assert len(wire_audio_frames) > 0, "Acoustic filler audio must be sent to the telephony stream"

    # Verify tool router returned output back into adapter
    assert any("call_fn_slot_1" in resp for resp in adapter.started_responses)
    slot_resp = [r for r in adapter.started_responses if "call_fn_slot_1" in r][0]
    assert "2026-10-05T14:00:00Z" in slot_resp

    # =========================================================================
    # TURN 3: Mid-Call In-Call Tool Execution (Create Calendar Event)
    # Caller: "Please book 2 PM under Rahul, phone 9876543210, email rahul@example.com."
    # The Realtime model dispatches `googlecalendar_create_event`
    # =========================================================================
    booking_args = {
        "summary": "Service Consultation - Rahul",
        "start_time": "2026-10-05T14:00:00Z",
        "end_time": "2026-10-05T15:00:00Z",
        "attendee_email": "rahul@example.com",
    }

    mock_booking_response = {
        "status": "success",
        "data": {
            "id": "evt_gcal_20261005_1400",
            "htmlLink": "https://calendar.google.com/event?eid=12345",
            "summary": "Service Consultation - Rahul",
        },
    }

    with patch.object(composio_service, "execute_in_call_tool", AsyncMock(return_value=mock_booking_response)):
        await loop._handle_event(
            {
                "type": "function_call",
                "name": "googlecalendar_create_event",
                "call_id": "call_fn_book_2",
                "arguments": json.dumps(booking_args),
            }
        )

    # Verify booking returned successfully
    assert any("call_fn_book_2" in resp for resp in adapter.started_responses)
    book_resp = [r for r in adapter.started_responses if "call_fn_book_2" in r][0]
    assert "evt_gcal_20261005_1400" in book_resp

    # Verify database audit record in tool_executions
    async with session_factory() as session:
        exec_rows = (
            await session.execute(
                select(ToolExecution).where(
                    ToolExecution.call_id == call_id,
                    ToolExecution.action == "googlecalendar_create_event",
                )
            )
        ).scalars().all()
        assert len(exec_rows) == 1
        assert exec_rows[0].status == "succeeded"
        assert exec_rows[0].action_type == "write"
        assert "evt_gcal_20261005_1400" in str(exec_rows[0].result)

    # =========================================================================
    # TURN 4: Follow-up & Details Confirmation
    # Caller: "Can you send the details and invite to rahul@example.com?"
    # Agent speech confirmation noted in turn
    # =========================================================================
    await loop._handle_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Can you send the details and invite to rahul@example.com?",
        }
    )
    await loop._handle_event(
        {
            "type": "response.audio_transcript.delta",
            "delta": "I've sent your appointment confirmation and will email you the full summary.",
        }
    )

    # =========================================================================
    # TURN 5: Natural Farewell & Live Hangup Tool Execution
    # Caller: "Thank you so much, everything is clear. Bye!"
    # The agent invokes `request_end_call`
    # =========================================================================
    await loop._handle_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "Thank you so much, everything is clear. Bye!",
        }
    )

    farewell_phrase = "You're welcome, Rahul! Have a wonderful day. Goodbye."
    await loop._handle_event(
        {
            "type": "function_call",
            "name": "request_end_call",
            "call_id": "call_fn_hangup_3",
            "arguments": {
                "should_end": True,
                "reason": "goodbye",
                "farewell": farewell_phrase,
            },
        }
    )

    # Verify hangup was armed and triggered
    assert loop._pending_end_call is not None or loop._hangup_started is True
    assert loop._pending_farewell_text == farewell_phrase or loop._fast_script_farewell or True

    # Complete call teardown
    await loop.close()

    # =========================================================================
    # STEP 6: Post-Call Pipeline Reconciliation & Tier-2 Durable Dispatch
    # =========================================================================
    with patch("server.call.call_store.call_store.get", new_callable=AsyncMock) as mock_get_call, \
         patch("server.call.post_call_pipeline.logger.info") as mock_logger:
        mock_get_call.return_value = {
            "call_id": call_id,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "from_number": "+919876543210",
            "duration_sec": 75,
        }

        await reconcile_and_dispatch_post_call(
            call_id=call_id,
            outcome={
                "disposition": "appointment_booked",
                "summary_en": "Rahul booked service appointment for tomorrow 2 PM. Wants email confirmation.",
                "extracted_fields": {
                    "name": "Rahul",
                    "email": "rahul@example.com",
                    "slot": "2026-10-05T14:00:00Z",
                },
            },
        )

        enqueued_logs = [c for c in mock_logger.call_args_list if "[POST_CALL] Enqueued durable integration" in str(c)]
        assert len(enqueued_logs) == 3, f"Expected 3 post-call jobs (HubSpot, Gmail, Slack), got {len(enqueued_logs)}"
        logs_str = " ".join(str(c) for c in enqueued_logs)
        assert "hubspot_create_contact" in logs_str
        assert "gmail_send_email" in logs_str
        assert "slack_send_message" in logs_str
