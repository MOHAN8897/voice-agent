"""Language-switch callbacks: detect, record, list, call back in the requested pack.

Calls built with `_ctx()` cannot switch live (no `supports_language_switch`), so they
keep the confirm-record-close path; the live English fallback is in
test_language_live_switch.py.
"""
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

from server.call import language_switch as ls
from server.call.call_ledger import call_ledger
from server.config.env import get_settings
from server.db.models.entities import Call
from server.db.models.language_switch_models import ContactLanguagePreference, LanguageSwitchRequest
from server.services.saas import language_switch_service as svc
from server.services.saas.tenant_guard import SubscriberPrincipal


# -- Detection ------------------------------------------------------------------------

@pytest.mark.parametrize(("text", "call_language", "expected"), [
    ("in English please", "hi-IN", "en-IN"),
    ("Can you speak in English?", "te-IN", "en-IN"),
    ("Sir English please", "ta-IN", "en-IN"),
    ("English mein baat karo", "hi-IN", "en-IN"),
    ("Price kya hai? English mein bataiye", "hi-IN", "en-IN"),
    ("हिंदी में बात कीजिए", "en-IN", "hi-IN"),
    ("Hindi lo matladandi", "te-IN", "hi-IN"),
    ("హిందీలో మాట్లాడండి", "te-IN", "hi-IN"),
    ("ఇంగ్లీష్ లో చెప్పండి", "te-IN", "en-IN"),
    ("தமிழ்ல பேசுங்க", "te-IN", "ta-IN"),
    ("Tamil la pesunga", "en-IN", "ta-IN"),
    ("English la pesunga", "ta-IN", "en-IN"),
    ("I can't understand Telugu, speak English", "te-IN", "en-IN"),
    ("Urdu mein baat karo", "hi-IN", "ur-IN"),
])
def test_explicit_language_requests_are_detected_across_scripts(text, call_language, expected):
    assert ls.detect_language_request(text, call_language) == expected


@pytest.mark.parametrize(("text", "call_language"), [
    ("I don't speak Hindi", "en-IN"),
    ("హిందీ రాదు", "te-IN"),
    ("मुझे हिंदी नहीं आती", "en-IN"),
    ("हिंदी में बात मत करो", "en-IN"),
    ("Do you have Hindi books for children in stock", "en-IN"),
    ("speak in Telugu", "te-IN"),
    ("Book my order for Saturday please", "en-IN"),
])
def test_mentions_negations_and_own_language_are_not_requests(text, call_language):
    assert ls.detect_language_request(text, call_language) is None


@pytest.mark.parametrize(("text", "expected"), [
    ("What is the price of this product and when can you deliver", "en-IN"),
    ("मुझे इसकी कीमत जाननी है कृपया बताइए", "hi-IN"),
    ("నాకు ధర ఎంత చెప్పండి", "te-IN"),
    ("எனக்கு விலை எவ்வளவு சொல்லுங்க", "ta-IN"),
    ("kya hai price bhai batao na", None),  # romanised Hindi is code-mix, not English
    ("ok", None),
])
def test_utterance_language_by_script(text, expected):
    assert ls.utterance_language(text) == expected


def _ctx(**extra):
    base = dict(call_id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4()), agent_id=str(uuid.uuid4()),
                status="active", contact_preference="none", call_end_policy=None)
    return SimpleNamespace(**{**base, **extra})


@pytest.mark.parametrize(("call_language", "text", "target"), [
    ("hi-IN", "in English please", "en-IN"),
    ("te-IN", "Hindi lo matladandi", "hi-IN"),
    ("ta-IN", "English la pesunga", "en-IN"),
    ("en-IN", "हिंदी में बात कीजिए", "hi-IN"),
])
def test_explicit_request_closes_with_callback_in_the_call_language(call_language, text, target):
    decision = ls.decide_language_switch(_ctx(), text, call_language)
    assert decision.action == "close" and decision.language == target
    # Spoken in the call's own language, naming the requested one.
    assert ls.language_name(target, spoken_in=call_language) in decision.text
    if call_language != "en-IN":
        assert ls.utterance_language(decision.text.replace("call", "")) in (call_language, None)


def test_opt_out_wins_over_language_request():
    ctx = _ctx()
    assert ls.decide_language_switch(ctx, "Don't call me again. Speak English", "hi-IN") is None
    assert ls.decide_language_switch(_ctx(contact_preference="do_not_call"), "in English please", "hi-IN") is None


