"""Tests for L1 stack resolver — Phase 1."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from server.config.env import Settings
from server.providers.base import StackSelection, StageSelection
from server.providers.registry import ProviderRegistry
from server.providers.resolver import StackResolver
from server.utils.errors import AppError, ErrorCode


@pytest.fixture
def resolver(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("ENABLE_SARVAM", "true")
    monkeypatch.setenv("ENABLE_OPENAI", "true")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    registry = ProviderRegistry(settings)
    return StackResolver(settings, registry)


def test_env_mode_resolves_medium_tier(resolver):
    stack = resolver.resolve(mode="env", tier="medium", language="te-IN")
    assert stack.stt.provider == "sarvam"
    assert stack.llm.provider == "openai"
    assert stack.tts.provider == "sarvam"
    assert stack.combination_id
    assert len(stack.combination_id) == 16


def test_frontend_mode_with_valid_selection(resolver):
    selection = StackSelection(
        stt=StageSelection("sarvam", "saaras:v3", {}),
        llm=StageSelection("openai", "gpt-5.6-luna", {}),
        tts=StageSelection("sarvam", "bulbul:v3", {}),
        language="te-IN",
    )
    stack = resolver.resolve(mode="frontend", user_selection=selection, language="te-IN")
    assert stack.mode == "frontend"
    assert stack.stt.model == "saaras:v3"


def test_disabled_provider_rejected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("ENABLE_OPENAI", "false")
    monkeypatch.setenv("ENABLE_DEEPSEEK", "false")
    from server.config.env import get_settings

    get_settings.cache_clear()
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    registry = ProviderRegistry(settings)
    resolver = StackResolver(settings, registry)
    with patch(
        "server.services.dev_fallback_store.dev_fallback_store.get_chains",
        return_value={"stt": ["sarvam"], "llm": ["openai"], "tts": ["sarvam"]},
    ):
        with pytest.raises(AppError) as exc:
            resolver.resolve(mode="env", tier="medium")
    assert exc.value.code == ErrorCode.PROVIDER_DISABLED
    get_settings.cache_clear()


def test_stack_override_rejected_in_production(resolver):
    with pytest.raises(AppError) as exc:
        resolver.resolve(
            mode="env",
            tier="low",
            stack_override={"stt": {"model": "saaras:v3"}},
            environment="production",
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_resolver_rejects_gemini(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-test")
    monkeypatch.setenv("ENABLE_SARVAM", "true")
    monkeypatch.setenv("ENABLE_OPENAI", "true")
    monkeypatch.setenv("ENABLE_GEMINI", "true")
    from server.config.env import get_settings
    from server.services.dev_secrets_store import dev_secrets_store

    get_settings.cache_clear()
    dev_secrets_store.update({"enable_gemini": True, "gemini_api_key": "gem-test"})
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    registry = ProviderRegistry(settings)
    resolver = StackResolver(settings, registry)
    selection = StackSelection(
        stt=StageSelection("sarvam", "saaras:v3", {}),
        llm=StageSelection("gemini", "gemini-3.5-flash-lite", {}),
        tts=StageSelection("sarvam", "bulbul:v3", {}),
        language="te-IN",
    )
    stack = resolver.resolve(mode="frontend", user_selection=selection, language="te-IN")
    assert stack.llm.provider == "openai"
    assert registry.is_provider_enabled("gemini", "llm") is False
    assert all(p.get("id") != "gemini" for p in registry.get_catalog()["providers"])
    dev_secrets_store.remove_overlay_key("enable_gemini")
    dev_secrets_store.remove_overlay_key("gemini_api_key")
    get_settings.cache_clear()
