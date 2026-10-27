"""Provider regressions and CRM boundaries, without real calls or payments."""
import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.call.live_turn_orchestrator import LiveTurnOrchestrator
from server.call.outcome_schema import derive_status_tags, normalize_custom_tags
from server.db.models.entities import Base
from server.db.models.saas_models import Lead
from server.providers.llm_protocol import IncompleteTurnError
from server.routes import app_leads
from server.services import gnani_tts_ws
from server.services.saas import lead_sync
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.tests.test_close_classifier_handoff import run_voice_simulation
from server.tests.test_integration_security_hardening import AID, TID
from server.tests.test_integration_security_hardening import db as shared_db

db = shared_db


def test_documented_gnani_hinglish_route_is_not_silently_changed_to_hindi():
    from server.providers.voice_inventory import provider_language

    assert gnani_tts_ws._gnani_language_code("hi-en", model="timbre-v3.0") == "hi-en"
    assert provider_language("gnani", "timbre-v3.0", "Shivani", "hi-en") == "hi-en"


@pytest.mark.parametrize("language,user,closing", [
    ("te-IN", "అంతే అంతే థ్యాంక్ యూ", True),
    ("en-IN", "that's all I needed", True),
    ("hi-IN", "बस इतना ही धन्यवाद", True),
    ("ta-IN", "அவ்வளவுதான் நன்றி", True),
    ("kn-IN", "ಇಷ್ಟೇ ಸಾಕು ಧನ್ಯವಾದಗಳು", True),
    ("te-IN", "ధర ఎంత?", False),
    ("en-IN", "thanks, but one more question", False),
])
async def test_empty_provider_reply_still_uses_server_close_gate(monkeypatch, language, user, closing):
    result = await run_voice_simulation(monkeypatch, language, user, closing, empty_speech=True)
    assert result["spoken"], result
    assert result["hangup_commands"] == int(closing), result


async def test_contextual_empty_reply_recovery_reaches_speech_without_hangup(monkeypatch):
    line = "సరే, మళ్లీ మాట్లాడటానికి మీకు ఏ సమయం అనుకూలంగా ఉంటుంది?"
    result = await run_voice_simulation(monkeypatch, "te-IN", "నేను బిజీగా ఉన్నాను. తర్వాత మాట్లాడదాం.", False, empty_speech=True, recovered_text=line)
    assert result["spoken"] == [line]
    assert result["hangup_commands"] == 0


@pytest.mark.parametrize("output", ["What day would suit you?", '{"decision":"close"}', ""])
async def test_empty_speech_recovery_pins_model_and_cannot_emit_control_json(monkeypatch, output):
    from server.call.speech_recovery import recover_empty_speech
    from server.providers.base import StageSelection

    calls = []
    usage = {"input_tokens": 100, "output_tokens": 12, "total_tokens": 112}

    class Adapter:
        provider_id = "sarvam"

        async def stream_live_turn(self, **kwargs):
            calls.append(kwargs)
            yield {"done": True, "text": output, "usage": usage}

    registry = SimpleNamespace(is_provider_enabled=lambda *args: True, is_model_allowed=lambda *args: True, get_llm=lambda *args: Adapter())
    recorded = []
    monkeypatch.setattr("server.providers.get_provider_registry", lambda: registry)
    monkeypatch.setattr("server.services.saas.composed_costing.record_composed_stage_usage", lambda *args: recorded.append(args))
    selected = StageSelection("sarvam", "sarvam-105b-conversations", {"api_mode": "chat_completions_v1"})
    text = await recover_empty_speech(llm=selected, language="te-IN", transcript="I am busy, call later", agent_previous="How may I help?", call_id="synthetic-recovery")
    assert text == (output if output.startswith("What") else "")
    assert len(calls) == 1 and calls[0]["model"] == selected.model
    assert calls[0]["reasoning_effort"] is None and calls[0]["max_output_tokens"] == 128
    assert len(calls[0]["input_messages"]) == 2 and "tools" not in calls[0]
    assert recorded and recorded[0][:2] == ("synthetic-recovery", "llm")


