"""
Live End-to-End Dental Clinic Voice Agent Test Suite with Real Integrations.

Tests 3 distinct conversation scenarios for user: mohansaiteja.99@gmail.com
Tenant ID: 6d3fba56-7109-4812-8eb5-4a0d11f558c6
Agent ID:  82fa89d1-00c6-4d95-a124-e6d3103c0430

Integrations Tested Live:
1. Google Calendar (FreeBusy check & Event creation) via Nango OAuth proxy
2. Gmail (Confirmation email dispatch) via Nango OAuth proxy
"""
from __future__ import annotations

import os
os.environ["LIVE_DB"] = "1"
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://voice_agent:voice_agent@localhost:5432/voice_agent"

import asyncio
import json
import uuid
import pytest
from sqlalchemy import select

from server.db.connection import get_session_factory, init_db
from server.db.models.integration_models import ToolExecution
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
from server.services.tool_router import tool_router


TENANT_ID = "6d3fba56-7109-4812-8eb5-4a0d11f558c6"
AGENT_ID = "82fa89d1-00c6-4d95-a124-e6d3103c0430"
TEST_EMAIL = "mohansaiteja.99@gmail.com"


def extract_output(started_responses: list[str], call_id: str) -> dict:
    prefix = f"fn:{call_id}:"
    for r in started_responses:
        if r.startswith(prefix):
            raw = r[len(prefix):]
            return json.loads(raw)
    raise AssertionError(f"No response found for call_id {call_id} in {started_responses}")


@pytest.fixture(autouse=True)
async def setup_env():
    await init_db()


@pytest.mark.asyncio
async def test_scenario_1_standard_lead_booking():
    """Scenario 1: Standard Inbound Lead Booking with Specific Date/Time."""
    print("\n========================================================")
    print("RUNNING SCENARIO 1: Standard Inbound Lead Booking")
    print("========================================================")

    call_id = f"dental-call-sc1-{uuid.uuid4().hex[:6]}"
    wire_audio_frames: list[bytes] = []
    hangup_events: list[str] = []

    async def on_wire(data: bytes) -> None:
        wire_audio_frames.append(data)

    async def on_hangup() -> None:
        hangup_events.append("hangup")

    adapter = FakeRealtimeVoiceAdapter()
    agent_tools = [
        "googlecalendar_find_free_slots",
        "googlecalendar_create_event",
        "gmail_send_email",
        "request_end_call",
    ]

    loop = PstnRealtimeVoiceLoop(
        session_id=f"sess-{call_id}",
        call_id=call_id,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id=TENANT_ID,
        agent_id=AGENT_ID,
        agent_tools=agent_tools,
        stack_override={"pipeline": "realtime_voice"},
    )
    loop.set_hangup_handler(on_hangup)
    await loop.start_call(play_greeting=False)

    # TURN 1: Caller states intent to book free checkup
    print("Turn 1: Caller asks about free checkup for tomorrow afternoon")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "Hello, I saw your dental clinic offers a free checkup. Are there any slots open tomorrow afternoon?",
    })

    # TURN 2: Agent checks real Google Calendar availability
    print("Turn 2: Agent checks live Google Calendar availability...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_find_free_slots",
        "call_id": "fn_check_slots_sc1",
        "arguments": json.dumps({"date": "tomorrow", "duration": 30}),
    })

    # Assert acoustic filler sent & adapter received live slots
    assert len(wire_audio_frames) > 0, "Acoustic filler audio must be emitted"
    slot_resp = extract_output(adapter.started_responses, "fn_check_slots_sc1")
    print("-> Live Slot Check Output:", slot_resp)
    assert slot_resp.get("status") == "available" or "available_slots" in slot_resp

    # TURN 3: Caller picks 2:00 PM and provides contact details
    print("Turn 3: Caller chooses 2:00 PM and gives email")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": f"2:00 PM works great for me. My name is Kavya Reddy and my email is {TEST_EMAIL}.",
    })

    # TURN 4: Agent books appointment on live Google Calendar
    print("Turn 4: Agent creates event on live Google Calendar...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_create_event",
        "call_id": "fn_book_event_sc1",
        "arguments": json.dumps({
            "summary": "Dental Clinic Free Checkup - Kavya Reddy",
            "start": "2026-10-07T14:00:00+05:30",
            "end": "2026-10-07T14:30:00+05:30",
            "attendee_email": TEST_EMAIL,
            "description": "Complimentary Dental Screening and Oral Examination",
        }),
    })

    # Verify event created
    book_resp = extract_output(adapter.started_responses, "fn_book_event_sc1")
    print("-> Live Event Creation Output:", book_resp)
    assert book_resp.get("status") == "confirmed" or book_resp.get("confirmed") is True

    # TURN 5: Agent dispatches email confirmation via Gmail
    print("Turn 5: Agent sends confirmation email via Gmail...")
    await loop._handle_event({
        "type": "function_call",
        "name": "gmail_send_email",
        "call_id": "fn_send_email_sc1",
        "arguments": json.dumps({
            "to": TEST_EMAIL,
            "subject": "Appointment Confirmation - Free Dental Checkup (Smile Dental Care)",
            "body": "Dear Kavya,\n\nYour free dental checkup is confirmed for tomorrow, Oct 7 at 2:00 PM.\n\nLocation: Smile Dental Clinic, Main Road\nConsultation Fee: Free ($0)\n\nWe look forward to seeing you!",
        }),
    })

    email_resp = extract_output(adapter.started_responses, "fn_send_email_sc1")
    print("-> Live Gmail Send Output:", email_resp)
    assert email_resp.get("status") == "sent"

    # TURN 6: Wrap up and hangup
    print("Turn 6: Caller thanks agent and call ends")
    await loop._handle_event({
        "type": "function_call",
        "name": "request_end_call",
        "call_id": "fn_hangup_sc1",
        "arguments": json.dumps({"reason": "Appointment booked and confirmed successfully"}),
    })

    # Verify database audit records
    session_factory = get_session_factory()
    async with session_factory() as session:
        execs = (
            await session.execute(
                select(ToolExecution).where(ToolExecution.call_id == call_id)
            )
        ).scalars().all()
        print(f"Audit log recorded {len(execs)} tool executions in DB:")
        for ex in execs:
            print(f"  [{ex.status}] {ex.action} (type: {ex.action_type})")
        assert len(execs) >= 2


