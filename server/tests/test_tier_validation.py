"""Tier validation tests — Phase 1."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server.app as app_mod
from server.config.env import Settings
from server.providers.registry import ProviderRegistry
from server.providers.resolver import StackResolver
from server.utils.errors import AppError, ErrorCode


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    from server.config.env import get_settings

    get_settings.cache_clear()
    yield TestClient(app_mod.app)
    get_settings.cache_clear()


def test_tiers_endpoint_lists_three_tiers(client):
    r = client.get("/api/tiers")
    assert r.status_code == 200
    tiers = {t["tier"] for t in r.json()["tiers"]}
    assert tiers == {"low", "medium", "premium"}


def test_tier_resolved_returns_stack(client):
    r = client.get("/api/tiers/medium/resolved")
    assert r.status_code == 200
    body = r.json()
    assert body["stt"]["provider"] == "sarvam"
    assert body["combination_id"]


def test_unknown_tier_404(client):
    r = client.get("/api/tiers/ultra/resolved")
    assert r.status_code == 404


def test_invalid_model_rejected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    registry = ProviderRegistry(settings)
    resolver = StackResolver(settings, registry)
    from server.providers.base import StackSelection, StageSelection

    bad = StackSelection(
        stt=StageSelection("sarvam", "nonexistent-model", {}),
        llm=StageSelection("openai", "gpt-5.6-luna", {}),
        tts=StageSelection("sarvam", "bulbul:v3", {}),
    )
    with pytest.raises(AppError) as exc:
        resolver.resolve(mode="frontend", user_selection=bad)
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_benchmarks_disabled_by_default(client):
    r = client.get("/api/benchmarks")
    assert r.status_code == 403