@pytest.mark.parametrize("failure", ["incomplete", "stall", "disabled"])
async def test_empty_speech_recovery_has_a_deadline_and_no_provider_fallback(monkeypatch, failure):
    from server.call import speech_recovery
    from server.providers.base import StageSelection

    calls = []

    class Adapter:
        provider_id = "sarvam"

        async def stream_live_turn(self, **kwargs):
            calls.append(kwargs)
            if failure == "incomplete":
                raise IncompleteTurnError(provider="sarvam", finish_reason="length", partial_text="unusable")
            await asyncio.Event().wait()
            yield  # async generator

    registry = SimpleNamespace(is_provider_enabled=lambda *args: failure != "disabled", is_model_allowed=lambda *args: True, get_llm=lambda *args: Adapter())
    monkeypatch.setattr("server.providers.get_provider_registry", lambda: registry)
    real_timeout = asyncio.timeout
    monkeypatch.setattr(speech_recovery.asyncio, "timeout", lambda seconds: real_timeout(0.01))
    selected = StageSelection("sarvam", "sarvam-105b-conversations", {})
    result = await speech_recovery.recover_empty_speech(llm=selected, language="en-IN", transcript="Later please", agent_previous="Hello")
    assert result == ""
    assert len(calls) == (0 if failure == "disabled" else 1)


async def test_completed_empty_speech_does_not_resend_the_full_brain():
    calls = []

    class Adapter:
        uses_plain_live_speech = True

        async def stream_live_turn(self, **kwargs):
            calls.append(kwargs)
            raise IncompleteTurnError(provider="sarvam", finish_reason="stop", partial_text="", usage={"input_tokens": 5000, "output_tokens": 71})
            yield  # async generator

    events = [event async for event in LiveTurnOrchestrator()._stream_composed_speech(
        adapter=Adapter(), messages=[{"role": "user", "content": "I'm busy, call later."}],
        schema=None, stream_kwargs={"model": "sarvam-105b-conversations"},
        call_id=None, provider="sarvam", model="sarvam-105b-conversations")]
    assert len(calls) == 1
    assert events[-1]["empty_provider_response"]
    assert events[-1]["usage"] == {"input_tokens": 5000, "output_tokens": 71, "total_tokens": 5071}
    assert all(call["model"] == "sarvam-105b-conversations" for call in calls)


async def test_gnani_empty_error_list_and_next_turn_preserve_previous_tail(monkeypatch):
    incoming = asyncio.Queue()
    ws = SimpleNamespace(send=AsyncMock(), recv=incoming.get, close=AsyncMock())
    monkeypatch.setattr(gnani_tts_ws.websockets, "connect", AsyncMock(return_value=ws))
    monkeypatch.setattr(gnani_tts_ws, "_gnani_api_key", lambda: "synthetic")
    async with gnani_tts_ws.connect_gnani_tts_ws(model="timbre-v3.0") as proxy:
        await proxy.send(json.dumps({"type": "text", "data": {"text": "First response."}}))
        await proxy.send(json.dumps({"type": "flush"}))
        second = asyncio.create_task(proxy.send(json.dumps({"type": "text", "data": {"text": "Next response."}})))
        pcm = b"\x01\x00" * 30
        await incoming.put(json.dumps({"type": "audio", "errors": [], "data": {"audio": base64.b64encode(pcm).decode()}}))
        await incoming.put(json.dumps({"type": "complete"}))
        await asyncio.wait_for(second, 1)
        assert ws.send.await_count == 2
        first = json.loads(await asyncio.wait_for(proxy.__anext__(), 1))
        assert base64.b64decode(first["data"]["audio"]) == pcm
        assert json.loads(await proxy.__anext__())["type"] == "end_of_stream"
        await incoming.put(json.dumps({"type": "complete"}))


