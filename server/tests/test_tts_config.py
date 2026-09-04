"""Tests for canonical TTS config resolver."""
from server.config.env import get_settings
from server.providers.registry import init_provider_registry
from server.services.runtime_settings import runtime_settings
from server.services.tts_config import TtsConfigError, merge_ws_tts_config, resolve_tts_config
import pytest


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-tts-cfg")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test-tts-cfg")
    get_settings.cache_clear()
    runtime_settings.clear("cfg-test")
    yield
    runtime_settings.clear("cfg-test")
    get_settings.cache_clear()


def test_resolve_defaults_from_env():
    cfg = resolve_tts_config("cfg-test")
    assert cfg["speaker"] == "shubh"
    assert cfg["model"] == "bulbul:v3"


def test_runtime_speaker_overrides_env():
    runtime_settings.update("cfg-test", {"ttsSpeaker": "ritu"})
    cfg = resolve_tts_config("cfg-test")
    assert cfg["speaker"] == "ritu"


def test_invalid_speaker_raises():
    with pytest.raises(TtsConfigError):
        resolve_tts_config("cfg-test", speaker="not_a_voice", model="bulbul:v3")


def test_cartesia_voice_uuid_not_validated_as_sarvam_speaker(monkeypatch):
    monkeypatch.setenv("ENABLE_CARTESIA", "true")
    monkeypatch.setenv("CARTESIA_API_KEY", "sk-cartesia-test")
    get_settings.cache_clear()
    init_provider_registry()
    runtime_settings.update(
        "cfg-test",
        {
            "ttsSpeaker": "4418bb06-8329-49a1-bb11-53bb64ca0547",
            "ttsModel": "sonic-3.5",
        },
    )
    cfg = resolve_tts_config("cfg-test", language_code="te-IN")
    assert cfg["provider"] == "cartesia"
    assert cfg["model"] == "sonic-3.5"
    assert cfg["speaker"] == "4418bb06-8329-49a1-bb11-53bb64ca0547"


def test_cartesia_uuid_falls_back_to_sarvam_when_cartesia_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_CARTESIA", "false")
    monkeypatch.setenv("CARTESIA_API_KEY", "")
    get_settings.cache_clear()
    init_provider_registry()
    runtime_settings.update(
        "cfg-test",
        {
            "ttsSpeaker": "4418bb06-8329-49a1-bb11-53bb64ca0547",
            "ttsModel": "sonic-3.5",
        },
    )
    cfg = resolve_tts_config("cfg-test", language_code="te-IN")
    assert cfg["provider"] == "sarvam"
    assert cfg["model"] == "bulbul:v3"
    assert cfg["speaker"] == "shubh"


def test_merge_ws_ignores_stale_client_speaker():
    runtime_settings.update("cfg-test", {"ttsSpeaker": "priya"})
    cfg = merge_ws_tts_config(
        "cfg-test",
        {"speaker": "shubh", "language_code": "te-IN"},
        language_code="te-IN",
        ws_model="bulbul:v3",
    )
    assert cfg["speaker"] == "priya"
