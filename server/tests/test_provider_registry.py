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


def test_composed_model_allowlists_honor_persisted_admin_configuration(base_settings, monkeypatch):
    from server.services.dev_secrets_store import dev_secrets_store

    overrides = {
        "sarvam_llm_models_csv": "sarvam-105b-conversations,sarvam-105b-conversations",
        "gemini_tts_models_csv": "gemini-3.8-flash-lite-tts",
        "enable_gemini": True,
    }
    monkeypatch.setattr(dev_secrets_store, "effective", lambda field, default=None: overrides.get(field, default))
    monkeypatch.setattr(dev_secrets_store, "effective_secret", lambda field: "unit-test-placeholder")
    settings = Settings(_env_file=None)
    premium_before = {key: value for key, value in settings.model_dump().items() if key.startswith("voice_premium_")}
    registry = ProviderRegistry(settings)
    providers = {row["id"]: row for row in registry.get_catalog()["providers"]}
    assert [row["id"] for row in providers["sarvam"]["models"]["llm"]] == ["sarvam-105b-conversations"]
    assert providers["gemini"]["models"]["tts"][0]["id"] == "gemini-3.8-flash-lite-tts"
    assert registry.is_model_allowed("sarvam", "llm", "sarvam-105b-conversations")
    assert registry.is_model_allowed("gemini", "tts", "gemini-3.8-flash-lite-tts")
    assert {key: value for key, value in settings.model_dump().items() if key.startswith("voice_premium_")} == premium_before
