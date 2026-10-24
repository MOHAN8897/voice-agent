"""Regression tests for the browser voice WebSocket."""

from importlib import import_module
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,pipeline,profile_error", [
    ("low", "composed_voice", False),
    ("medium", "composed_voice", False),
    ("premium", "realtime_voice", False),
    ("low", "realtime_voice", False),
    ("low", "composed_voice", True),
])
async def test_web_agent_uses_selected_stack_and_private_ready_metadata(monkeypatch, tier, pipeline, profile_error):
    route = import_module("server.routes.web_agent_ws")
    agent_service_module = import_module("server.brain.agent_service")
    billing_module = import_module("server.services.saas.billing_wallet_service")
    lifecycle_module = import_module("server.call.call_lifecycle_service")
    voice_core_module = import_module("server.services.pstn_realtime_voice_core")
    composed_core_module = import_module("server.services.pstn_voice_core")
    voice_flow_module = import_module("server.services.pstn_voice_flow")
    playback_module = import_module("server.services.pstn_playback")
    failure_log_module = import_module("server.services.saas.session_failure_log")

    class FakeWebSocket:
        def __init__(self):
            self.query_params = {"agentId": "agent-1", "language": "hi-IN"}
            self.headers = {}
            self.scope = {"subprotocols": ["voxly-web-agent", "voxly-auth.test-token"]}
            self.events = []
            self.accepted_subprotocol = None
            self.ready = asyncio.Event()
            self.audio = []

        async def accept(self, subprotocol=None):
            self.accepted_subprotocol = subprotocol

        async def send_json(self, payload):
            self.events.append(payload)
            if payload.get("type") == "ready":
                self.ready.set()

        async def close(self, code=1000):
            self.close_code = code

        async def send_bytes(self, pcm):
            self.audio.append(pcm)

        async def receive(self):
            await self.ready.wait()
            return {"type": "websocket.disconnect"}

    class FakeVoiceLoop:
        def __init__(self, **_kwargs):
            # Exercise the stack model fallback used by adapters that don't expose one.
            self._adapter = SimpleNamespace()
            self._llm_provider = "openai"
            self.on_agent_wire = _kwargs["on_agent_wire"]

        def set_hangup_notice_handler(self, _handler):
            pass

        def set_hangup_handler(self, _handler):
            pass

        def set_barge_handler(self, _handler):
            pass

        async def start_call(self, *, play_greeting):
            assert play_greeting is True
            await self.on_agent_wire(b"\x01\x00" * 320)

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
            "default_tier": tier,
        }

    async def allow_wallet_usage(_tenant_id):
        pass

    stack_used = {}
    async def stack_override(_agent):
        assert _agent["languages"] == ["hi-IN"]
        if profile_error:
            from server.services.saas.voice_stack_profiles import VoiceProfileError
            raise VoiceProfileError("profile_revision_conflict", "Private configuration detail", status_code=409)
        stack_used.update({"value": {"pipeline": pipeline, "language": "hi-IN", "llm": {"provider": "openai", "model": "private-provider-model"}, "_voice_stack_snapshot": {"tier": tier} if pipeline == "composed_voice" else None}})
        return stack_used["value"]

    started_kwargs = {}
    async def start_call(**_kwargs):
        started_kwargs.update(_kwargs)
        return {"call_id": "call-1", "session_id": "session-1", "pipeline": pipeline}

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
    tracker = playback_module.EstimatedPlaybackTracker()
    tracker.note_sent_frames = Mock(wraps=tracker.note_sent_frames)
    monkeypatch.setattr(playback_module, "EstimatedPlaybackTracker", lambda **_kwargs: tracker)
    actual_factory = voice_flow_module.create_pstn_voice_loop
    loops = []

    def selected_factory(**kwargs):
        loop = actual_factory(**kwargs)
        loops.append(loop)
        if isinstance(loop, composed_core_module.PstnVoiceLoop):
            loop._archive.enqueue = Mock()
            loop.close = AsyncMock()
        return loop

    async def composed_start(self, *, play_greeting):
        assert play_greeting is True
        self.current_generation_id = "opening-1"
        await self._emit_agent_wire(b"\x01\x00" * 320)

    monkeypatch.setattr(composed_core_module.PstnVoiceLoop, "start_call", composed_start)
    monkeypatch.setattr(voice_flow_module, "create_pstn_voice_loop", selected_factory)
    monkeypatch.setattr(failure_log_module, "record_session_failure", lambda **_kwargs: None)

    websocket = FakeWebSocket()
    await route.web_agent_ws(websocket)

    if profile_error:
        assert any(event.get("type") == "error" for event in websocket.events)
        error = next(event for event in websocket.events if event.get("type") == "error")
        assert error["code"] == "profile_revision_conflict"
        assert "refresh" in error["message"]
        assert "Private configuration" not in str(websocket.events)
        assert not any(event.get("type") == "ready" for event in websocket.events)
        assert started_kwargs == {}
        assert loops == []
        assert websocket.audio == []
        tracker.note_sent_frames.assert_not_called()
        return

    ready = next((event for event in websocket.events if event.get("type") == "ready"), None)
    assert ready is not None, websocket.events
    assert ready["voiceProvider"] == "Enterprise Voice Network"
    assert ready["voiceModel"] == ({"low": "Economical", "medium": "Standard"}[tier] if pipeline == "composed_voice" else "Live voice")
    assert "private-provider-model" not in str(websocket.events)
    assert "openai" not in str(websocket.events).lower()
    assert ready["pipeline"] == pipeline
    assert ready["sampleRate"] == 16000
    assert websocket.audio == [b"\x01\x00" * 320]
    tracker.note_sent_frames.assert_called_once_with(1)
    if pipeline == "composed_voice":
        assert isinstance(loops[0], composed_core_module.PstnVoiceLoop)
        assert loops[0].sample_rate == 16000
        assert loops[0].tts_output_codec == "linear16"
        assert loops[0].current_output_codec == "L16"
    else:
        assert isinstance(loops[0], FakeVoiceLoop)
    assert websocket.accepted_subprotocol == "voxly-web-agent"
    assert stack_used["value"]["language"] == "hi-IN"
    assert started_kwargs["language"] == "hi-IN"
    assert started_kwargs["tenant_id"] == "tenant-1"
    assert started_kwargs["stack_override"] is stack_used["value"]


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