def test_unsupported_language_is_said_once_and_call_continues():
    ctx = _ctx()
    first = ls.decide_language_switch(ctx, "Urdu mein baat karo", "hi-IN")
    assert first.action == "hint" and "not available" in first.text and "Do not switch" in first.text
    assert ls.decide_language_switch(ctx, "Urdu mein baat karo please", "hi-IN") is None


def test_sustained_foreign_speech_offers_once_then_closes_on_yes():
    ctx = _ctx()
    assert ls.decide_language_switch(ctx, "What is the price of this product please tell me", "te-IN") is None
    offer = ls.decide_language_switch(ctx, "Can you tell me when the delivery will happen", "te-IN")
    assert offer.action == "offer" and offer.language == "en-IN"
    closing = ls.decide_language_switch(ctx, "yes please", "te-IN")
    assert closing.action == "close" and closing.language == "en-IN"


def test_declined_offer_is_not_repeated():
    ctx = _ctx()
    ls.decide_language_switch(ctx, "मुझे इसकी कीमत जाननी है कृपया बताइए", "ta-IN")
    assert ls.decide_language_switch(ctx, "डिलीवरी कब तक होगी बताइए", "ta-IN").action == "offer"
    assert ls.decide_language_switch(ctx, "नहीं, ठीक है", "ta-IN") is None
    assert ls.decide_language_switch(ctx, "डिलीवरी कब तक होगी बताइए", "ta-IN") is None
    assert ls.decide_language_switch(ctx, "मुझे इसकी कीमत जाननी है कृपया", "ta-IN") is None


def test_prompt_lock_follows_the_platform_active_language_note():
    from server.prompts.agent_voice_rules import LANGUAGE_LOCK

    for code in ("hi-IN", "te-IN", "ta-IN", "en-IN"):
        # The model never switches on its own; the platform's ACTIVE LANGUAGE note decides.
        assert "ACTIVE LANGUAGE note" in LANGUAGE_LOCK[code] and "Never switch on your own" in LANGUAGE_LOCK[code]
        assert "never switch mid-call" not in LANGUAGE_LOCK[code]


# -- Storage ---------------------------------------------------------------------------

@pytest.fixture
async def db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ls.db'}")
    columns = [c for c in Call.__table__.columns if isinstance(c.type, ARRAY)]
    original = [c.type for c in columns]
    for c in columns:
        c.type = JSON()
    try:
        async with engine.begin() as conn:
            for table in (Call.__table__, LanguageSwitchRequest.__table__, ContactLanguagePreference.__table__):
                await conn.run_sync(lambda sync, t=table: t.create(sync))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(svc, "get_session_factory", lambda: factory)
        principal = SubscriberPrincipal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="customer_admin",
                                        email="test@example.invalid")
        yield factory, principal
    finally:
        await engine.dispose()
        for c, t in zip(columns, original):
            c.type = t
        get_settings.cache_clear()


async def _live_call(factory, principal, *, language="te-IN", phone="+919000000001", direction="inbound"):
    ctx = _ctx(tenant_id=str(principal.tenant_id))
    async with factory() as session:
        session.add(Call(call_id=uuid.UUID(ctx.call_id), tenant_id=principal.tenant_id, agent_id=uuid.UUID(ctx.agent_id),
                         combination_id="test", storage_path="test", status_tags=[]))
        await session.commit()
    call_ledger.meta_path(ctx.call_id).parent.mkdir(parents=True, exist_ok=True)
    key = "callee_e164" if direction == "outbound" else "caller_id"
    call_ledger.write_meta(ctx.call_id, {"call_id": ctx.call_id, "tenant_id": str(principal.tenant_id),
                                         "agent_id": ctx.agent_id, "direction": direction, key: phone,
                                         "language": language})
    return ctx