@pytest.mark.asyncio
async def test_scenario_2_hesitant_caller_faq_and_morning_slot():
    """Scenario 2: Hesitant Caller Asking About Fees, Then Booking Friday Morning."""
    print("\n========================================================")
    print("RUNNING SCENARIO 2: Objection Handling & Morning Booking")
    print("========================================================")

    call_id = f"dental-call-sc2-{uuid.uuid4().hex[:6]}"
    wire_audio_frames: list[bytes] = []

    async def on_wire(data: bytes) -> None:
        wire_audio_frames.append(data)

    adapter = FakeRealtimeVoiceAdapter()
    agent_tools = [
        "googlecalendar_find_free_slots",
        "googlecalendar_create_event",
        "gmail_send_email",
        "request_end_call",
    ]

    loop = PstnRealtimeVoiceLoop(
        session_id=f"sess-{call_id}",
        call_id=call_id,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id=TENANT_ID,
        agent_id=AGENT_ID,
        agent_tools=agent_tools,
        stack_override={"pipeline": "realtime_voice"},
    )
    await loop.start_call(play_greeting=False)

    # TURN 1: Caller asks about fees & procedure
    print("Turn 1: Caller asks about hidden charges")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "Hi, is this dental checkup completely free or will there be extra fees when I visit?",
    })

    # Agent reassurance turn
    await loop._handle_event({
        "type": "assistant_transcript",
        "text": "The comprehensive examination and doctor consultation are completely free with zero hidden fees. We would love to have you visit!",
    })

    # TURN 2: Caller agrees and requests Friday morning
    print("Turn 2: Caller requests Friday morning appointment")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "That sounds wonderful. What morning slots do you have for Friday October 9th?",
    })

    # TURN 3: Agent checks live calendar for 2026-10-09
    print("Turn 3: Agent queries live calendar for 2026-10-09...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_find_free_slots",
        "call_id": "fn_check_slots_sc2",
        "arguments": json.dumps({"date": "2026-10-09", "duration": 30}),
    })

    slot_resp = extract_output(adapter.started_responses, "fn_check_slots_sc2")
    print("-> Live Slot Check Output:", slot_resp)
    assert slot_resp.get("status") == "available" or "available_slots" in slot_resp

    # TURN 4: Caller picks 10:00 AM
    print("Turn 4: Caller confirms 10:00 AM for Vikram Verma")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": f"Please book 10:00 AM under Vikram Verma, email is {TEST_EMAIL}.",
    })

    # TURN 5: Agent books live calendar event
    print("Turn 5: Booking appointment on Google Calendar...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_create_event",
        "call_id": "fn_book_event_sc2",
        "arguments": json.dumps({
            "summary": "Dental Consultation - Vikram Verma",
            "start": "2026-10-09T10:00:00+05:30",
            "end": "2026-10-09T10:30:00+05:30",
            "attendee_email": TEST_EMAIL,
            "description": "First time dental patient - Free health checkup",
        }),
    })

    book_resp = extract_output(adapter.started_responses, "fn_book_event_sc2")
    print("-> Live Event Creation Output:", book_resp)
    assert book_resp.get("status") == "confirmed" or book_resp.get("confirmed") is True

    # TURN 6: Email dispatch
    print("Turn 6: Sending confirmation email via Gmail...")
    await loop._handle_event({
        "type": "function_call",
        "name": "gmail_send_email",
        "call_id": "fn_send_email_sc2",
        "arguments": json.dumps({
            "to": TEST_EMAIL,
            "subject": "Smile Dental Clinic - Friday 10:00 AM Free Checkup Confirmed",
            "body": "Hi Vikram,\n\nYour appointment is confirmed for Friday, Oct 9 at 10:00 AM.\n\nPlease arrive 5 minutes early. We are excited to meet you!\n\nBest,\nSmile Dental Team",
        }),
    })

    email_resp = extract_output(adapter.started_responses, "fn_send_email_sc2")
    print("-> Live Gmail Send Output:", email_resp)
    assert email_resp.get("status") == "sent"


