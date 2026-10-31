"""Sarvam key failover, provider error classification, call-setup refusals and
the admin provider-health endpoint."""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from server.services import provider_health as ph
from server.services.sarvam_keys import sarvam_key_pool

PRIMARY = "primary-key-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
BACKUP = "backup-key-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
BACKUP2 = "backup2-key-CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"

SARVAM_402 = {"error": {"message": "Insufficient credits", "code": "insufficient_quota_error"}}


@pytest.fixture
def keys(monkeypatch):
    from server.services.dev_secrets_store import dev_secrets_store

    monkeypatch.setattr(dev_secrets_store, "effective_secret",
                        lambda field: PRIMARY if field == "sarvam_api_key" else None)
    monkeypatch.setenv("SARVAM_API_KEY_1", BACKUP)
    return monkeypatch


def _chat_ok() -> bytes:
    return (
        b'data: {"choices":[{"delta":{"content":"Namaste"},"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":1}}\n\n'
        b"data: [DONE]\n\n"
    )


def _transport(seen: list[str], answers: dict[str, tuple[int, bytes]]):
    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers.get("api-subscription-key", "")
        seen.append(key)
        status, body = answers.get(key, (500, b"{}"))
        return httpx.Response(status, content=body)

    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, transport):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def _stream_text(adapter) -> str:
    text = ""
    async for event in adapter.stream_live_turn(
        input_messages=[{"role": "user", "content": "hi"}], model="sarvam-105b",
        api_mode="chat_completions_v1", max_output_tokens=20,
    ):
        if event.get("done"):
            text = event["text"]
    return text


# ----------------------------------------------------------- classification