async def test_server_turn_records_item_before_promising_and_closes(db):
    factory, principal = db
    ctx = await _live_call(factory, principal)
    turn = await ls.server_language_switch_turn(ctx, "Hindi lo matladandi", "te-IN")
    assert turn["end_call"]["should_end"] is True
    assert turn["end_call"]["contact_preference"] == "callback"
    assert "హిందీ" in turn["text"]  # "call back in Hindi", said in Telugu
    async with factory() as session:
        item = (await session.execute(select(LanguageSwitchRequest))).scalar_one()
        pref = (await session.execute(select(ContactLanguagePreference))).scalar_one()
    assert (item.kind, item.requested_language, item.original_language, item.status) == \
        ("language_switch", "hi-IN", "te-IN", "pending")
    assert item.phone_e164 == "+919000000001" and pref.language == "hi-IN"
    meta = call_ledger.read_meta(ctx.call_id)
    assert meta["language_callback"]["kind"] == "language_switch"
    assert meta["language_callback"]["id"] == str(item.id)
    # Recorded once: a later turn on the same call does nothing more.
    assert await ls.server_language_switch_turn(ctx, "Hindi please", "te-IN") is None


async def test_failed_storage_never_promises_a_callback(db, monkeypatch):
    factory, principal = db
    ctx = await _live_call(factory, principal)
    monkeypatch.setattr(svc, "record_language_switch", AsyncMock(side_effect=RuntimeError("db down")))
    turn = await ls.server_language_switch_turn(ctx, "in English please", "te-IN")
    assert turn["end_call"]["contact_preference"] == "none"
    assert "English" not in turn["text"]


async def test_outcome_is_tagged_as_language_switch(db, monkeypatch):
    from server.call import post_call_pipeline as pipeline

    factory, principal = db
    ctx = await _live_call(factory, principal, language="ta-IN")
    await ls.server_language_switch_turn(ctx, "English la pesunga", "ta-IN")
    monkeypatch.setattr(pipeline, "_mark_outcome", AsyncMock())
    monkeypatch.setattr(pipeline.call_store, "update", AsyncMock())
    monkeypatch.setattr(pipeline, "_sync_lead", AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline, "_generate_outcome", AsyncMock(return_value=({
        "disposition": "no_outcome", "summary_en": "Caller wanted English.", "extracted_fields": {}}, "unavailable")))
    result = await pipeline._run_outcome_locked(ctx.call_id)
    assert result["disposition"] == "callback_required"
    assert result["facts"]["requested_language"] == "en-IN"
    assert "followup:language_switch" in result["status_tags"]
    assert result["language_switch"]["original_language"] == "ta-IN"


def test_language_switch_tag_is_server_owned_and_dropped_for_dnd():
    from server.call.outcome_schema import MODEL_STATUS_TAGS, derive_status_tags

    assert "followup:language_switch" not in MODEL_STATUS_TAGS
    facts = {"language_switch": "true", "requested_language": "hi-IN"}
    assert "followup:language_switch" in derive_status_tags("callback_required", facts)
    assert "followup:language_switch" not in derive_status_tags("callback_required", facts, contact_preference="do_not_call")


async def _item(factory, principal, *, language="hi-IN", agent_id=None, phone="+919000000002", status="pending"):
    row = LanguageSwitchRequest(id=uuid.uuid4(), tenant_id=principal.tenant_id, agent_id=agent_id or str(uuid.uuid4()),
                                phone_e164=phone, requested_language=language, original_language="te-IN", status=status)
    async with factory() as session:
        session.add(row)
        await session.commit()
    return row


async def test_list_api_filters_by_language_and_status(db):
    factory, principal = db
    await _item(factory, principal, language="hi-IN")
    await _item(factory, principal, language="en-IN", phone="+919000000003")
    await _item(factory, principal, language="hi-IN", phone="+919000000004", status="done")
    other = SubscriberPrincipal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="customer_admin", email="o@example.invalid")
    await _item(factory, other, language="hi-IN", phone="+919000000005")
    rows = await svc.list_language_switch_requests(principal.tenant_id, language="hi-IN")
    assert [(r["requestedLanguage"], r["status"], r["kind"]) for r in rows] == [("hi-IN", "pending", "language_switch")]
    assert rows[0]["requestedLanguageLabel"] == "Hindi" and rows[0]["originalLanguage"] == "te-IN"
    assert len(await svc.list_language_switch_requests(principal.tenant_id, status="all")) == 3