async def test_gnani_wait_deadline_tracks_progress_instead_of_cutting_long_audio(monkeypatch):
    incoming = asyncio.Queue()
    ws = SimpleNamespace(send=AsyncMock(), recv=incoming.get, close=AsyncMock())
    monkeypatch.setattr(gnani_tts_ws.websockets, "connect", AsyncMock(return_value=ws))
    monkeypatch.setattr(gnani_tts_ws, "_gnani_api_key", lambda: "synthetic")
    settings = gnani_tts_ws.get_settings().model_copy(update={"request_timeout_ms": 100})
    monkeypatch.setattr(gnani_tts_ws, "get_settings", lambda: settings)
    async with gnani_tts_ws.connect_gnani_tts_ws(model="timbre-v3.0") as proxy:
        await proxy.send(json.dumps({"type": "text", "data": {"text": "Long response."}}))
        second = asyncio.create_task(proxy.send(json.dumps({"type": "text", "data": {"text": "Next."}})))
        for _ in range(5):
            await asyncio.sleep(0.04)
            await incoming.put(b"\x01\x00" * 3)
        await incoming.put(json.dumps({"type": "complete"}))
        await asyncio.wait_for(second, 1)
        assert ws.send.await_count == 2


def test_custom_tags_are_multilingual_idempotent_and_exclude_contact_data():
    raw = ["Solar Rooftop", "తెలుగు సేవ", "हिंदी", "custom:solar-rooftop", "person@example.invalid", "+1 202 555 0199", {"bad": "tag"}]
    tags = normalize_custom_tags(raw)
    assert tags == ["custom:solar-rooftop", "custom:తెలుగు-సేవ", "custom:हिंदी"]
    assert normalize_custom_tags(tags) == tags


def test_tag_conflicts_cannot_prompt_followups_for_an_opt_out():
    tags = derive_status_tags("not_interested", {}, next_action="Remove from callback list", model_tags=[
        "signal:do_not_call", "signal:ready_to_buy", "followup:callback", "sentiment:positive", "sentiment:negative"])
    assert "outcome:not_interested" in tags and "signal:do_not_call" in tags
    assert not any(tag.startswith(("followup:", "action:", "sentiment:")) for tag in tags)
    assert "signal:ready_to_buy" not in tags


def test_handling_guidance_recompiles_without_leaking_editor_metadata():
    from server.brain.brain_prompt_validate import validate_rendered_brain
    from server.brain.business_brain_store import assemble_raw_business_prompt
    from server.brain.compiled_brain_artifact import assemble_unified_brain

    sections = [
        {"type": "facts", "title": "Calling script", "raw_text": "You represent Example Support. Answer approved enquiries.", "enabled": True},
        {"type": "custom", "title": "saas_handling_rules", "raw_text": '{"private_editor_state":"do not send"}', "enabled": True},
        {"type": "faq", "title": "Objection & Objective Handling", "raw_text": "[Objective]\nWhen: Caller asks for a demo\nGuidance: Explain first, then collect the preferred time.", "enabled": True},
    ]
    raw, before = assemble_raw_business_prompt(sections)
    compiled = assemble_unified_brain(language="te-IN", script=raw)
    assert "Explain first, then collect" in compiled
    assert "private_editor_state" not in compiled
    assert not validate_rendered_brain(compiled, "te-IN")
    sections[-1]["raw_text"] = "[Objective]\nWhen: Caller asks for a demo\nGuidance: Answer the latest question first."
    changed, after = assemble_raw_business_prompt(sections)
    assert after != before
    assert "Answer the latest question first" in assemble_unified_brain(language="te-IN", script=changed)
    sections[-1]["enabled"] = False
    disabled, _ = assemble_raw_business_prompt(sections)
    assert "Answer the latest question first" not in disabled


def test_defer_cannot_be_closed_even_with_a_conflicting_refusal_decision():
    from server.call.close_classifier import parse_classifier_output

    user = "I am busy, contact me later"
    assert parse_classifier_output({"intent": "defer", "decision": "close", "reason": "refused", "evidence": user, "explicit_end": True}, user) is None
    user = "That is all I needed"
    result = parse_classifier_output({"intent": "done", "decision": "close", "reason": "refused", "evidence": user, "explicit_end": True}, user)
    assert result["reason"] == "goal_complete"
    assert parse_classifier_output({"decision": "close", "reason": "done", "evidence": user, "explicit_end": False}, user) is None


