"""WS registry factory smoke tests — Phase 1 §4.6."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from server.config.env import Settings
from server.providers.registry import ProviderRegistry
from server.routes import ws as ws_mod


@pytest.fixture
def registry_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("USE_PROVIDER_REGISTRY", "true")
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_connect_stt_upstream_uses_registry(registry_settings, monkeypatch):
    monkeypatch.setenv("USE_PROVIDER_REGISTRY", "true")
    from server.config.env import get_settings

    get_settings.cache_clear()
    adapter = MagicMock()
    adapter.connect_realtime.return_value = "upstream-cm"
    registry = ProviderRegistry(registry_settings)
    registry._stt["sarvam"] = adapter

    with patch.object(ws_mod, "get_provider_registry", return_value=registry), patch.object(
        ws_mod, "resolve_stack_for_session"
    ) as mock_resolve:
        from server.providers.base import ResolvedStack, StageSelection

        mock_resolve.return_value = ResolvedStack(
            combination_id="abc123",
            tier="medium",
            mode="frontend",
            stt=StageSelection("sarvam", "saaras:v3-realtime", {"stream_type": "fast"}),
            llm=StageSelection("openai", "gpt-5.6-luna", {}),
            tts=StageSelection("sarvam", "bulbul:v3", {}),
            language="te-IN",
        )
        result = ws_mod._connect_stt_upstream(session_id="sess-1", language_code="te-IN")
        assert result == "upstream-cm"
        adapter.connect_realtime.assert_called_once()
    get_settings.cache_clear()


def test_connect_tts_upstream_uses_registry(registry_settings, monkeypatch):
    monkeypatch.setenv("USE_PROVIDER_REGISTRY", "true")
    from server.config.env import get_settings

    get_settings.cache_clear()
    adapter = MagicMock()
    adapter.connect_stream.return_value = "tts-upstream"
    registry = ProviderRegistry(registry_settings)
    registry._tts["sarvam"] = adapter

    with patch.object(ws_mod, "get_provider_registry", return_value=registry), patch.object(
        ws_mod, "resolve_stack_for_session"
    ) as mock_resolve:
        from server.providers.base import ResolvedStack, StageSelection

        mock_resolve.return_value = ResolvedStack(
            combination_id="abc123",
            tier="medium",
            mode="frontend",
            stt=StageSelection("sarvam", "saaras:v3-realtime", {}),
            llm=StageSelection("openai", "gpt-5.6-luna", {}),
            tts=StageSelection("sarvam", "bulbul:v3", {"speaker": "shubh"}),
            language="te-IN",
        )
        result = ws_mod._connect_tts_upstream("bulbul:v3", session_id="sess-1")
        assert result == "tts-upstream"
        adapter.connect_stream.assert_called_once()
    get_settings.cache_clear()


def test_connect_stt_uses_locked_call_stack(registry_settings, monkeypatch):
    monkeypatch.setenv("USE_PROVIDER_REGISTRY", "true")
    from datetime import datetime, timezone

    from server.call.call_context import CallContext, clear_all, put
    from server.config.env import get_settings
    from server.providers.base import ResolvedStack, StageSelection

    get_settings.cache_clear()
    clear_all()
    adapter = MagicMock()
    adapter.connect_realtime.return_value = "call-stack-cm"
    registry = ProviderRegistry(registry_settings)
    registry._stt["sarvam"] = adapter
    put(
        CallContext(
            call_id="locked-call",
            tenant_id="t",
            agent_id="a",
            session_id="sess-1",
            channel="browser",
            direction="inbound",
            environment="development",
            tier="medium",
            resolved_stack=ResolvedStack(
                combination_id="locked",
                tier="medium",
                mode="frontend",
                stt=StageSelection("sarvam", "saaras:v3-realtime", {"stream_type": "fast"}),
                llm=StageSelection("openai", "gpt-5.6-luna", {}),
                tts=StageSelection("sarvam", "bulbul:v3", {}),
                language="te-IN",
            ),
            compiled_brain_version=None,
            compiled_brain_text=None,
            started_at=datetime.now(timezone.utc),
            storage_path="data/calls/locked-call/",
        )
    )
    with patch.object(ws_mod, "get_provider_registry", return_value=registry):
        result = ws_mod._connect_stt_upstream(session_id="sess-1", call_id="locked-call", language_code="te-IN")
        assert result == "call-stack-cm"
        adapter.connect_realtime.assert_called_once()
    clear_all()
    get_settings.cache_clear()
