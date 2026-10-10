"""
Live End-to-End Dental Clinic Voice Agent Test Suite: Slot Non-Availability & Conflict Handling.

Tests 3 distinct conflict/non-availability conversation scenarios for user: mohansaiteja.99@gmail.com
Tenant ID: 6d3fba56-7109-4812-8eb5-4a0d11f558c6
Agent ID:  82fa89d1-00c6-4d95-a124-e6d3103c0430

Tests live behavior when callers request already-booked slots:
1. Scenario A: Direct Collision on Oct 7 at 2:00 PM (Booked slot detected -> Negotiates 4:30 PM -> Books -> Emails).
2. Scenario B: Friday Morning Collision on Oct 9 at 10:00 AM (Booked slot detected -> Negotiates 11:30 AM -> Books -> Emails).
3. Scenario C: Blind Double-Booking Rejection & Recovery (Direct conflict caught by pre-booking engine -> Caller offered open slot -> Rescheduled).
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
async def test_scenario_a_booked_slot_collision_and_reschedule():
    """Scenario A: Caller requests Oct 7 at 2:00 PM (Already Booked) -> Rescheduled to 4:30 PM."""
    print("\n========================================================")
    print("RUNNING SCENARIO A: Oct 7 2:00 PM Collision & Reschedule")
    print("========================================================")

    call_id = f"conflict-call-sca-{uuid.uuid4().hex[:6]}"
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

    # TURN 1: Caller specifically asks for tomorrow 2:00 PM
    print("Turn 1: Caller asks for tomorrow at 2:00 PM (which is already booked)")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "Hello, I saw your free dental checkup offer. Can I book for tomorrow at 2:00 PM?",
    })

    # TURN 2: Agent checks slot with preferred_time="2:00 PM"
    print("Turn 2: Agent executes live calendar lookup for 2:00 PM...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_find_free_slots",
        "call_id": "fn_check_slot_sca",
        "arguments": json.dumps({"date": "2026-10-07", "preferred_time": "2:00 PM"}),
    })

    slot_resp = extract_output(adapter.started_responses, "fn_check_slot_sca")
    print("-> Live Slot Check Output:", slot_resp)
    # Verification: Tool correctly flagged slot as unavailable
    assert slot_resp.get("status") == "unavailable"
    assert "02:00 PM" in slot_resp.get("requested_slot", "") or "02:00 PM" in slot_resp.get("busy_slots", [])
    assert "02:00 PM" not in slot_resp.get("available_slots", [])
    print("-> Successfully detected slot non-availability!")

    # TURN 3: Agent speaks alternative offer & Caller accepts 4:30 PM
    print("Turn 3: Agent explains 2:00 PM is booked and offers 4:30 PM; Caller accepts")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": f"Ah I see 2:00 PM is taken. 4:30 PM tomorrow is fine. Please book Siddharth Roy at {TEST_EMAIL}.",
    })

    # TURN 4: Agent books open slot at 4:30 PM
    print("Turn 4: Booking open slot at 4:30 PM on Google Calendar...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_create_event",
        "call_id": "fn_book_event_sca",
        "arguments": json.dumps({
            "summary": "Dental Consultation - Siddharth Roy",
            "start": "2026-10-07T16:30:00+05:30",
            "end": "2026-10-07T17:00:00+05:30",
            "attendee_email": TEST_EMAIL,
            "description": "Complimentary Dental Screening - Rescheduled from 2 PM",
        }),
    })

    book_resp = extract_output(adapter.started_responses, "fn_book_event_sca")
    print("-> Live Event Creation Output:", book_resp)
    assert book_resp.get("status") == "confirmed" or book_resp.get("confirmed") is True

    # TURN 5: Confirmation email dispatch
    print("Turn 5: Sending confirmation email via Gmail...")
    await loop._handle_event({
        "type": "function_call",
        "name": "gmail_send_email",
        "call_id": "fn_send_email_sca",
        "arguments": json.dumps({
            "to": TEST_EMAIL,
            "subject": "Smile Dental Clinic - Tomorrow 4:30 PM Appointment Confirmed",
            "body": "Dear Siddharth,\n\nYour appointment is confirmed for tomorrow, Oct 7 at 4:30 PM (rescheduled from 2:00 PM).\n\nSee you then!\nSmile Dental Team",
        }),
    })

    email_resp = extract_output(adapter.started_responses, "fn_send_email_sca")
    print("-> Live Gmail Send Output:", email_resp)
    assert email_resp.get("status") == "sent"


@pytest.mark.asyncio
async def test_scenario_b_friday_morning_collision():
    """Scenario B: Caller requests Friday Oct 9 at 10:00 AM (Already Booked) -> Offered 11:30 AM."""
    print("\n========================================================")
    print("RUNNING SCENARIO B: Friday 10:00 AM Collision")
    print("========================================================")

    call_id = f"conflict-call-scb-{uuid.uuid4().hex[:6]}"
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

    # TURN 1: Caller requests Friday Oct 9 at 10:00 AM
    print("Turn 1: Caller requests Friday Oct 9 at 10:00 AM")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "Hello! Can I schedule my free checkup this Friday Oct 9 at 10:00 AM?",
    })

    # TURN 2: In-call slot check
    print("Turn 2: Agent checks live calendar for 10:00 AM on 2026-10-09...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_find_free_slots",
        "call_id": "fn_check_slot_scb",
        "arguments": json.dumps({"date": "2026-10-09", "preferred_time": "10:00 AM"}),
    })

    slot_resp = extract_output(adapter.started_responses, "fn_check_slot_scb")
    print("-> Live Slot Check Output:", slot_resp)
    # Verification: Tool flagged 10:00 AM as unavailable
    assert slot_resp.get("status") == "unavailable"
    assert "10:00 AM" in slot_resp.get("requested_slot", "") or "10:00 AM" in slot_resp.get("busy_slots", [])

    # TURN 3: Caller chooses 11:30 AM
    print("Turn 3: Caller agrees to open 11:30 AM slot")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": f"Alright, 11:30 AM on Friday works for Meera Nair. Email is {TEST_EMAIL}.",
    })

    # TURN 4: Agent books 11:30 AM
    print("Turn 4: Booking 11:30 AM on Google Calendar...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_create_event",
        "call_id": "fn_book_event_scb",
        "arguments": json.dumps({
            "summary": "Dental Consultation - Meera Nair",
            "start": "2026-10-09T11:30:00+05:30",
            "end": "2026-10-09T12:00:00+05:30",
            "attendee_email": TEST_EMAIL,
            "description": "Free Oral Health Examination",
        }),
    })

    book_resp = extract_output(adapter.started_responses, "fn_book_event_scb")
    print("-> Live Event Creation Output:", book_resp)
    assert book_resp.get("status") == "confirmed" or book_resp.get("confirmed") is True

    # TURN 5: Gmail Send
    print("Turn 5: Sending email via Gmail...")
    await loop._handle_event({
        "type": "function_call",
        "name": "gmail_send_email",
        "call_id": "fn_send_email_scb",
        "arguments": json.dumps({
            "to": TEST_EMAIL,
            "subject": "Smile Dental Clinic - Friday 11:30 AM Confirmed",
            "body": "Dear Meera,\n\nYour appointment is confirmed for Friday, Oct 9 at 11:30 AM.\n\nWarm regards,\nSmile Dental Team",
        }),
    })

    email_resp = extract_output(adapter.started_responses, "fn_send_email_scb")
    assert email_resp.get("status") == "sent"


@pytest.mark.asyncio
async def test_scenario_c_blind_double_booking_prevention():
    """Scenario C: Direct Double Booking Attempt Rejection & Real-Time Recovery."""
    print("\n========================================================")
    print("RUNNING SCENARIO C: Direct Double Booking Rejection")
    print("========================================================")

    call_id = f"conflict-call-scc-{uuid.uuid4().hex[:6]}"
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

    # TURN 1: Caller immediately demands 3:30 PM tomorrow (which was already booked)
    print("Turn 1: Caller demands 3:30 PM tomorrow without checking availability")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "Please book me immediately for tomorrow at 3:30 PM under Arjun Kapoor.",
    })

    # TURN 2: Agent attempts to book 3:30 PM -> Conflict Caught!
    print("Turn 2: Attempting booking at 3:30 PM (Pre-booking conflict engine activates)...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_create_event",
        "call_id": "fn_book_conflict_scc",
        "arguments": json.dumps({
            "summary": "Dental Consultation - Arjun Kapoor",
            "start": "2026-10-07T15:30:00+05:30",
            "end": "2026-10-07T16:00:00+05:30",
            "attendee_email": TEST_EMAIL,
        }),
    })

    book_resp = extract_output(adapter.started_responses, "fn_book_conflict_scc")
    print("-> Conflict Engine Response:", book_resp)
    # Verification: Booking rejected with conflict status
    assert book_resp.get("status") == "conflict"
    assert book_resp.get("confirmed") is False
    assert book_resp.get("error") == "slot_already_booked"
    print("-> Successfully blocked double-booking attempt!")

    # TURN 3: Caller adjusts to alternative (10:00 AM)
    print("Turn 3: Agent explains conflict; Caller adjusts to 10:00 AM")
    await loop._handle_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": f"Understood. Let's do 10:00 AM tomorrow instead. Email is {TEST_EMAIL}.",
    })

    # TURN 4: Agent books 10:00 AM
    print("Turn 4: Booking 10:00 AM on Google Calendar...")
    await loop._handle_event({
        "type": "function_call",
        "name": "googlecalendar_create_event",
        "call_id": "fn_book_success_scc",
        "arguments": json.dumps({
            "summary": "Dental Consultation - Arjun Kapoor",
            "start": "2026-10-07T10:00:00+05:30",
            "end": "2026-10-07T10:30:00+05:30",
            "attendee_email": TEST_EMAIL,
            "description": "Free Dental Examination",
        }),
    })

    book_success = extract_output(adapter.started_responses, "fn_book_success_scc")
    print("-> Event Creation Output:", book_success)
    assert book_success.get("status") == "confirmed" or book_success.get("confirmed") is True

    # TURN 5: Gmail Send
    print("Turn 5: Sending confirmation email via Gmail...")
    await loop._handle_event({
        "type": "function_call",
        "name": "gmail_send_email",
        "call_id": "fn_send_email_scc",
        "arguments": json.dumps({
            "to": TEST_EMAIL,
            "subject": "Smile Dental Clinic - Tomorrow 10:00 AM Confirmed",
            "body": "Dear Arjun,\n\nYour appointment is confirmed for tomorrow, Oct 7 at 10:00 AM.\n\nBest,\nSmile Dental Team",
        }),
    })

    email_resp = extract_output(adapter.started_responses, "fn_send_email_scc")
    assert email_resp.get("status") == "sent"

    print("\nALL 3 SLOT CONFLICT & NON-AVAILABILITY SCENARIOS PASSED WITH LIVE INTEGRATIONS!")
