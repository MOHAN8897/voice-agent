"""Regression tests for the browser voice WebSocket."""

from importlib import import_module
import asyncio
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_web_agent_ready_uses_stack_model_when_adapter_has_no_model(monkeypatch):
    route = import_module("server.routes.web_agent_ws")
    agent_service_module = import_module("server.brain.agent_service")
    billing_module = import_module("server.services.saas.billing_wallet_service")
    lifecycle_module = import_module("server.call.call_lifecycle_service")
    voice_core_module = import_module("server.services.pstn_realtime_voice_core")
    failure_log_module = import_module("server.services.saas.session_failure_log")

    class FakeWebSocket:
        def __init__(self):
            self.query_params = {"agentId": "agent-1", "language": "hi-IN"}
            self.headers = {}
            self.scope = {"subprotocols": ["voxly-web-agent", "voxly-auth.test-token"]}
            self.events = []
            self.accepted_subprotocol = None
            self.ready = asyncio.Event()

        async def accept(self, subprotocol=None):
            self.accepted_subprotocol = subprotocol

        async def send_json(self, payload):
            self.events.append(payload)
            if payload.get("type") == "ready":
                self.ready.set()

        async def close(self, code=1000):
            self.close_code = code

        async def receive(self):
            await self.ready.wait()
            return {"type": "websocket.disconnect"}

    class FakeVoiceLoop:
        def __init__(self, **_kwargs):
            # Exercise the stack model fallback used by adapters that don't expose one.
            self._adapter = SimpleNamespace()
            self._llm_provider = "openai"

        def set_hangup_notice_handler(self, _handler):
            pass

        def set_hangup_handler(self, _handler):
            pass

        def set_barge_handler(self, _handler):
            pass

        async def start_call(self, *, play_greeting):
            assert play_greeting is True

        async def close(self):
            pass

    async def verified_principal(_token):
        return SimpleNamespace(user_id="user-1", tenant_id="tenant-1")

    async def get_agent(_agent_id, *, tenant_id):
        assert tenant_id == "tenant-1"
        return {
            "agent_id": "agent-1",
            "status": "active",
            "active_compiled_brain_version": 1,
            "languages": ["en-IN"],
        }

    async def allow_wallet_usage(_tenant_id):
        pass

    stack_used = {}
    async def stack_override(_agent):
        stack_used.update({"value": {"language": "en-IN", "llm": {"provider": "openai", "model": "stack-model"}}})
        return stack_used["value"]

    started_kwargs = {}
    async def start_call(**_kwargs):
        started_kwargs.update(_kwargs)
        return {"call_id": "call-1", "session_id": "session-1", "pipeline": "realtime"}

    async def end_call(_call_id, *, reason):
        assert reason == "user_stop"

    monkeypatch.setattr(route._web_agent_limiter, "allow", lambda _key: (True, 0))
    monkeypatch.setattr(route, "principal_from_verified_token", verified_principal)
    monkeypatch.setattr(route, "subscriber_workspace_tenant_id", lambda _principal: "tenant-1")
    monkeypatch.setattr(agent_service_module.agent_service, "get_agent", get_agent)
    monkeypatch.setattr(billing_module, "assert_wallet_allows_usage", allow_wallet_usage)
    monkeypatch.setattr(
        route,
        "saas_stack_override_for_agent",
        stack_override,
    )
    monkeypatch.setattr(lifecycle_module.call_lifecycle_service, "start", start_call)
    monkeypatch.setattr(lifecycle_module.call_lifecycle_service, "end", end_call)
    monkeypatch.setattr(voice_core_module, "PstnRealtimeVoiceLoop", FakeVoiceLoop)
    monkeypatch.setattr(failure_log_module, "record_session_failure", lambda **_kwargs: None)

    websocket = FakeWebSocket()
    await route.web_agent_ws(websocket)

    ready = next((event for event in websocket.events if event.get("type") == "ready"), None)
    assert ready is not None, websocket.events
    assert ready["voiceProvider"] == "openai"
    assert ready["voiceModel"] == "stack-model"
    assert websocket.accepted_subprotocol == "voxly-web-agent"
    assert stack_used["value"]["language"] == "hi-IN"
    assert started_kwargs["language"] == "hi-IN"


def test_web_agent_token_prefers_subprotocol_over_url_query():
    route = import_module("server.routes.web_agent_ws")
    websocket = SimpleNamespace(
        scope={"subprotocols": ["voxly-web-agent", "voxly-auth.header-token"]},
        query_params={"token": "query-token"},
        headers={"authorization": "Bearer authorization-token"},
    )

    assert route._ws_token(websocket) == "header-token"


def test_web_agent_token_keeps_legacy_query_and_authorization_fallbacks():
    route = import_module("server.routes.web_agent_ws")
    query_ws = SimpleNamespace(scope={}, query_params={"token": "query-token"}, headers={})
    auth_ws = SimpleNamespace(scope={}, query_params={}, headers={"authorization": "Bearer authorization-token"})

    assert route._ws_token(query_ws) == "query-token"
    assert route._ws_token(auth_ws) == "authorization-token"
