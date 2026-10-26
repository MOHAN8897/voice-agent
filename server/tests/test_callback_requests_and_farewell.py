"""Durable future callbacks and exact, published server farewell delivery."""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import JSON, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.call.call_end_policy import (
    apply_call_end_policy,
    callback_save_failed_for,
    policy_from_brain,
    policy_from_sections,
    server_farewell_for,
)
from server.db.models.entities import Call, CallCallback
from server.services.saas import callback_request_service as svc
from server.services.saas.tenant_guard import SubscriberPrincipal


@pytest.fixture
async def callback_db(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'callbacks.db'}")
    # SQLite test adapter only; production uses the existing PostgreSQL tables.
    columns = [c for table in (Call.__table__, CallCallback.__table__) for c in table.columns if isinstance(c.type, ARRAY)]
    original = [c.type for c in columns]
    for c in columns:
        c.type = JSON()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync: Call.__table__.create(sync))
            await conn.run_sync(lambda sync: CallCallback.__table__.create(sync))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(svc, "get_session_factory", lambda: factory)
        principal = SubscriberPrincipal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="customer_admin", email="test@example.invalid")
        ctx = SimpleNamespace(call_id=str(uuid.uuid4()), tenant_id=str(principal.tenant_id), agent_id=str(uuid.uuid4()),
                              callback_phone="+12025550123", callback_when="next month", callback_request_text="Please call me next month", call_end_policy={"farewell": "Thank you for your time. Take care."})
        async with factory() as session:
            session.add(Call(call_id=uuid.UUID(ctx.call_id), tenant_id=principal.tenant_id, agent_id=uuid.UUID(ctx.agent_id), combination_id="test", storage_path="test", status_tags=[]))
            await session.commit()
        yield factory, principal, ctx
    finally:
        await engine.dispose()
        for c, original_type in zip(columns, original):
            c.type = original_type


async def test_requested_callback_is_durable_idempotent_and_does_not_dial(callback_db):
    factory, principal, ctx = callback_db
    saved = await svc.record_callback_request(ctx, ctx.callback_request_text)
    assert saved == await svc.record_callback_request(ctx, ctx.callback_request_text)
    async with factory() as session:
        rows = (await session.execute(select(CallCallback))).scalars().all()
        assert len(rows) == 1
        assert rows[0].mode == rows[0].status == "requested"
        assert rows[0].provider_call_control_id is None
    items = await svc.list_callback_requests(principal, agent_id=ctx.agent_id)
    assert items[0]["requestedWhen"] == "next month"
    assert items[0]["requestText"] == ctx.callback_request_text
    assert await svc.list_callback_requests(principal, agent_id="different") == []


@pytest.mark.parametrize("status", ["converted", "dismissed"])
async def test_tenant_can_clear_request_without_deleting_audit(callback_db, status):
    _, principal, ctx = callback_db
    saved = await svc.record_callback_request(ctx, ctx.callback_request_text)
    updated = await svc.update_callback_request(principal, uuid.UUID(saved["id"]), status)
    assert updated["status"] == status
    assert await svc.list_callback_requests(principal) == []
    assert len(await svc.list_callback_requests(principal, status=status)) == 1


async def test_callback_queue_is_tenant_scoped(callback_db):
    _, _principal, ctx = callback_db
    saved = await svc.record_callback_request(ctx, ctx.callback_request_text)
    foreign = SubscriberPrincipal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="customer_admin", email="other@example.invalid")
    assert await svc.list_callback_requests(foreign) == []
    with pytest.raises(HTTPException) as error:
        await svc.update_callback_request(foreign, uuid.UUID(saved["id"]), "converted")
    assert error.value.status_code == 404
    ctx.tenant_id = str(foreign.tenant_id)
    assert await svc.record_callback_request(ctx, ctx.callback_request_text) is None


async def test_callback_is_saved_before_confirmation_and_custom_farewell(callback_db):
    _, principal, ctx = callback_db
    result = await svc.prepare_callback_close(ctx, {"should_end": True, "contact_preference": "callback"}, "en-IN", ctx.callback_request_text)
    assert "I've saved your details" in result["farewell"]
    assert result["farewell"].endswith(ctx.call_end_policy["farewell"])
    assert len(await svc.list_callback_requests(principal)) == 1


async def test_reported_telugu_call_closes_with_saved_callback_and_full_farewell(callback_db, monkeypatch):
    from server.call.call_ledger import call_ledger
    from server.call.close_call_executor import execute_agent_close
    from server.call.live_turn_orchestrator import live_turn_orchestrator

    _, principal, ctx = callback_db
    ctx.session_id, ctx.status = "callback-regression", "active"
    ctx.agent_hangup_armed = False
    ctx.callback_request_text = ""
    ctx.callback_close_phase = "idle"
    ctx.call_end_policy = {"farewell": "మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం."}
    monkeypatch.setattr("server.call.call_context.get", lambda call_id: ctx if call_id == ctx.call_id else None)
    caller = "ఆహా ఇప్పుడైతే వద్దు నెక్స్ట్ మంత్ కావాలి మీరేమన్నా నెక్స్ట్ మంత్ మళ్ళీ కాల్ చేస్తారా నాకు"
    decision = live_turn_orchestrator._gate_end_call(
        {"decision": "close", "reason": "goal_complete", "evidence": caller},
        transcript=caller, language_code="te-IN", call_id=ctx.call_id,
    )
    assert decision["should_end"] and decision["contact_preference"] == "callback"
    decision = await svc.prepare_callback_close(ctx, decision, "te-IN", caller)
    assert decision["farewell"].endswith(ctx.call_end_policy["farewell"])
    assert len(await svc.list_callback_requests(principal)) == 1
    events = []

    async def speak():
        events.append(decision["farewell"])

    async def disconnect():
        assert events == [decision["farewell"]]
        assert len(await svc.list_callback_requests(principal)) == 1
        events.append("carrier_ack")

    result = await execute_agent_close(
        call_id=ctx.call_id, reason=decision["reason"], flush_audio=speak,
        is_playing=lambda: False, on_provider_hangup=disconnect, end_lifecycle=False, trail_sec=0,
    )
    await result.background_task
    assert events[-1] == "carrier_ack"
    assert call_ledger.read_meta(ctx.call_id)["hangup_outcome"] == "agent_ended"


