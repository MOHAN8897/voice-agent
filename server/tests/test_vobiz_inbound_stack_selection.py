"""Signed inbound callbacks pin the agent's saved voice stack before media."""
import base64
import hashlib
import hmac
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET

import pytest
from fastapi import HTTPException
from starlette.requests import Request


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,pipeline,failure", [
    ("low", "composed_voice", None),
    ("medium", "composed_voice", None),
    ("premium", "realtime_voice", None),
    ("low", "realtime_voice", None),
    ("low", "composed_voice", "profile_unavailable"),
    ("low", "composed_voice", "agent_unavailable"),
])
async def test_inbound_uses_tenant_saved_stack_and_fails_closed(monkeypatch, tier, pipeline, failure):
    from server.brain.agent_service import agent_service
    from server.routes import vobiz
    from server.services.dev_secrets_store import dev_secrets_store
    from server.services.saas import call_admission, pstn_saas_stack, telephony_profile
    from server.services.vobiz_client import VobizCallRegistry, VobizStreamTokens

    tenant_id = "00000000-0000-4000-8000-000000000001"
    agent = {"agent_id": "saved-agent", "tenant_id": tenant_id, "default_tier": tier, "languages": ["te-IN"],
             "voice_settings": {"stackSelectionVersion": 1} if pipeline == "composed_voice" else {}}
    selected = {"pipeline": pipeline, "language": "te-IN", "llm": {"provider": "sarvam" if pipeline == "composed_voice" else "gemini", "model": "selected-model"}}
    if pipeline == "composed_voice":
        selected.update(voice_flow="composed_stages", _voice_stack_snapshot={"tier": tier, "profileRevision": 7, "voiceId": "selected-voice"})

    registry = VobizCallRegistry()
    tokens = VobizStreamTokens()
    monkeypatch.setattr(registry, "_redis", lambda: None)
    monkeypatch.setattr(tokens, "_redis", lambda: None)
    monkeypatch.setattr(vobiz, "vobiz_call_registry", registry)
    monkeypatch.setattr(vobiz, "vobiz_stream_tokens", tokens)
    monkeypatch.setattr(dev_secrets_store, "effective_secret", lambda _key: None)
    monkeypatch.setattr(vobiz, "get_settings", lambda: SimpleNamespace(app_environment="production", vobiz_auth_token="unit-inbound-secret", pstn_enforce_wallet_on_inbound=False))
    monkeypatch.setattr(vobiz, "public_api_base", lambda: "https://voice.example")
    monkeypatch.setattr(vobiz, "ws_public_base", lambda: "wss://voice.example")
    monkeypatch.setattr(vobiz, "_parse_vobiz_payload", AsyncMock(return_value={"CallUUID": "selected-inbound-call", "To": "test-destination", "Direction": "inbound"}))
    monkeypatch.setattr(telephony_profile, "profile_for_number", AsyncMock(return_value={"agent_id": "saved-agent", "tenant_id": tenant_id, "agent_status": "active", "vobiz_account_scope": "platform"}))

    @asynccontextmanager
    async def factory():
        yield SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(status="active", deleted_at=None)))

    monkeypatch.setattr("server.db.connection.get_session_factory", lambda: factory)
    get_agent = AsyncMock(return_value=agent, side_effect=KeyError("saved-agent") if failure == "agent_unavailable" else None)
    monkeypatch.setattr(agent_service, "get_agent", get_agent)
    resolve_voice = AsyncMock(return_value=selected, side_effect=HTTPException(status_code=409, detail={"error": {"code": "profile_unavailable"}}) if failure == "profile_unavailable" else None)
    monkeypatch.setattr(pstn_saas_stack, "saas_stack_override_for_agent", resolve_voice)
    reserve = AsyncMock(return_value=("inbound-admission", {}))
    monkeypatch.setattr(call_admission, "reserve", reserve)
    monkeypatch.setattr(call_admission, "finish", AsyncMock())
    monkeypatch.setattr(call_admission, "provider_event", AsyncMock())

    signature = base64.b64encode(hmac.new(b"unit-inbound-secret", b"https://voice.example/api/vobiz/answer.unit-nonce", hashlib.sha256).digest()).decode()
    request = Request({"type": "http", "scheme": "https", "method": "POST", "server": ("voice.example", 443),
                       "path": "/api/vobiz/answer", "query_string": b"", "headers": [
                           (b"x-vobiz-signature-v3", signature.encode()), (b"x-vobiz-signature-v3-nonce", b"unit-nonce")
                       ]})
    response = await vobiz.vobiz_answer(request)
    get_agent.assert_awaited_once_with("saved-agent", tenant_id=tenant_id)

    if failure:
        assert b"<Hangup" in response.body
        assert b"<Stream" not in response.body
        assert registry.get("selected-inbound-call") is None
        reserve.assert_not_awaited()
        if failure == "agent_unavailable":
            resolve_voice.assert_not_awaited()
        return

    stream = ET.fromstring(response.body).find("Stream")
    assert stream.attrib["bidirectional"] == "true"
    assert stream.attrib["contentType"] == "audio/x-l16;rate=16000"
    token = parse_qs(urlparse(stream.text).query)["token"][0]
    metadata = tokens.peek(token)
    if pipeline != "composed_voice":
        assert metadata["tier"] is None
        assert metadata["language"] is None
        assert metadata["stack_override"] is None
        assert registry.get("selected-inbound-call")["stack_override"] is None
        resolve_voice.assert_not_awaited()
        return

    assert metadata["tier"] == tier
    assert metadata["language"] == "te-IN"
    assert metadata["stack_override"] == selected
    assert registry.get("selected-inbound-call")["stack_override"] == selected
    resolve_voice.assert_awaited_once_with(agent)

    # Answer retries retain the admitted revision even if the catalog changes.
    get_agent.side_effect = AssertionError("saved selection must not be reloaded")
    resolve_voice.side_effect = AssertionError("saved selection must not be re-resolved")
    repeated = await vobiz.vobiz_answer(request)
    assert b"<Stream" in repeated.body
    get_agent.assert_awaited_once()
    resolve_voice.assert_awaited_once()
