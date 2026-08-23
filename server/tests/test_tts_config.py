"""Tests for canonical TTS config resolver."""
from server.config.env import get_settings
from server.services.runtime_settings import runtime_settings
from server.services.tts_config import TtsConfigError, resolve_tts_config
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