@pytest.mark.parametrize("provider,status,body,expected", [
    ("sarvam", 402, SARVAM_402, ph.CREDITS),
    ("sarvam", 429, {"error": {"code": "insufficient_quota_error"}}, ph.CREDITS),
    ("sarvam", 403, {"error": {"code": "invalid_api_key_error", "message": "bad"}}, ph.AUTH),
    ("sarvam", 429, {"error": {"code": "rate_limit_exceeded_error"}}, ph.RATE),
    ("sarvam", 429, {"error": {"code": "seat_budget_exhausted_error"}}, ph.QUOTA),
    ("sarvam", 503, {"error": {"code": "model_overloaded"}}, ph.UNAVAILABLE),
    ("sarvam", 400, {"error": {"code": "invalid_request_error"}}, ph.BAD_REQUEST),
    ("openai", 429, {"error": {"code": "insufficient_quota", "type": "insufficient_quota"}}, ph.CREDITS),
    ("openai", 429, {"error": {"code": "rate_limit_exceeded"}}, ph.RATE),
    ("openai", 401, {"error": {"code": "invalid_api_key"}}, ph.AUTH),
    ("gemini", 400, {"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}, ph.AUTH),
    ("gemini", 429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded for metric"}}, ph.QUOTA),
    ("gemini", 429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "Too many requests, slow down"}}, ph.RATE),
    ("cartesia", 402, "Payment Required", ph.CREDITS),
    ("cartesia", 401, "Invalid API key", ph.AUTH),
    ("deepgram", 402, {"err_code": "ASR_PAYMENT_REQUIRED"}, ph.CREDITS),
    ("elevenlabs", 401, {"detail": {"status": "quota_exceeded", "message": "quota"}}, ph.CREDITS),
    ("vobiz", 400, "Insufficient balance to place the call", ph.CREDITS),
    ("telnyx", 503, "", ph.UNAVAILABLE),
    ("telnyx", 504, "", ph.TIMEOUT),
    ("razorpay", 401, {"error": {"description": "Authentication failed"}}, ph.AUTH),
])
def test_classification_per_provider(provider, status, body, expected):
    assert ph.classify(provider, status=status, body=json.dumps(body) if isinstance(body, dict) else body) == expected


def test_failure_from_exception_chain_needs_vendor_evidence():
    try:
        try:
            raise ph.ProviderFailure("Sarvam Chat Completions HTTP 402", provider="sarvam", component="llm",
                                     category=ph.CREDITS, status=402)
        except Exception as inner:
            raise RuntimeError("Opening audio preparation failed; call was not placed") from inner
    except RuntimeError as outer:
        failure = ph.provider_failure_from(outer)
    assert failure is not None and failure.provider == "sarvam" and failure.category == ph.CREDITS
    # A local timeout is not a vendor outage.
    assert ph.provider_failure_from(TimeoutError("Greeting not ready")) is None
    # Legacy string errors still classify.
    legacy = ph.provider_failure_from(RuntimeError("Sarvam Chat Completions HTTP 402"))
    assert legacy is not None and legacy.category == ph.CREDITS


# ------------------------------------------------------------- key failover

async def test_402_on_primary_uses_backup_and_records_incident(keys, caplog):
    from server.providers.sarvam_llm import SarvamLLMAdapter

    seen: list[str] = []
    _patch_client(keys, _transport(seen, {PRIMARY: (402, json.dumps(SARVAM_402).encode()), BACKUP: (200, _chat_ok())}))
    caplog.set_level(logging.DEBUG)
    assert await _stream_text(SarvamLLMAdapter()) == "Namaste"
    assert seen == [PRIMARY, BACKUP]

    # Subsequent requests go straight to the backup while the primary cools down.
    seen.clear()
    assert await _stream_text(SarvamLLMAdapter()) == "Namaste"
    assert seen == [BACKUP]

    snap = sarvam_key_pool.snapshot()
    states = {s["slot"]: s["state"] for s in snap["slots"]}
    assert states == {"primary": "cooling_down", "secondary-1": "active"}
    assert snap["activeSlot"] == "secondary-1"

    incidents = ph.provider_health.incidents()
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["provider"] == "sarvam" and incident["category"] == ph.CREDITS
    assert incident["keySlot"] == "primary" and incident["failedOverTo"] == "secondary-1"
    assert "now using the secondary-1 key" in incident["message"]
    assert incident["active"]

    # No key material anywhere: logs, incidents, snapshot.
    blob = caplog.text + json.dumps(incidents) + json.dumps(snap)
    assert PRIMARY not in blob and BACKUP not in blob


async def test_primary_rechecked_after_cooldown_and_recovers(keys):
    from server.providers.sarvam_llm import SarvamLLMAdapter

    seen: list[str] = []
    answers = {PRIMARY: (402, json.dumps(SARVAM_402).encode()), BACKUP: (200, _chat_ok())}
    _patch_client(keys, _transport(seen, answers))
    await _stream_text(SarvamLLMAdapter())
    # Cool-down elapses (simulated) and the primary has been topped up.
    sarvam_key_pool._state["primary"].cooldown_until = 0.0
    answers[PRIMARY] = (200, _chat_ok())
    seen.clear()
    assert await _stream_text(SarvamLLMAdapter()) == "Namaste"
    assert seen == [PRIMARY]
    assert sarvam_key_pool.snapshot()["activeSlot"] == "primary"
    incident = ph.provider_health.incidents()[0]
    assert incident["resolvedAt"] and not incident["active"]


async def test_all_keys_dead_raises_classified_error_and_fails_fast(keys):
    from server.providers.sarvam_llm import SarvamLLMAdapter

    keys.setenv("SARVAM_API_KEY_2", BACKUP2)
    seen: list[str] = []
    dead = (402, json.dumps(SARVAM_402).encode())
    _patch_client(keys, _transport(seen, {PRIMARY: dead, BACKUP: dead, BACKUP2: dead}))
    with pytest.raises(ph.ProviderFailure) as info:
        await _stream_text(SarvamLLMAdapter())
    assert seen == [PRIMARY, BACKUP, BACKUP2]
    assert info.value.category == ph.CREDITS and info.value.all_keys_failed
    assert "Sarvam Chat Completions HTTP 402" in str(info.value)
    incident = ph.provider_health.incidents()[0]
    assert incident["allKeysFailed"] and "all API keys" in incident["message"]

    # Every key cooling down: the next request does not hammer them.
    seen.clear()
    with pytest.raises(ph.ProviderFailure) as again:
        await _stream_text(SarvamLLMAdapter())
    assert seen == []
    assert again.value.all_keys_failed


async def test_rate_limit_does_not_burn_backup_key(keys):
    from server.providers.sarvam_llm import SarvamLLMAdapter

    seen: list[str] = []
    body = json.dumps({"error": {"code": "rate_limit_exceeded_error"}}).encode()
    _patch_client(keys, _transport(seen, {PRIMARY: (429, body), BACKUP: (200, _chat_ok())}))
    with pytest.raises(ph.ProviderFailure) as info:
        await _stream_text(SarvamLLMAdapter())
    assert seen == [PRIMARY]
    assert info.value.category == ph.RATE
    assert sarvam_key_pool.snapshot()["slots"][0]["state"] != "cooling_down"


async def test_structured_completion_fails_over(keys):
    from server.providers.base import LLMConfig
    from server.providers.sarvam_llm import SarvamLLMAdapter

    seen: list[str] = []
    ok = json.dumps({"choices": [{"message": {"content": json.dumps({"a": 1})}}]}).encode()
    _patch_client(keys, _transport(seen, {PRIMARY: (403, json.dumps({"error": {"code": "invalid_api_key_error"}}).encode()),
                                          BACKUP: (200, ok)}))
    result = await SarvamLLMAdapter().structured_completion(
        [{"role": "user", "content": "x"}], {"type": "object"},
        LLMConfig(provider="sarvam", model="sarvam-105b", max_tokens=10), api_mode="chat_completions_v1")
    assert result == {"a": 1}
    assert seen == [PRIMARY, BACKUP]
    assert ph.provider_health.incidents()[0]["category"] == ph.AUTH


async def test_tts_rest_fails_over(keys):
    from server.services import sarvam_tts_service

    seen: list[str] = []
    import base64, io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\x00\x00" * 80)
    ok = json.dumps({"audios": [base64.b64encode(buf.getvalue()).decode()], "request_id": "r"}).encode()
    transport = _transport(seen, {PRIMARY: (402, json.dumps(SARVAM_402).encode()), BACKUP: (200, ok)})
    client = httpx.AsyncClient(transport=transport)
    keys.setattr(sarvam_tts_service, "get_sarvam_client", lambda: client)
    keys.setattr(sarvam_tts_service, "resolve_tts_config", lambda *a, **k: {
        "model": "bulbul:v3", "speaker": "shubh", "pace": 1.0, "language_code": "te-IN"})
    result = await sarvam_tts_service.synthesize("namaste", session_id=None)
    assert result["audio_bytes"]
    assert seen == [PRIMARY, BACKUP]
    await client.aclose()


async def test_stt_rest_fails_over(keys):
    from server.services import sarvam_stt_service

    seen: list[str] = []
    ok = json.dumps({"transcript": "hello", "language_code": "te-IN"}).encode()
    client = httpx.AsyncClient(transport=_transport(seen, {PRIMARY: (402, json.dumps(SARVAM_402).encode()), BACKUP: (200, ok)}))
    keys.setattr(sarvam_stt_service, "get_sarvam_client", lambda: client)
    result = await sarvam_stt_service.transcribe(b"RIFF....", language_code="te-IN")
    assert result["transcript"] == "hello"
    assert seen == [PRIMARY, BACKUP]
    await client.aclose()


async def test_websocket_handshake_rejection_fails_over(keys):
    from server.services import sarvam_ws

    tried: list[str] = []

    class Rejected(Exception):
        def __init__(self):
            super().__init__("server rejected WebSocket connection: HTTP 402")
            self.response = SimpleNamespace(status_code=402, body=json.dumps(SARVAM_402).encode())

    def fake_connect(url, headers, **kw):
        key = headers["api-subscription-key"]

        async def run():
            tried.append(key)
            if key == PRIMARY:
                raise Rejected()
            return SimpleNamespace(close=AsyncMock())

        return run()

    keys.setattr(sarvam_ws, "_connect", fake_connect)
    async with sarvam_ws.connect_tts_ws("bulbul:v3") as ws:
        assert ws is not None
    assert tried == [PRIMARY, BACKUP]
    assert ph.provider_health.incidents()[0]["component"] == "tts"


# ------------------------------------------------------------ call setup

async def test_prepare_retries_once_then_reports_voice_service_unavailable(monkeypatch):
    from server.services import call_setup_failures as csf

    calls = []

    async def prepare(provider, external_id, meta):
        calls.append(external_id)
        raise RuntimeError("Opening audio preparation failed") from ph.ProviderFailure(
            "Sarvam Chat Completions HTTP 402", provider="sarvam", component="llm", category=ph.CREDITS,
            status=402, all_keys_failed=True)

    registry = SimpleNamespace(prepare=prepare)
    with pytest.raises(RuntimeError) as info:
        await csf.prepare_with_retry(registry, "vobiz", "vobiz-1", {})
    assert calls == ["vobiz-1", "vobiz-1"]
    failure = csf.setup_failure(info.value)
    result = csf.unavailable_result(failure, call_id="vobiz-1", tenant_id="t-1")
    assert result["code"] == "voice_service_unavailable" and result["status"] == 503
    assert "weren't charged" in result["error"]
    incident = ph.provider_health.incidents()[0]
    assert incident["callsRejected"] == 1 and incident["tenantsAffected"] == 1


async def test_prepare_retry_succeeds_on_second_attempt():
    from server.services import call_setup_failures as csf

    attempts = []

    async def prepare(provider, external_id, meta):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("x") from ph.ProviderFailure("Sarvam Chat Completions HTTP 402", provider="sarvam",
                                                            component="llm", category=ph.CREDITS, status=402)

    await csf.prepare_with_retry(SimpleNamespace(prepare=prepare), "vobiz", "v", {})
    assert len(attempts) == 2


async def test_local_failure_is_not_retried():
    from server.services import call_setup_failures as csf

    prepare = AsyncMock(side_effect=TimeoutError("Greeting not ready"))
    with pytest.raises(TimeoutError):
        await csf.prepare_with_retry(SimpleNamespace(prepare=prepare), "vobiz", "v", {})
    assert prepare.await_count == 1


async def test_vobiz_outbound_returns_voice_service_unavailable(monkeypatch):
    from server.brain.agent_service import agent_service
    from server.routes import dev_telephony
    from server.services.pstn_prewarm import pstn_prewarm_registry
    from server.services.saas import voice_kyc_service
    from server.services.vobiz_client import vobiz_call_registry, vobiz_stream_tokens

    client = Mock()
    client.create_outbound_call = AsyncMock()

    async def prepare(*args, **kwargs):
        raise RuntimeError("Opening audio preparation failed") from ph.ProviderFailure(
            "Sarvam Chat Completions HTTP 402", provider="sarvam", component="llm", category=ph.CREDITS, status=402)

    monkeypatch.setattr(pstn_prewarm_registry, "prepare", prepare)
    monkeypatch.setattr(agent_service, "get_agent", AsyncMock(return_value={}))
    monkeypatch.setattr(voice_kyc_service, "vobiz_client_for_number", AsyncMock(return_value=(client, "tenant")))
    monkeypatch.setattr(vobiz_call_registry, "upsert", Mock())
    monkeypatch.setattr(vobiz_stream_tokens, "create", Mock(return_value="tok"))
    stack = {"pipeline": "composed_voice", "voice_flow": "composed_stages", "language": "te-IN",
             "llm": {"provider": "sarvam", "model": "sarvam-105b"}}
    monkeypatch.setattr(dev_telephony, "_outbound_pstn_context", lambda _: ("medium", "te-IN", stack, []))
    monkeypatch.setattr(dev_telephony, "_resolve_outbound_source_session", lambda _: ("isolated", False))
    monkeypatch.setattr(dev_telephony, "_billed_user_id_from_session", lambda _: None)
    body = dev_telephony.OutboundTestBody(agentId="a", fromE164="+12025550123", toE164="+12025550181")
    session = SimpleNamespace(kind="app", tenant_id="00000000-0000-4000-8000-000000000001")
    result = await dev_telephony._outbound_vobiz(body, session)
    assert result["ok"] is False and result["code"] == "voice_service_unavailable" and result["status"] == 503
    client.create_outbound_call.assert_not_awaited()


def test_admission_safe_response_keeps_honest_message():
    from server.services.saas.call_admission import NO_DIAL_CODES, safe_response

    assert "voice_service_unavailable" in NO_DIAL_CODES
    out = safe_response({"ok": False, "code": "voice_service_unavailable", "error": "x", "status": 503, "retry_after": 120})
    assert "voice service is temporarily unavailable" in out["error"] and out["retry_after"] == 120


def test_outbound_route_turns_refusal_into_http_error():
    from fastapi import HTTPException

    from server.routes.app_telephony import _raise_if_not_placed

    with pytest.raises(HTTPException) as info:
        _raise_if_not_placed({"ok": False, "code": "voice_service_unavailable", "status": 503,
                              "error": "We couldn't start this call", "retry_after": 120})
    assert info.value.status_code == 503
    assert info.value.detail["error"]["code"] == "voice_service_unavailable"
    assert info.value.headers == {"Retry-After": "120"}
    with pytest.raises(HTTPException) as legacy:
        _raise_if_not_placed({"ok": False, "code": "voice_preparation_failed", "error": "x"})
    assert legacy.value.status_code == 503
    with pytest.raises(HTTPException) as unknown:
        _raise_if_not_placed({"ok": False, "error": "The call could not be confirmed."})
    assert unknown.value.status_code == 502
    _raise_if_not_placed({"ok": True, "call_id": "c"})  # placed: no error


# ------------------------------------------------------------ admin endpoint

def test_admin_provider_health_endpoint(keys):
    from fastapi.testclient import TestClient

    from server.app import app
    from server.auth.dependencies import require_dev_session
    from server.auth.session import SessionData
    DEV_TEST_BASE_URL = "http://localhost"

    sarvam_key_pool.report_failure("primary", ph.CREDITS, component="llm", status=402,
                                   detail="HTTP 402 insufficient_quota_error", next_slot="secondary-1")
    sarvam_key_pool.report_success("secondary-1", component="llm")
    ph.provider_health.record_failure("cartesia", "tts", ph.AUTH, status=401, detail="HTTP 401")
    session = SessionData(kind="dev", subject="admin@example.com", tenant_id=None, role="platform_admin", issued_at=0)
    app.dependency_overrides[require_dev_session] = lambda: session
    try:
        with TestClient(app, base_url=DEV_TEST_BASE_URL) as client:
            res = client.get("/api/dev/admin/provider-health")
    finally:
        app.dependency_overrides.pop(require_dev_session, None)
    assert res.status_code == 200, res.text
    data = res.json()
    cards = {(c["component"], c["provider"]): c for g in data["components"] for c in g["providers"]}
    sarvam = cards[("llm", "sarvam")]
    assert sarvam["status"] == "degraded"
    assert "now using the secondary-1 key" in sarvam["headline"]
    assert sarvam["keys"]["activeSlot"] == "secondary-1"
    assert cards[("tts", "cartesia")]["status"] == "failing"
    assert "Cartesia: API key rejected" in cards[("tts", "cartesia")]["headline"]
    assert any(b["provider"] == "cartesia" and b["status"] == "failing" for b in data["banner"])
    assert data["overall"] == "failing"
    assert PRIMARY not in res.text and BACKUP not in res.text