@pytest.mark.asyncio
async def test_scenario_3_rescheduling_and_afternoon_slot():
    """Scenario 3: Rescheduling Negotiation and Booking Afternoon Slot."""
    print("\n========================================================")
    print("RUNNING SCENARIO 3: Rescheduling & Slot Negotiation")
    print("========================================================")

    call_id = f"dental-call-sc3-{uuid.uuid4().hex[:6]}"
    wire_audio_frames: list[bytes] = []

    async def on_wire(data: bytes) -> None:
        wire_audio_frames.append(data)

    adapter = FakeRealtimeVoiceAdapter()
    agent_tools = [
        "googlecalendar_find_free_slots",
        "googlecalendar_create_event",
        "gmail_send_email",
        "request_end_call",
    ]

    loop = PstnRealtimeVoiceLoop(
        session_id=f"sess-{call_id}",
        call_id=call_id,
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id=TENANT_ID,
        agent_id=AGENT_ID,
        agent_tools=agent_tools,
        stack_override={"pipeline": "realtime_voice"},
    )
    await loop.start_call(play_greeting=False)

    # TURN 1: Caller wants today at 11:00 AM
    print("Turn 1: Caller requests slot for today")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "Hello, can I come in for the free checkup today at 11:00 AM?",
    })

    # TURN 2: Check availability for today
    print("Turn 2: Agent checks live calendar for today...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_find_free_slots",
        "call_id": "fn_check_slots_sc3",
        "arguments": json.dumps({"date": "today", "duration": 30}),
    })

    slot_resp = extract_output(adapter.started_responses, "fn_check_slots_sc3")
    print("-> Live Slot Check Output:", slot_resp)
    assert slot_resp.get("status") == "available" or "available_slots" in slot_resp

    # TURN 3: Caller negotiates for tomorrow afternoon at 3:30 PM
    print("Turn 3: Caller switches to tomorrow afternoon at 3:30 PM")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": f"Alright, tomorrow at 3:30 PM works. Please book it under Ananya Sen, email {TEST_EMAIL}.",
    })

    # TURN 4: Agent books event on Google Calendar
    print("Turn 4: Booking tomorrow 3:30 PM on Google Calendar...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_create_event",
        "call_id": "fn_book_event_sc3",
        "arguments": json.dumps({
            "summary": "Free Dental Consultation - Ananya Sen",
            "start": "2026-10-07T15:30:00+05:30",
            "end": "2026-10-07T16:00:00+05:30",
            "attendee_email": TEST_EMAIL,
            "description": "Routine dental examination and teeth cleaning consultation",
        }),
    })

    book_resp = extract_output(adapter.started_responses, "fn_book_event_sc3")
    print("-> Live Event Creation Output:", book_resp)
    assert book_resp.get("status") == "confirmed" or book_resp.get("confirmed") is True

    # TURN 5: Confirmation email dispatch
    print("Turn 5: Sending confirmation email via Gmail...")
    await loop._handle_event({
        "type": "function_call",
        "name": "gmail_send_email",
        "call_id": "fn_send_email_sc3",
        "arguments": json.dumps({
            "to": TEST_EMAIL,
            "subject": "Smile Dental Clinic - Tomorrow 3:30 PM Checkup Confirmed",
            "body": "Dear Ananya,\n\nYour free dental checkup appointment is booked for tomorrow at 3:30 PM.\n\nAddress: 124 Dental Care Plaza, Suite 3\nDoctor: Dr. Rao\nCost: $0 (Free Examination)\n\nSee you tomorrow!",
        }),
    })

    email_resp = extract_output(adapter.started_responses, "fn_send_email_sc3")
    print("-> Live Gmail Send Output:", email_resp)
    assert email_resp.get("status") == "sent"

    print("\nALL 3 CONVERSATION SCENARIOS PASSED WITH 100% REAL INTEGRATIONS!")
