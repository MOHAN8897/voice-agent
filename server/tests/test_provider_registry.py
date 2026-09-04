"""Tests for provider registry — Phase 1."""
from __future__ import annotations

import pytest

from server.config.env import Settings
from server.providers.registry import ProviderRegistry, init_provider_registry


@pytest.fixture
def base_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("ENABLE_SARVAM", "true")
    monkeypatch.setenv("ENABLE_OPENAI", "true")
    monkeypatch.setenv("ENABLE_DEEPSEEK", "false")
    monkeypatch.setenv("ENABLE_GEMINI", "false")
    monkeypatch.setenv("ENABLE_CARTESIA", "false")
    from server.config.env import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_catalog_includes_sarvam_and_openai(base_settings):
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    registry = ProviderRegistry(settings)
    catalog = registry.get_catalog()
    ids = {p["id"] for p in catalog["providers"]}
    assert "sarvam" in ids
    assert "openai" in ids
    assert catalog["fx_rate_inr"] == settings.fx_rate_inr


def test_disabled_provider_filtered(base_settings, monkeypatch):
    monkeypatch.setenv("ENABLE_OPENAI", "false")
    from server.config.env import get_settings
    from server.services.dev_secrets_store import dev_secrets_store

    get_settings.cache_clear()
    monkeypatch.setattr(
        dev_secrets_store,
        "effective",
        lambda field, default=None: getattr(get_settings(), field, default),
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    registry = ProviderRegistry(settings)
    ids = {p["id"] for p in registry.get_catalog()["providers"]}
    assert "openai" not in ids
    assert "sarvam" in ids
    get_settings.cache_clear()


def test_no_secrets_in_catalog(base_settings):
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    catalog = ProviderRegistry(settings).get_catalog()
    text = str(catalog)
    assert "sk-test" not in text
    assert "sarvam-test" not in text


def test_init_singleton(base_settings):
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    r1 = init_provider_registry(settings)
    from server.providers.registry import get_provider_registry

    r2 = get_provider_registry()
    assert r1 is r2
