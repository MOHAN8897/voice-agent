"""Session stack resolution tests — Phase 1."""
from __future__ import annotations

import pytest

from server.config.env import Settings
from server.providers.registry import ProviderRegistry
from server.providers.session_stack import resolve_stack_for_session


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("VOICE_AGENT_CONFIG_MODE", "frontend")
    from server.config.env import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_resolve_stack_for_session_default(env):
    stack = resolve_stack_for_session("default")
    assert stack.stt.provider == "sarvam"
    assert stack.llm.provider == "openai"
    assert stack.combination_id


def test_resolve_stack_env_mode(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("VOICE_AGENT_CONFIG_MODE", "env")
    monkeypatch.setenv("VOICE_AGENT_TIER", "low")
    from server.config.env import get_settings

    get_settings.cache_clear()
    stack = resolve_stack_for_session("any")
    assert stack.tier == "low"
    assert stack.mode == "env"
    get_settings.cache_clear()