async def test_call_now_uses_same_agent_and_requested_language(db, monkeypatch):
    from server.services.saas import call_callback_service

    factory, principal = db
    item = await _item(factory, principal, language="hi-IN")
    agent = {"agent_id": item.agent_id, "languages": ["te-IN"], "active_compiled_brain_version": "v1"}
    monkeypatch.setattr(call_callback_service, "resolve_workspace_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(svc, "language_readiness", AsyncMock(return_value={"ready": True, "code": "ready", "message": ""}))
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound",
                        AsyncMock(return_value={"ok": True, "call_control_id": "cc"}))
    dial = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("server.services.saas.telephony_orchestrator.subscriber_outbound", dial)
    result = await svc.call_language_switch(principal, item.id)
    assert result["ok"] and result["language"] == "hi-IN"
    kwargs = dial.await_args.kwargs
    assert kwargs["agent_id"] == item.agent_id and kwargs["to_e164"] == item.phone_e164
    assert kwargs["contact"] == {"call_language": "hi-IN", "language_switch_id": str(item.id)}
    rows = await svc.list_language_switch_requests(principal.tenant_id)
    assert rows[0]["status"] == "calling"


async def test_call_now_refuses_when_agent_cannot_speak_the_language(db, monkeypatch):
    from server.services.saas import call_callback_service

    factory, principal = db
    item = await _item(factory, principal, language="hi-IN")
    monkeypatch.setattr(call_callback_service, "resolve_workspace_agent", AsyncMock(return_value={"agent_id": item.agent_id}))
    monkeypatch.setattr(svc, "language_readiness", AsyncMock(return_value={
        "ready": False, "code": "script_needs_review", "message": "Review the farewell for Hindi."}))
    with pytest.raises(HTTPException) as err:
        await svc.call_language_switch(principal, item.id)
    assert err.value.status_code == 409 and "Hindi" in err.value.detail["error"]["message"]


async def test_readiness_builds_the_brain_for_the_requested_pack(monkeypatch):
    import importlib
    from server.brain.compiled_brain_artifact import assemble_unified_brain

    cbs = importlib.import_module("server.brain.compiled_brain_service")
    from server.services.saas import pstn_saas_stack

    brain = assemble_unified_brain(language="te-IN", script="--- OPENING ---\nNamaste, SunPeak nunchi.\n")
    monkeypatch.setattr(cbs.compiled_brain_service, "get_active_for_agent", AsyncMock(return_value={"compiled_text": brain}))
    seen = {}

    async def stack(agent):
        seen["languages"] = agent["languages"]
        return {"language": agent["languages"][0]}

    monkeypatch.setattr(pstn_saas_stack, "saas_stack_override_for_agent", stack)
    ready = await svc.language_readiness({"agent_id": "a", "languages": ["te-IN"], "active_compiled_brain_version": "v"}, "hi-IN")
    assert ready["ready"], ready
    assert seen["languages"] == ["hi-IN", "te-IN"]
    unavailable = await svc.language_readiness({"agent_id": "a", "active_compiled_brain_version": "v"}, "ur-IN")
    assert unavailable["code"] == "language_unavailable"


def test_override_brain_uses_requested_spoken_pack():
    from server.brain.compiled_brain_artifact import assemble_unified_brain, refresh_platform_sections

    brain = assemble_unified_brain(language="te-IN", script="--- OPENING ---\nNamaste.\n")
    rendered = refresh_platform_sections(brain, "hi-IN")
    assert "--- SPOKEN LANGUAGE (hi-IN) ---" in rendered
    assert "--- SPOKEN LANGUAGE (te-IN) ---" not in rendered


