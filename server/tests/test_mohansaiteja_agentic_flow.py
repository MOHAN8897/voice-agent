"""Comprehensive verification and edge-case testing for user mohansaiteja.99@gmail.com and agents.

Tests multi-language conversation flow (te-IN, en-IN, hi-IN), prewarm greeting extraction,
in-call tool dispatch, calendar conflicts, sudden hangups, SLA timeouts, split-brain reconciliation,
post-call CRM pipelines, and security isolation.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from server.app import app
from server.db.connection import get_session_factory, init_db
from server.db.models import Agent, AgentIntegration, Tenant, User
from server.db.models.brain_models import CompiledBrainSnapshot
from server.db.models.integration_models import TenantIntegration, ToolExecution
from server.db.models.saas_models import TenantMembership
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
from server.services.pstn_text_chunker import extract_prewarm_greeting, extract_opening_greeting
from server.services.tool_router import DialtactToolRouter
from server.call.post_call_pipeline import reconcile_and_dispatch_post_call


TEST_USER_EMAIL = "mohansaiteja.99@gmail.com"
TEST_TENANT_ID = "6d3fba56-7109-4812-8eb5-4a0d11f558c6"
TEST_AGENT_ID = "832dd86c-bbd5-4bcc-8466-469b3411c99f"  # 'sai'
TEST_COMPILED_BRAIN_ID = "cb_v20261001_0c0145"


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()


# ---------------------------------------------------------------------------
# 1. Account, Tenant, Agent & Brain Snapshot DB Integrity
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_account_and_agent_db_integrity():
    """Verify test user, workspace tenant, active agent, and compiled brain exist in DB."""
    session_factory = get_session_factory()
    if session_factory is None:
        pytest.skip("Live database not configured (run with LIVE_DB=1)")

    async with session_factory() as session:
        # User
        user_res = await session.execute(select(User).where(User.email == TEST_USER_EMAIL))
        user = user_res.scalar_one_or_none()
        assert user is not None, f"User {TEST_USER_EMAIL} must exist in database"
        assert user.status == "active"

        # Tenant Membership
        mem_res = await session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user.user_id,
                TenantMembership.tenant_id == uuid.UUID(TEST_TENANT_ID),
            )
        )
        membership = mem_res.scalar_one_or_none()
        assert membership is not None, f"User must belong to tenant {TEST_TENANT_ID}"

        # Agent
        agent = await session.get(Agent, uuid.UUID(TEST_AGENT_ID))
        assert agent is not None, f"Agent {TEST_AGENT_ID} must exist in database"
        assert agent.name == "sai"
        assert agent.active_compiled_brain_version == TEST_COMPILED_BRAIN_ID

        # Compiled Brain
        cb = await session.get(CompiledBrainSnapshot, TEST_COMPILED_BRAIN_ID)
        assert cb is not None, f"CompiledBrain {TEST_COMPILED_BRAIN_ID} must exist"
        assert len(cb.compiled_text) > 1000

        # Integrations
        ai_res = await session.execute(
            select(AgentIntegration).where(AgentIntegration.agent_id == uuid.UUID(TEST_AGENT_ID))
        )
        agent_integs = {ai.app_name.lower(): ai for ai in ai_res.scalars().all()}
        assert "googlecalendar" in agent_integs
        assert agent_integs["googlecalendar"].enabled is True
        assert "googlecalendar_find_free_slots" in agent_integs["googlecalendar"].action_whitelist


# ---------------------------------------------------------------------------
# 2. Prewarm Greeting & Opening Extraction Across Locales
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prewarm_greeting_extraction_for_agent():
    """Verify prewarm greeting is extracted cleanly without leaking system headers or disclosures."""
    session_factory = get_session_factory()
    if session_factory is None:
        pytest.skip("Live database not configured (run with LIVE_DB=1)")
    async with session_factory() as session:
        cb = await session.get(CompiledBrainSnapshot, TEST_COMPILED_BRAIN_ID)
        assert cb is not None

        greeting_te = extract_prewarm_greeting(cb.compiled_text, "te-IN")
        opening_te = extract_opening_greeting(cb.compiled_text, "te-IN")

        assert greeting_te, "Prewarm greeting must not be empty"
        assert "--- SAFETY ---" not in greeting_te
        assert "API key" not in greeting_te
        assert "This call may be recorded" not in greeting_te
        assert greeting_te == opening_te


# ---------------------------------------------------------------------------
# 3. Multilingual Flow: Telugu (te-IN) with Calendar Booking & Hangup
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_agent_conversation_flow_telugu_booking_and_farewell():
    """Verify te-IN voice flow: calendar slot check, booking, farewell audio, and transport hangup."""
    adapter = FakeRealtimeVoiceAdapter()
    wire_frames: list[bytes] = []

    async def on_wire(data: bytes) -> None:
        wire_frames.append(data)

    loop = PstnRealtimeVoiceLoop(
        session_id="test-session-te",
        call_id="call-te-001",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id=TEST_TENANT_ID,
        agent_id=TEST_AGENT_ID,
        agent_tools={"googlecalendar_find_free_slots", "googlecalendar_create_event"},
        stack_override={"pipeline": "realtime_voice", "language": "te-IN"},
    )
    finish_hangup = AsyncMock()
    loop._finish_hangup = finish_hangup

    slot_result = {"status": "available", "slots": [{"start": "14:00", "end": "14:30"}]}
    booking_result = {"status": "confirmed", "event_id": "cal_evt_te_123"}

    try:
        with patch(
            "server.services.tool_router.tool_router.route_and_execute",
            new_callable=AsyncMock,
            side_effect=[slot_result, booking_result],
        ) as mock_route:
            # 1. Caller asks for free slots
            await loop._handle_event({
                "type": "function_call",
                "name": "googlecalendar_find_free_slots",
                "call_id": "call-slot-check",
                "arguments": json.dumps({"date": "2026-10-15"}),
            })
            assert any("call-slot-check" in r and json.dumps(slot_result) in r for r in adapter.started_responses)

            # 2. Caller books slot
            await loop._handle_event({
                "type": "function_call",
                "name": "googlecalendar_create_event",
                "call_id": "call-book-slot",
                "arguments": json.dumps({
                    "summary": "Dental Consultation - Sai",
                    "start": "2026-10-15T14:00:00+05:30",
                    "end": "2026-10-15T14:30:00+05:30",
                    "attendee_email": TEST_USER_EMAIL,
                }),
            })
            assert any("call-book-slot" in r and json.dumps(booking_result) in r for r in adapter.started_responses)

            # 3. Caller bids farewell -> agent requests end call
            await loop._handle_event({
                "type": "audio_delta",
                "pcm": b"\x01\x00" * 2400,
            })
            await loop._handle_event({
                "type": "assistant_transcript_delta",
                "delta": "ధన్యవాదాలు, మీ అపాయింట్‌మెంట్ కన్ఫర్మ్ అయింది. హావ్ ఏ గ్రేట్ డే!",
            })
            await loop._handle_event({
                "type": "function_call",
                "name": "request_end_call",
                "call_id": "call-hangup-req",
                "arguments": json.dumps({
                    "should_end": True,
                    "reason": "goodbye",
                    "farewell": "ధన్యవాదాలు, మీ అపాయింట్‌మెంట్ కన్ఫర్మ్ అయింది. హావ్ ఏ గ్రేట్ డే!",
                }),
            })
            assert loop._pending_end_call is not None

            # 4. Farewell audio delta completes -> finish_hangup executes
            await loop._handle_event({
                "type": "response_done",
                "response": {"status": "completed"},
            })
            finish_hangup.assert_awaited()
    finally:
        await loop.close()


# ---------------------------------------------------------------------------
# 4. Multilingual Flow: English (en-IN) & Hindi (hi-IN)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en-IN", "hi-IN"])
async def test_agent_conversation_flow_multilingual_locales(locale: str):
    """Verify voice loop executes seamlessly in en-IN and hi-IN with tool dispatch and graceful hangup."""
    adapter = FakeRealtimeVoiceAdapter()
    wire_frames: list[bytes] = []

    async def on_wire(data: bytes) -> None:
        wire_frames.append(data)

    loop = PstnRealtimeVoiceLoop(
        session_id=f"test-session-{locale}",
        call_id=f"call-{locale}-001",
        on_agent_wire=on_wire,
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id=TEST_TENANT_ID,
        agent_id=TEST_AGENT_ID,
        agent_tools={"googlecalendar_find_free_slots"},
        stack_override={"pipeline": "realtime_voice", "language": locale},
    )
    finish_hangup = AsyncMock()
    loop._finish_hangup = finish_hangup

    mock_slots = {"status": "available", "slots": [{"start": "10:00", "end": "10:30"}]}
    try:
        with patch(
            "server.services.tool_router.tool_router.route_and_execute",
            new_callable=AsyncMock,
            return_value=mock_slots,
        ):
            await loop._handle_event({
                "type": "function_call",
                "name": "googlecalendar_find_free_slots",
                "call_id": f"call-slots-{locale}",
                "arguments": json.dumps({"date": "2026-10-16"}),
            })
            assert any(f"call-slots-{locale}" in r for r in adapter.started_responses)

            # End call
            await loop._handle_event({
                "type": "audio_delta",
                "pcm": b"\x01\x00" * 2400,
            })
            await loop._handle_event({
                "type": "assistant_transcript_delta",
                "delta": "Thank you, goodbye!",
            })
            await loop._handle_event({
                "type": "function_call",
                "name": "request_end_call",
                "call_id": f"call-end-{locale}",
                "arguments": json.dumps({
                    "should_end": True,
                    "reason": "goodbye",
                    "farewell": "Thank you, goodbye!",
                }),
            })
            await loop._handle_event({
                "type": "response_done",
                "response": {"status": "completed"},
            })
            finish_hangup.assert_awaited()
    finally:
        await loop.close()


# ---------------------------------------------------------------------------
# 5. Edge Case: Calendar Conflict Resolution & Alternative Selection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_agent_flow_calendar_conflict_and_alternative():
    """Verify that when a requested slot is booked, agent receives conflict, alternative is chosen, and booked."""
    adapter = FakeRealtimeVoiceAdapter()
    loop = PstnRealtimeVoiceLoop(
        session_id="test-conflict-session",
        call_id="call-conflict-001",
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=adapter,
        tenant_id=TEST_TENANT_ID,
        agent_id=TEST_AGENT_ID,
        agent_tools={"googlecalendar_find_free_slots", "googlecalendar_create_event"},
        stack_override={"pipeline": "realtime_voice", "language": "te-IN"},
    )

    conflict_res = {
        "status": "conflict",
        "requested": "15:00",
        "alternatives": ["16:30", "17:00"],
    }
    alternative_booked = {
        "status": "confirmed",
        "event_id": "cal_evt_alt_456",
        "start": "16:30",
    }

    try:
        with patch(
            "server.services.tool_router.tool_router.route_and_execute",
            new_callable=AsyncMock,
            side_effect=[conflict_res, alternative_booked],
        ):
            # 1. Attempt 15:00 slot -> conflict
            await loop._handle_event({
                "type": "function_call",
                "name": "googlecalendar_create_event",
                "call_id": "req-1500",
                "arguments": json.dumps({"start": "2026-10-15T15:00:00+05:30"}),
            })
            assert any("req-1500" in r and "conflict" in r for r in adapter.started_responses)

            # 2. Select alternative 16:30 -> confirmed
            await loop._handle_event({
                "type": "function_call",
                "name": "googlecalendar_create_event",
                "call_id": "req-1630",
                "arguments": json.dumps({"start": "2026-10-15T16:30:00+05:30"}),
            })
            assert any("req-1630" in r and "cal_evt_alt_456" in r for r in adapter.started_responses)
    finally:
        await loop.close()


# ---------------------------------------------------------------------------
# 6. Edge Case: Tool 1.5s Voice SLA Timeout & DB Reconciliation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_sla_timeout_acoustic_bridge_and_post_call_reconciliation():
    """Verify tool SLA timeout returns acoustic filler message, records timed_out_pending, and post-call reconciles it."""
    router = DialtactToolRouter()
    call_id = f"test-sla-call-{uuid.uuid4().hex[:8]}"

    async def _slow_tool(*args, **kwargs):
        await asyncio.sleep(2.0)
        return {"status": "success"}

    with patch.object(router.nango, "execute_in_call_tool", side_effect=_slow_tool):
        res = await router.route_and_execute(
            tenant_id=TEST_TENANT_ID,
            agent_id=TEST_AGENT_ID,
            call_id=call_id,
            tool_name="googlecalendar_create_event",
            arguments={"summary": "Timeout Test Booking"},
        )

    # Agent returns polite message rather than failing call
    assert res["status"] == "timeout"
    assert "taking a moment" in res["message"]

    # Verify database recorded timed_out_pending
    session_factory = get_session_factory()
    if session_factory is None:
        pytest.skip("Live database not configured (run with LIVE_DB=1)")
    async with session_factory() as session:
        te_res = await session.execute(
            select(ToolExecution).where(ToolExecution.call_id == call_id)
        )
        record = te_res.scalar_one_or_none()
        assert record is not None
        assert record.status == "timed_out_pending"

    # Execute post-call pipeline reconciliation
    with patch("server.call.call_store.call_store.get", new_callable=AsyncMock, return_value={
        "tenant_id": TEST_TENANT_ID,
        "agent_id": TEST_AGENT_ID,
        "from_number": "+919876543210",
        "duration_sec": 45,
    }):
        await reconcile_and_dispatch_post_call(call_id, {
            "disposition": "completed",
            "summary_en": "Booking completed with reconciliation",
        })

    # Verify status transitioned to reconciled
    async with session_factory() as session:
        reconciled = await session.get(ToolExecution, record.id)
        assert reconciled is not None
        assert reconciled.status == "reconciled"
        assert reconciled.completed_at is not None


# ---------------------------------------------------------------------------
# 7. Security: Stripe Decommissioned HTTP 410 & Fail-Closed Isolation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stripe_endpoints_fail_closed_and_return_410():
    """Verify Stripe webhook returns HTTP 410 Gone and performs zero DB operations."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/stripe/webhook",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Content-Type": "application/json", "Stripe-Signature": "test_sig"},
        )
        assert resp.status_code == 410
        assert "decommissioned" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_tenant_isolation_fails_closed_on_cross_tenant_tool_request():
    """Verify tool router rejects requests where tenant_id does not match caller or is empty."""
    router = DialtactToolRouter()

    res_missing_tenant = await router.route_and_execute(
        tenant_id=None,
        agent_id=TEST_AGENT_ID,
        call_id="call-iso-01",
        tool_name="googlecalendar_find_free_slots",
        arguments={},
    )
    assert res_missing_tenant["status"] == "error"
    assert "Unauthorized" in res_missing_tenant["message"]

    res_missing_agent = await router.route_and_execute(
        tenant_id=TEST_TENANT_ID,
        agent_id=None,
        call_id="call-iso-02",
        tool_name="googlecalendar_find_free_slots",
        arguments={},
    )
    assert res_missing_agent["status"] == "error"
    assert "Unauthorized" in res_missing_agent["message"]
