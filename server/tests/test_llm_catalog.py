"""LLM catalog and registry model list tests."""
from __future__ import annotations

import pytest

from server.config.env import Settings
from server.providers.llm_catalog import llm_models_for_provider
from server.providers.registry import ProviderRegistry
from server.services.dev_secrets_store import dev_secrets_store


@pytest.fixture
def llm_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-test")
    monkeypatch.setenv("ENABLE_OPENAI", "true")
    monkeypatch.setenv("ENABLE_DEEPSEEK", "true")
    monkeypatch.setenv("ENABLE_GEMINI", "true")
    from server.config.env import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_openai_llm_catalog_uses_labels():
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    models = llm_models_for_provider("openai", settings)
    ids = {m["id"] for m in models}
    assert "gpt-5.6-luna" in ids
    luna = next(m for m in models if m["id"] == "gpt-5.6-luna")
    assert "Luna" in luna["label"]


def test_deepseek_llm_catalog_lists_documented_models():
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    models = llm_models_for_provider("deepseek", settings)
    ids = {m["id"] for m in models}
    assert "deepseek-chat" in ids
    assert "deepseek-reasoner" in ids


def test_gemini_llm_catalog_lists_latest_models():
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    models = llm_models_for_provider("gemini", settings)
    ids = {m["id"] for m in models}
    assert "gemini-3.8-flash" in ids
    assert "gemini-3.7-flash" in ids
    assert "gemini-3.5-flash-lite" in ids
    assert "gemini-3.5-flash" in ids
    lite = next(m for m in models if m["id"] == "gemini-3.5-flash-lite")
    assert lite.get("default") is True


def test_registry_exposes_llm_models_when_enabled(llm_settings):
    dev_secrets_store.update(
        {
            "enable_openai": True,
            "enable_deepseek": True,
            "enable_gemini": True,
            "openai_api_key": "sk-overlay",
            "deepseek_api_key": "ds-overlay",
            "gemini_api_key": "gem-overlay",
        }
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    catalog = ProviderRegistry(settings).get_catalog()
    openai = next(p for p in catalog["providers"] if p["id"] == "openai")
    deepseek = next(p for p in catalog["providers"] if p["id"] == "deepseek")
    gemini = next(p for p in catalog["providers"] if p["id"] == "gemini")
    assert len(openai["models"]["llm"]) >= 3
    assert len(deepseek["models"]["llm"]) >= 2
    assert len(gemini["models"]["llm"]) >= 5
    gemini_ids = {m["id"] for m in gemini["models"]["llm"]}
    assert "gemini-3.8-flash" in gemini_ids
    assert "gemini-3.7-flash" in gemini_ids
    assert "gemini-3.5-flash-lite" in gemini_ids
    assert gemini["adapter_available"] is True
    assert gemini["healthy"] is True
    assert ProviderRegistry(settings).get_llm("gemini").provider_id == "gemini"
    dev_secrets_store.remove_overlay_key("enable_openai")
    dev_secrets_store.remove_overlay_key("enable_deepseek")
    dev_secrets_store.remove_overlay_key("enable_gemini")
    dev_secrets_store.remove_overlay_key("openai_api_key")
    dev_secrets_store.remove_overlay_key("deepseek_api_key")
    dev_secrets_store.remove_overlay_key("gemini_api_key")