async def test_override_stack_resolves_stt_tts_for_requested_language(monkeypatch):
    from server.services.saas import pstn_saas_stack, voice_stack_profiles

    captured = {}

    async def selection(*, environment, tier, voice_settings, language):
        captured["language"] = language
        return ({"pipeline": "composed_voice", "language": language,
                 "stt": {"provider": "sarvam", "model": "saaras:v3"},
                 "llm": {"provider": "openai", "model": "gpt-4.1-mini"},
                 "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {}}}, {})

    monkeypatch.setattr(pstn_saas_stack, "load_agent_voice_config", AsyncMock(return_value={}))
    monkeypatch.setattr(voice_stack_profiles, "load_profile_records", AsyncMock(return_value={"medium": {"profile": {"engines": {}}}}))
    monkeypatch.setattr(voice_stack_profiles, "resolve_agent_selection", selection)
    monkeypatch.setattr(pstn_saas_stack, "normalize_pstn_stack_override", lambda stack, **kw: (stack, []))
    agent = svc.language_override_agent({"agent_id": "a", "languages": ["te-IN"], "default_tier": "medium"}, "hi-IN")
    stack = await pstn_saas_stack.saas_stack_override_for_agent(agent)
    assert captured["language"] == "hi-IN" and stack["language"] == "hi-IN"


async def test_subscriber_outbound_applies_contact_call_language(monkeypatch):
    from server.services.saas import telephony_orchestrator as tel
    from server.services.saas import call_callback_service, kyc_gate, billing_wallet_service, telephony_profile

    captured = {}

    class Stop(Exception):
        pass

    async def stack(agent):
        captured["agent"] = agent
        raise Stop()

    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "telnyx")
    monkeypatch.setattr("server.services.telephony.telephony_guard_error", lambda provider: None)
    monkeypatch.setattr(call_callback_service, "resolve_workspace_agent", AsyncMock(return_value={
        "agent_id": "a", "status": "live", "languages": ["te-IN"], "active_compiled_brain_version": "v"}))
    monkeypatch.setattr(telephony_profile, "get_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(kyc_gate, "assert_kyc_approved", AsyncMock())
    monkeypatch.setattr(billing_wallet_service, "assert_wallet_allows_pstn", AsyncMock())
    monkeypatch.setattr(tel, "resolve_outbound_from_e164", AsyncMock(return_value="+914000000000"))
    monkeypatch.setattr(tel, "get_session_factory", lambda: None)
    monkeypatch.setattr(tel, "assert_concurrent_limit", AsyncMock())
    monkeypatch.setattr(tel, "saas_stack_override_for_agent", stack)
    monkeypatch.setattr(svc, "preferred_language_for", AsyncMock(return_value=None))
    principal = SubscriberPrincipal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role="customer_admin", email="t@example.invalid")
    with pytest.raises(Stop):
        await tel.subscriber_outbound(principal, agent_id="a", from_e164=None, to_e164="+919000000009",
                                      contact={"call_language": "hi-IN", "language_switch_id": "x"})
    assert captured["agent"]["languages"][0] == "hi-IN"
    with pytest.raises(HTTPException) as err:
        await tel.subscriber_outbound(principal, agent_id="a", from_e164=None, to_e164="+919000000009",
                                      contact={"call_language": "ur-IN"})
    assert err.value.detail["error"]["code"] == "language_unavailable"
    # A remembered language leads only for an agent configured to speak it.
    monkeypatch.setattr(svc, "preferred_language_for", AsyncMock(return_value="hi-IN"))
    with pytest.raises(Stop):
        await tel.subscriber_outbound(principal, agent_id="a", from_e164=None, to_e164="+919000000009")
    assert captured["agent"]["languages"] == ["te-IN"]


async def test_bulk_campaign_carries_each_contacts_language(db, monkeypatch):
    from server.routes import campaigns as campaign_routes
    from server.routes import language_switch as routes
    from server.services.saas import call_callback_service

    factory, principal = db
    agent_a, agent_b = str(uuid.uuid4()), str(uuid.uuid4())
    hindi = await _item(factory, principal, language="hi-IN", agent_id=agent_a, phone="+919000000011")
    english = await _item(factory, principal, language="en-IN", agent_id=agent_a, phone="+919000000012")
    tamil = await _item(factory, principal, language="ta-IN", agent_id=agent_b, phone="+919000000013")
    closed = await _item(factory, principal, language="hi-IN", agent_id=agent_a, phone="+919000000014", status="done")
    monkeypatch.setattr(call_callback_service, "resolve_workspace_agent", AsyncMock(side_effect=lambda a, t: {"agent_id": a}))
    monkeypatch.setattr(svc, "language_readiness", AsyncMock(return_value={"ready": True, "code": "ready", "message": ""}))
    created: list = []

    async def fake_create(request, body, ctx):
        created.append(body)
        return {"campaignId": str(uuid.uuid4()), "campaign": {"status": "running"}}

    monkeypatch.setattr(campaign_routes, "create_campaign", fake_create)
    ctx = SimpleNamespace(role="customer_admin", workspace_tenant_id=principal.tenant_id)
    body = routes.BulkCampaignBody(ids=[hindi.id, english.id, tamil.id, closed.id], consentConfirmed=True)
    result = await routes.bulk_campaign(SimpleNamespace(), body, ctx)
    assert result["skipped"] == [str(closed.id)]
    by_agent = {b.agent_id: {c["phone"]: c["call_language"] for c in b.contacts} for b in created}
    assert by_agent == {agent_a: {"+919000000011": "hi-IN", "+919000000012": "en-IN"},
                        agent_b: {"+919000000013": "ta-IN"}}
    assert all(c["language_switch_id"] for b in created for c in b.contacts)
    rows = {r["id"]: r for r in await svc.list_language_switch_requests(principal.tenant_id, status="all")}
    assert rows[str(hindi.id)]["status"] == "calling" and rows[str(hindi.id)]["campaignId"]
    assert rows[str(closed.id)]["status"] == "done"


async def test_campaign_runner_passes_contact_language_to_outbound():
    import inspect
    from server.services.saas import campaign_runner

    # The runner hands the snapshot metadata (with call_language) to subscriber_outbound as `contact`.
    source = inspect.getsource(campaign_runner._dial_claim)
    assert "payload = {**(row.metadata_ or {})" in source and "contact=payload" in source


async def test_successful_callback_marks_item_done_and_remembers_language(db):
    factory, principal = db
    item = await _item(factory, principal, language="hi-IN", status="calling")
    call_id = str(uuid.uuid4())
    call_ledger.meta_path(call_id).parent.mkdir(parents=True, exist_ok=True)
    meta = {"tenant_id": str(principal.tenant_id), "language": "hi-IN",
            "contact": {"call_language": "hi-IN", "language_switch_id": str(item.id)}}
    # No caller turn (voicemail / no answer): stays open.
    assert await svc.complete_language_switch_after_call(call_id, meta) is False
    await call_ledger.append_user_turn(call_id, "हाँ बताइए")
    assert await svc.complete_language_switch_after_call(call_id, meta) is True
    rows = await svc.list_language_switch_requests(principal.tenant_id, status="all")
    assert rows[0]["status"] == "done" and rows[0]["callbackCallId"] == call_id
    async with factory() as session:
        pref = (await session.execute(select(ContactLanguagePreference))).scalar_one()
    assert (pref.language, pref.source) == ("hi-IN", "callback_completed")


async def test_callback_asking_for_another_language_keeps_item_open(db):
    factory, principal = db
    item = await _item(factory, principal, language="hi-IN", status="calling")
    call_id = str(uuid.uuid4())
    call_ledger.meta_path(call_id).parent.mkdir(parents=True, exist_ok=True)
    await call_ledger.append_user_turn(call_id, "English please")
    meta = {"tenant_id": str(principal.tenant_id), "contact": {"call_language": "hi-IN", "language_switch_id": str(item.id)},
            "language_callback": {"status": "requested", "caller_language": "en-IN"}}
    assert await svc.complete_language_switch_after_call(call_id, meta) is False


async def test_realtime_handoff_gets_an_item_post_call(db):
    factory, principal = db
    ctx = await _live_call(factory, principal, language="hi-IN", phone="+919000000021", direction="outbound")
    meta = call_ledger.read_meta(ctx.call_id)
    meta["language_callback"] = {"status": "requested", "caller_language": "Telugu", "configured_language": "hi-IN",
                                 "summary": "Caller needs bike servicing; prefers Telugu."}
    item_id = await svc.ensure_language_switch_from_meta(ctx.call_id, meta)
    rows = await svc.list_language_switch_requests(principal.tenant_id)
    assert rows[0]["id"] == item_id and rows[0]["requestedLanguage"] == "te-IN"
    assert rows[0]["phone"] == "+919000000021"


async def test_live_turn_never_reaches_the_reply_model_for_a_language_request(db, monkeypatch):
    from server.call import call_context
    from server.call.live_turn_orchestrator import live_turn_orchestrator

    factory, principal = db
    ctx = await _live_call(factory, principal, language="hi-IN")
    ctx.session_id, ctx.pipeline, ctx.resolved_stack, ctx.turns = "ls-session", "realtime_text", None, []
    ctx.heartbeat = lambda: None
    call_context.put(ctx)
    monkeypatch.setattr(type(live_turn_orchestrator), "_stream_llm",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("reply model must not run")))
    try:
        chunks = [c async for c in live_turn_orchestrator.handle_user_turn_stream(
            transcript="in English please", language_code="hi-IN", session_id="ls-session", call_id=ctx.call_id)]
    finally:
        call_context.clear_all()
    done = [c for c in chunks if c.get("done")]
    assert len(done) == 1 and done[0]["end_call"]["should_end"] is True
    assert done[0]["replace_speech"] and "English" in done[0]["text"]
    assert any(r["role"] == "assistant" for r in call_ledger.read_lines(ctx.call_id))