@pytest.mark.parametrize("field,value", [
    ("intent", []), ("intent", {}), ("intent", 7),
    ("explicit_end", "true"), ("explicit_end", None), ("explicit_end", 1),
])
def test_malformed_close_classification_leaves_the_call_open(field, value):
    from server.call.close_classifier import parse_classifier_output

    caller = "That is all I needed"
    result = {"intent": "done", "decision": "close", "reason": "done", "evidence": caller, "explicit_end": True}
    result[field] = value
    assert parse_classifier_output(result, caller) is None


async def test_unidentified_callers_stay_separate_and_call_replays_are_idempotent(db, monkeypatch):
    async with db.kw["bind"].begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[Lead.__table__]))
    monkeypatch.setattr(lead_sync, "_session_factory", lambda: db)
    first = await lead_sync.sync_outcome_to_lead(outcome={"disposition": "interested", "facts": {"name": "First"}}, tenant_id=TID, agent_id=AID, call_id="call-a")
    second = await lead_sync.sync_outcome_to_lead(outcome={"disposition": "interested", "facts": {"name": "Second"}}, tenant_id=TID, agent_id=AID, call_id="call-b")
    replay = await lead_sync.sync_outcome_to_lead(outcome={"disposition": "interested", "facts": {"name": "First"}}, tenant_id=TID, agent_id=AID, call_id="call-a")
    assert first["leadId"] != second["leadId"]
    assert replay["leadId"] == first["leadId"]
    async with db() as session:
        rows = (await session.execute(select(Lead).where(Lead.tenant_id == TID))).scalars().all()
        assert len(rows) == 2
        assert all(row.notes.count("Call reference:") == 1 for row in rows)


@pytest.mark.parametrize("phone", ["not provided", "anonymous", "---", "123", "1234567890123456"])
def test_invalid_phone_facts_use_carrier_identity_or_stay_unidentified(phone):
    assert lead_sync._extract_phone({"phone": phone}, {}) == ""
    assert lead_sync._extract_phone({"phone": phone}, {"direction": "outbound", "callee_e164": "+12025550101"}) == "+12025550101"


async def test_automatic_followup_preserves_tenant_contact_name_and_never_books_from_a_plan(db, monkeypatch):
    async with db.kw["bind"].begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[Lead.__table__]))
    monkeypatch.setattr(lead_sync, "_session_factory", lambda: db)
    async with db() as session:
        row = Lead(tenant_id=TID, agent_id=str(AID), name="Tenant-approved name", phone="+1 202 555 0101", stage="contacted")
        session.add(row)
        await session.commit()
        lead_id = row.lead_id
    result = await lead_sync.sync_outcome_to_lead(outcome={"disposition": "site_visit_planned", "facts": {"name": "Unverified transcript name", "phone": "+12025550101"}}, tenant_id=TID, agent_id=AID, call_id="visit-planned")
    assert result["leadId"] == str(lead_id)
    assert result["stage"] == "qualified"
    async with db() as session:
        assert (await session.get(Lead, lead_id)).name == "Tenant-approved name"


async def test_read_only_user_cannot_create_or_modify_leads(monkeypatch):
    app = FastAPI()
    app.include_router(app_leads.router)
    app.dependency_overrides[require_subscriber_jwt] = lambda: SubscriberPrincipal(user_id=TID, tenant_id=TID, role="customer_viewer", email="viewer@example.invalid")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for method, path, body in [("POST", "/api/leads", {"name": "Denied"}), ("PATCH", f"/api/leads/{TID}", {"notes": "Denied"}), ("PATCH", f"/api/leads/{TID}/stage", {"stage": "qualified"})]:
            assert (await client.request(method, path, json=body)).status_code == 403
