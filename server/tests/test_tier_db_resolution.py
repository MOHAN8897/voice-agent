"""Tier DB cache drives resolver when mode=env."""
from __future__ import annotations

import pytest

from server.config.env import Settings
from server.db.tier_store import clear_tier_cache_for_tests, get_cached_tier_stack, upsert_tier_assignment
from server.providers.registry import ProviderRegistry
from server.providers.resolver import StackResolver


@pytest.fixture
def registry_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    from server.config.env import get_settings

    get_settings.cache_clear()
    yield
    clear_tier_cache_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_resolver_uses_tier_cache(registry_settings):
    clear_tier_cache_for_tests()
    payload = {
        "combination_id": "abc123",
        "tier": "medium",
        "mode": "env",
        "language": "te-IN",
        "stt": {"provider": "sarvam", "model": "saaras:v3-realtime", "config": {}},
        "llm": {"provider": "openai", "model": "gpt-5.6-luna", "config": {}},
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {}},
    }
    await upsert_tier_assignment("development", "medium", "abc123", payload)
    cached = get_cached_tier_stack("development", "medium")
    assert cached is not None
    assert cached.stt.model == "saaras:v3-realtime"

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    resolver = StackResolver(settings, ProviderRegistry(settings))
    resolved = resolver.resolve(mode="env", tier="medium", environment="development")
    assert resolved.stt.model == "saaras:v3-realtime"
    from server.providers.base import StackSelection

    expected_id = StackResolver._combination_id(
        StackSelection(stt=cached.stt, llm=cached.llm, tts=cached.tts, language=cached.language, voice_preset=cached.voice_preset)
    )
    assert resolved.combination_id == expected_id