@pytest.mark.parametrize("language", ["en-IN", "te-IN", "hi-IN", "ta-IN", "kn-IN"])
async def test_failed_save_never_claims_callback_noted(monkeypatch, language):
    monkeypatch.setattr(svc, "record_callback_request", AsyncMock(return_value=None))
    result = await svc.prepare_callback_close(None, {"should_end": True, "contact_preference": "callback"}, language, "call later")
    assert result["farewell"].startswith(callback_save_failed_for(language))
    assert result["contact_preference"] == "callback"  # Preserve intent even if storage failed.


@pytest.mark.parametrize("farewell", ["Thank you for your time. Goodbye.", "మీ సమయం ఇచ్చినందుకు ధన్యవాదాలు. నమస్కారం.", "Thanks.\nTake care."])
def test_farewell_survives_compile_and_refresh_exactly(farewell):
    from server.brain.compiled_brain_artifact import (
        assemble_unified_brain,
        refresh_platform_sections,
    )
    policy = policy_from_sections([{"title": "saas_call_end_policy", "enabled": False, "raw_text": json.dumps({"farewell": farewell})}], "te-IN")
    brain = apply_call_end_policy(assemble_unified_brain(language="te-IN", script="Answer approved business questions."), "te-IN", policy)
    refreshed = refresh_platform_sections(brain, "te-IN")
    assert policy_from_brain(refreshed, "te-IN")["farewell"] == farewell
    assert server_farewell_for("te-IN", policy=policy) == farewell


def test_overlong_farewell_is_rejected_not_truncated():
    with pytest.raises(ValueError, match="240"):
        policy_from_sections([{"title": "saas_call_end_policy", "raw_text": json.dumps({"farewell": "x" * 241})}], "en-IN")


def test_business_script_cannot_shadow_published_farewell():
    from server.brain.compiled_brain_artifact import assemble_unified_brain

    brain = assemble_unified_brain(language="en-IN", script='Farewell text (JSON): "wrong line"')
    brain = apply_call_end_policy(brain, "en-IN", {"farewell": "Approved closing words."})
    assert policy_from_brain(brain, "en-IN")["farewell"] == "Approved closing words."


def test_custom_farewell_requires_review_after_language_change():
    from server.brain.compiled_brain_artifact import (
        assemble_unified_brain,
        refresh_platform_sections,
    )

    brain = apply_call_end_policy(assemble_unified_brain(language="en-IN", script="Answer questions."), "en-IN", {"farewell": "A custom goodbye."})
    with pytest.raises(ValueError, match="reviewed"):
        refresh_platform_sections(brain, "te-IN")


@pytest.mark.parametrize("exact_artifact", [False, True])
async def test_publication_and_recompile_use_approved_farewell(monkeypatch, exact_artifact):
    from server.brain.agent_service import agent_service
    from server.brain.business_brain_store import business_brain_store
    from server.brain.compiled_brain_artifact import assemble_unified_brain
    from server.brain.compiled_brain_service import compiled_brain_service

    agent = await agent_service.ensure_default_agent()
    agent_id = agent["agent_id"]
    sections = await business_brain_store.ensure_default_sections(agent_id)
    sections = [s for s in sections if s["title"] != "saas_call_end_policy"]
    farewell = "Thank you for your time. We appreciate speaking with you. Goodbye."
    sections.append({"type": "custom", "title": "saas_call_end_policy", "raw_text": json.dumps({"farewell": farewell}), "enabled": False})
    script = "--- AGENT IDENTITY ---\nYou are a support representative. Answer approved questions."
    prompt = assemble_unified_brain(language=await compiled_brain_service._primary_language(agent_id), script=script) if exact_artifact else script
    published = await compiled_brain_service.publish_agent_brain(agent_id, sections=sections, optimized_prompt=prompt)
    assert policy_from_brain(published["compiled_text"], "en-IN")["farewell"] == farewell
    sections = await business_brain_store.get_sections(agent_id)
    for section in sections:
        if section["title"] == "saas_call_end_policy":
            section["raw_text"] = json.dumps({"farewell": "UNPUBLISHED EDIT"})
    await business_brain_store.save_draft_sections(agent_id, sections)
    compiled = await compiled_brain_service.compile_for_agent(agent_id)
    assert policy_from_brain(compiled["compiled_text"], "en-IN")["farewell"] == farewell
    assert "UNPUBLISHED EDIT" not in compiled["compiled_text"]
