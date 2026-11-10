"""Regressions from the 10 Nov 2026 audit: repetition, turn latency, inbound calls,
agent creation and integrations.

Each test names the behaviour a caller or tenant sees.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from server.call import close_classifier
from server.call.reply_guard import asks_to_repeat, drop_near_repeats, guard_reply


# ------------------------------------------------------------------ turn latency
class _SlowAdapter:
    """Every model request takes ``delay`` seconds; records how many overlapped."""

    def __init__(self, delay: float) -> None:
        self.delay, self.running, self.peak = delay, 0, 0

    async def stream_live_turn(self, *, input_messages, **_):
        self.running += 1
        self.peak = max(self.peak, self.running)
        await asyncio.sleep(self.delay)
        self.running -= 1
        review = "contact_action" in input_messages[0]["content"]
        text = ('{"contact_action":"keep","finish":false,"open_request":"","action_request":"none"}' if review
                else '{"decision":"continue","reason":"none"}')
        yield {"done": True, "text": text, "usage": {}}


@pytest.mark.asyncio
async def test_the_two_turn_decisions_run_together_not_one_after_the_other(monkeypatch):
    adapter = _SlowAdapter(0.25)
    registry = SimpleNamespace(is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
                               get_llm=lambda _p: adapter)
    monkeypatch.setattr("server.providers.get_provider_registry", lambda: registry)
    llm = SimpleNamespace(provider="sarvam", model="m", config={})
    started = time.perf_counter()
    proposal = await close_classifier.classify_close_turn(
        transcript="ధర ఎంత?", agent_previous="నమస్తే", language="te-IN", llm=llm)
    elapsed = time.perf_counter() - started
    assert proposal and proposal["decision"] == "continue"
    assert adapter.peak == 2          # both requests were in flight at once
    assert elapsed < 0.45             # ~one round-trip, not two (0.5 s in series)


# ------------------------------------------------------------------ repetition
ASK = "మీకు ఎన్ని విజిటింగ్ కార్డ్స్ కావాలో చెప్పండి."


def test_the_same_ask_is_not_made_a_third_time():
    # Call 9242334c: the agent asked "how many cards?" six times.
    earlier = ["ఎన్ని విజిటింగ్ కార్డ్స్ కావాలో చెప్తారా?", "సరే, చెప్తాను. " + ASK, "నమస్కారం, చెప్పండి.", "సరే, " + ASK]
    out = drop_near_repeats(ASK, caller="హలో.", previous=earlier[-2:], language="te-IN", earlier=earlier)
    assert "ఎన్ని" not in out and out == "సరే, చెప్పండి."


def test_a_repeated_sales_question_is_dropped_but_the_answer_stays():
    # "... ₹25. Order place చేద్దామా?" on every reply, even after a caller's question.
    previous = ["విజిటింగ్ కార్డ్స్ ఒక్కోటి ₹25. Order place చేద్దామా?"]
    reply = "ఆ విషయం నాకు తెలియదు. మా దగ్గర విజిటింగ్ కార్డ్స్ ఉన్నాయి. Order place చేద్దామా?"
    out = drop_near_repeats(reply, caller="బిల్ బుక్స్ చేస్తారా?", previous=previous, language="te-IN", earlier=previous)
    assert out == "ఆ విషయం నాకు తెలియదు. మా దగ్గర విజిటింగ్ కార్డ్స్ ఉన్నాయి."


def test_the_same_answer_to_the_same_question_is_kept():
    previous = ["Split AC servicing కి ₹599 అవుతుంది."]
    reply = "Split AC servicing కి ₹599 అవుతుంది."
    assert drop_near_repeats(reply, caller="Split AC ధర ఎంత?", previous=previous, language="te-IN", earlier=previous) == reply


@pytest.mark.parametrize("caller,expected", [
    ("మళ్ళీ చెప్పండి", True), ("say that again please", True), ("फिर से बताइए", True),
    ("మళ్ళీ చేస్తామండి, చెప్తాను ఎన్ని కావాలన్నది.", False),   # "we will call again"
    ("call me again tomorrow", False), ("बाद में फिर से कॉल करना", False),
])
def test_calling_again_later_is_not_a_request_to_repeat(caller, expected):
    assert asks_to_repeat(caller) is expected


def test_guard_reply_uses_the_last_six_replies(monkeypatch):
    history = [{"role": "assistant", "content": "సరే. " + ASK}, {"role": "user", "content": "హలో"},
               {"role": "assistant", "content": "నమస్కారం, చెప్పండి."}, {"role": "user", "content": "ఆ"},
               {"role": "assistant", "content": "క్షమించండి, వినిపించలేదు."}, {"role": "user", "content": "హలో"},
               {"role": "assistant", "content": "అవును, నేను ఉన్నాను. " + ASK}, {"role": "user", "content": "హలో"},
               {"role": "assistant", "content": "నమస్కారం."}, {"role": "user", "content": "ఆ"},
               {"role": "assistant", "content": "సరే."}]
    out, reasons = guard_reply(ASK, caller="హలో.", language="te-IN", history=history, state={})
    assert "near_repeat" in reasons and "ఎన్ని" not in out


# ------------------------------------------------------------------ agent creation
@pytest.mark.parametrize("language,opening", [
    ("bn-IN", "নমস্কার! আমি Acme থেকে Asha। বলুন, কীভাবে সাহায্য করতে পারি?"),
    ("pa-IN", "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ Acme ਤੋਂ Asha। ਦੱਸੋ, ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰਾਂ?"),
    ("hi-IN", "नमस्ते! मैं Acme से Asha। बताइए, आज आपकी कैसे मदद करूँ?"),
    ("gu-IN", "નમસ્તે! હું Acme માંથી Asha। કહો, કેવી રીતે મદદ કરું?"),
])
def test_openings_ending_in_the_danda_are_accepted(language, opening):
    from server.brain.agent_script_compiler import _opening_line_is_language_compatible

    assert _opening_line_is_language_compatible(opening, language)


def test_an_opening_in_another_script_is_still_rejected():
    from server.brain.agent_script_compiler import _opening_line_is_language_compatible

    assert not _opening_line_is_language_compatible("నమస్తే! నేను Asha.", "bn-IN")
    assert not _opening_line_is_language_compatible("नमस्ते! मैं Asha।", "te-IN")


def test_unusable_model_output_can_be_retried_on_the_same_draft():
    from server.brain.employee_script_pipeline import GenerationStageError

    retry = GenerationStageError("write", transient=False, correlation_id="c1", reason="invalid_output").to_public_dict()
    assert retry["code"] == "generation_failed" and retry["retryable"] is True
    # A provider that rejects the request outright is still not retried.
    assert GenerationStageError("write", transient=False, correlation_id="c1").to_public_dict()["retryable"] is False


@pytest.mark.asyncio
async def test_output_cut_at_the_token_limit_is_asked_again_with_more_room(monkeypatch):
    from pydantic import BaseModel

    from server.brain import employee_script_pipeline as pipeline, generation_runtime
    from server.providers.base import LLMConfig, StructuredOutputTruncated

    class Out(BaseModel):
        ok: bool

    budgets = []

    async def completion(**kw):
        budgets.append(kw["max_output_tokens"])
        if len(budgets) == 1:
            raise StructuredOutputTruncated("gemini", kw["max_output_tokens"], "MAX_TOKENS")
        return {"ok": True}

    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (
        SimpleNamespace(structured_completion=completion), LLMConfig(provider="gemini", model="test-model")))
    result = await pipeline._completion("write", "rules", {}, Out, temperature=0, tokens=1000, correlation_id="c1")
    assert result.ok is True and budgets == [1000, 1600]


@pytest.mark.asyncio
async def test_a_build_that_died_does_not_block_the_same_request_for_ever(monkeypatch):
    from server.brain import agent_service as module

    monkeypatch.setattr(module, "get_session_factory", lambda: None)
    service = module.AgentService()
    request_id, tenant = "11111111-1111-4111-8111-111111111111", "00000000-0000-4000-8000-0000000000aa"
    first = await service.claim_build_request(request_id=request_id, fingerprint="f1", tenant_id=tenant,
                                              name="Asha", language="te-IN")
    assert first["created"] is True
    # A second click while it is building is still refused ...
    again = await service.claim_build_request(request_id=request_id, fingerprint="f1", tenant_id=tenant,
                                              name="Asha", language="te-IN")
    assert again["created"] is False and not again.get("resumed") and again["state"] == "building"
    # ... but once the build cannot still be running, the same request starts it again.
    aid = first["agent"]["agent_id"]
    module._MEM_BUILD_REQUESTS[aid]["started_at"] = time.time() - module.BUILD_CLAIM_STALE_SECONDS - 5
    resumed = await service.claim_build_request(request_id=request_id, fingerprint="f1", tenant_id=tenant,
                                                name="Asha", language="te-IN")
    assert resumed.get("resumed") is True and resumed["agent"]["agent_id"] == aid
    module._MEM_AGENTS.pop(aid, None)
    module._MEM_BUILD_REQUESTS.pop(aid, None)


# ------------------------------------------------------------------ inbound calls
def _account(**overrides):
    base = dict(provisioning_status="active", auth_id="SA1", encrypted_auth_token="x", account_enabled=True,
                kyc_calls_blocked=False, kyc_status="approved", verifications={}, business_type="individual",
                account_name="Acme", last_status_sync_at=datetime.now(timezone.utc) - timedelta(seconds=120))
    return SimpleNamespace(**{**base, **overrides})


@pytest.fixture
def kyc(monkeypatch):
    from server.services.saas import voice_kyc_service as service

    monkeypatch.setattr("server.services.telephony.active_telephony_provider", lambda: "vobiz")
    monkeypatch.setattr(service, "_carrier_setup_configured", lambda: True)
    return service


TENANT = "00000000-0000-4000-8000-000000000001"


@pytest.mark.asyncio
async def test_answer_time_kyc_uses_the_stored_approval_instead_of_the_carrier(kyc, monkeypatch):
    import uuid

    monkeypatch.setattr(kyc, "_get_account", AsyncMock(return_value=_account()))
    refresh = AsyncMock(return_value={"approved": True, "status": "approved"})
    monkeypatch.setattr(kyc, "refresh_kyc_status", refresh)
    await kyc.assert_voice_kyc_approved(uuid.UUID(TENANT), action="receive a phone call", max_age_seconds=600)
    await asyncio.sleep(0)  # the background refresh keeps the stored status current
    assert refresh.await_count <= 1
    # Without the answer-time allowance the carrier is still asked every time.
    refresh.reset_mock()
    await kyc.assert_voice_kyc_approved(uuid.UUID(TENANT), action="place a call")
    refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_carrier_api_outage_does_not_hang_up_on_callers_of_an_approved_workspace(kyc, monkeypatch):
    import uuid

    stale = _account(last_status_sync_at=datetime.now(timezone.utc) - timedelta(hours=3))
    monkeypatch.setattr(kyc, "_get_account", AsyncMock(return_value=stale))
    monkeypatch.setattr(kyc, "refresh_kyc_status", AsyncMock(side_effect=kyc.VoiceKycError("voice_kyc_status_unavailable")))
    await kyc.assert_voice_kyc_approved(uuid.UUID(TENANT), action="receive a phone call", max_age_seconds=600)


@pytest.mark.asyncio
async def test_an_unapproved_workspace_is_still_refused(kyc, monkeypatch):
    import uuid

    monkeypatch.setattr(kyc, "_get_account", AsyncMock(return_value=_account(kyc_calls_blocked=True)))
    monkeypatch.setattr(kyc, "refresh_kyc_status", AsyncMock(return_value={"approved": False, "status": "pending"}))
    with pytest.raises(HTTPException) as refused:
        await kyc.assert_voice_kyc_approved(uuid.UUID(TENANT), action="receive a phone call", max_age_seconds=600)
    assert refused.value.status_code == 403
    monkeypatch.setattr(kyc, "refresh_kyc_status", AsyncMock(side_effect=kyc.VoiceKycError("voice_kyc_status_unavailable")))
    with pytest.raises(HTTPException) as unavailable:
        await kyc.assert_voice_kyc_approved(uuid.UUID(TENANT), action="receive a phone call", max_age_seconds=600)
    assert unavailable.value.status_code == 503


async def _answer_inbound(monkeypatch, decision):
    """POST a signed inbound answer webhook with the given after-hours decision."""
    from server.brain.agent_service import agent_service
    from server.routes import vobiz
    from server.services.dev_secrets_store import dev_secrets_store
    from server.services.saas import call_admission, pstn_saas_stack, telephony_profile
    from server.services.vobiz_client import VobizCallRegistry, VobizStreamTokens

    registry, tokens = VobizCallRegistry(), VobizStreamTokens()
    monkeypatch.setattr(registry, "_redis", lambda: None)
    monkeypatch.setattr(tokens, "_redis", lambda: None)
    monkeypatch.setattr(vobiz, "vobiz_call_registry", registry)
    monkeypatch.setattr(vobiz, "vobiz_stream_tokens", tokens)
    monkeypatch.setattr(dev_secrets_store, "effective_secret", lambda _key: None)
    monkeypatch.setattr(vobiz, "get_settings", lambda: SimpleNamespace(
        app_environment="production", vobiz_auth_token="unit-inbound-secret", pstn_enforce_wallet_on_inbound=False))
    monkeypatch.setattr(vobiz, "public_api_base", lambda: "https://voice.example")
    monkeypatch.setattr(vobiz, "ws_public_base", lambda: "wss://voice.example")
    monkeypatch.setattr(vobiz, "_parse_vobiz_payload", AsyncMock(return_value={
        "CallUUID": "after-hours-call", "To": "test-destination", "Direction": "inbound"}))
    monkeypatch.setattr(vobiz, "_note_inbound_decline", AsyncMock())
    monkeypatch.setattr(telephony_profile, "profile_for_number", AsyncMock(return_value={
        "agent_id": "saved-agent", "tenant_id": TENANT, "agent_status": "active", "vobiz_account_scope": "platform"}))
    monkeypatch.setattr(telephony_profile, "number_line_accepts_inbound", lambda _p: True)
    monkeypatch.setattr(telephony_profile, "evaluate_inbound_policy", lambda _p: decision)

    @asynccontextmanager
    async def factory():
        yield SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(status="active", deleted_at=None)))

    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: factory)
    monkeypatch.setattr(agent_service, "get_agent", AsyncMock(return_value={
        "agent_id": "saved-agent", "tenant_id": TENANT, "default_tier": "low", "languages": ["te-IN"],
        "voice_settings": {"stackSelectionVersion": 1}}))
    monkeypatch.setattr(pstn_saas_stack, "saas_stack_override_for_agent", AsyncMock(return_value={
        "pipeline": "composed_voice", "language": "te-IN", "voice_flow": "composed_stages",
        "llm": {"provider": "sarvam", "model": "m"}, "_voice_stack_snapshot": {"tier": "low", "profileRevision": 7}}))
    monkeypatch.setattr(call_admission, "reserve", AsyncMock(return_value=("inbound-admission", {})))
    monkeypatch.setattr(call_admission, "finish", AsyncMock())
    monkeypatch.setattr(call_admission, "provider_event", AsyncMock())
    monkeypatch.setattr("server.services.saas.voice_kyc_service.assert_voice_kyc_approved", AsyncMock(return_value=None))
    signature = base64.b64encode(hmac.new(
        b"unit-inbound-secret", b"https://voice.example/api/vobiz/answer.unit-nonce", hashlib.sha256).digest()).decode()
    request = Request({"type": "http", "scheme": "https", "method": "POST", "server": ("voice.example", 443),
                       "path": "/api/vobiz/answer", "query_string": b"", "headers": [
                           (b"x-vobiz-signature-v3", signature.encode()), (b"x-vobiz-signature-v3-nonce", b"unit-nonce")]})
    return await vobiz.vobiz_answer(request), registry


def _decision(**overrides):
    base = dict(should_answer=True, route="agent", reason="in_hours", greeting_phrase=None, transfer_number=None)
    return SimpleNamespace(**{**base, **overrides})


@pytest.mark.asyncio
async def test_after_hours_transfer_dials_the_number_instead_of_the_agent(monkeypatch):
    response, registry = await _answer_inbound(monkeypatch, _decision(
        route="transfer", reason="after_hours_transfer", transfer_number="+919000000001"))
    body = response.body.decode()
    assert "<Dial>" in body and "+919000000001" in body and "<Stream" not in body
    assert registry.get("after-hours-call") is None


@pytest.mark.asyncio
async def test_inbound_call_carries_the_tenant_greeting_and_voicemail_route(monkeypatch):
    response, registry = await _answer_inbound(monkeypatch, _decision(
        route="voicemail", reason="after_hours_voicemail", greeting_phrase="నమస్తే, Smile Studio కి స్వాగతం."))
    assert b"<Stream" in response.body
    row = registry.get("after-hours-call")
    assert row["greeting"] == "నమస్తే, Smile Studio కి స్వాగతం." and row["voicemail_mode"] is True


@pytest.mark.asyncio
async def test_a_declined_telnyx_call_is_rejected_not_left_ringing(monkeypatch):
    from server.routes import telnyx

    hangup = AsyncMock(return_value={})
    monkeypatch.setattr(telnyx, "TelnyxClient", lambda: SimpleNamespace(hangup=hangup))
    await telnyx._reject_inbound("v3:declined-call")
    hangup.assert_awaited_once_with("v3:declined-call")


def test_an_inbound_call_without_an_opening_gets_the_inbound_default():
    from server.services.pstn_text_chunker import extract_opening_greeting

    inbound = extract_opening_greeting(None, "en-IN", direction="inbound") or ""
    assert "how can i help" in inbound.lower() and "moment" not in inbound.lower()


# ------------------------------------------------------------------ integrations
@pytest.mark.parametrize("to,party,expected", [
    ("+91 98765 43210", None, "919876543210"),
    ("98765-43210", "+919876543210", "919876543210"),   # the call's own party: country code from the call
    ("9876543210", None, "9876543210"),
    ("+1 (415) 555-0100", None, "14155550100"),
])
def test_whatsapp_recipient_is_digits_with_the_country_code(to, party, expected):
    from server.services.nango_service import whatsapp_recipient

    assert whatsapp_recipient(to, party) == expected


def test_a_confirmation_can_cite_a_booking_made_earlier_on_the_call(monkeypatch):
    from server.call import call_context
    from server.services import message_grounding, recipient_guard

    booking = {"action": "GOOGLECALENDAR_CREATE_EVENT",
               "result": {"status": "booked", "start": "2026-11-14T15:30:00+05:30", "summary": "Site visit 14 Nov 3:30 PM"}}
    ctx = SimpleNamespace(compiled_brain_text="Smile Studio.", business_answers=[],
                          turn_action_results=[], call_action_results=[booking])
    monkeypatch.setattr(call_context, "get", lambda _call: ctx)
    monkeypatch.setattr(recipient_guard, "caller_turns", lambda _call: ["Please email me the confirmation."])
    args = {"to": "priya@example.com", "subject": "Your visit", "body": "Your site visit is booked for 14 Nov at 3:30 PM."}
    assert message_grounding.check("call-1", "GMAIL_SEND_EMAIL", args) is None
    # Nothing on the call supports it: still refused.
    ctx.call_action_results = []
    assert message_grounding.check("call-1", "GMAIL_SEND_EMAIL", args) is not None

