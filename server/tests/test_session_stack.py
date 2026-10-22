"""Session stack resolution tests — Phase 1."""
from __future__ import annotations

import pytest

from server.services.runtime_settings import runtime_settings
from server.config.env import Settings
from server.providers.registry import ProviderRegistry
from server.providers.session_stack import infer_stt_from_runtime, infer_tts_from_runtime, resolve_stack_for_session


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


def test_infer_cartesia_and_sarvam_models():
    stt_provider, stt_model = infer_stt_from_runtime(
        model="ink-whisper",
        default_provider="sarvam",
        default_model="saaras:v3",
        cartesia_on=True,
    )
    assert stt_provider == "cartesia"
    assert stt_model == "ink-whisper"

    stt_off_provider, stt_off_model = infer_stt_from_runtime(
        model="ink-whisper",
        default_provider="sarvam",
        default_model="saaras:v3-realtime",
        cartesia_on=False,
    )
    assert stt_off_provider == "sarvam"
    assert stt_off_model == "saaras:v3-realtime"

    tts_provider, tts_model = infer_tts_from_runtime(
        model="sonic-3.5",
        speaker="4418bb06-8329-49a1-bb11-53bb64ca0547",
        default_provider="sarvam",
        default_model="bulbul:v3",
        cartesia_on=True,
    )
    assert tts_provider == "cartesia"
    assert tts_model == "sonic-3.5"

    sarvam_provider, sarvam_model = infer_tts_from_runtime(
        model="bulbul:v3",
        speaker="shubh",
        default_provider="sarvam",
        default_model="bulbul:v3",
        cartesia_on=True,
    )
    assert sarvam_provider == "sarvam"
    assert sarvam_model == "bulbul:v3"


def test_runtime_settings_accepts_cartesia_stt_model():
    runtime_settings.clear("cartesia-stt-model")
    values = runtime_settings.update("cartesia-stt-model", {"sttModel": "ink-whisper"})
    assert values["sttModel"] == "ink-whisper"
    runtime_settings.clear("cartesia-stt-model")
