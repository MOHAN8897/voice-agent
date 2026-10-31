"""Tests for canonical TTS config resolver."""
from types import SimpleNamespace

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
    from server.providers import voice_inventory
    original = voice_inventory.voices_for_model
    monkeypatch.setattr(voice_inventory, "_voice_indexes", {})
    monkeypatch.setattr(voice_inventory, "voices_for_model", lambda provider, model: [
        {"id": "4418bb06-8329-49a1-bb11-53bb64ca0547", "providerVoiceId": "4418bb06-8329-49a1-bb11-53bb64ca0547", "languages": ["te-IN"]}
    ] if provider == "cartesia" else original(provider, model))
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


def test_disabled_selected_cartesia_voice_never_falls_back_to_sarvam(monkeypatch):
    monkeypatch.setenv("ENABLE_CARTESIA", "false")
    monkeypatch.setenv("CARTESIA_API_KEY", "")
    from server.services.dev_secrets_store import dev_secrets_store

    get_settings.cache_clear()
    monkeypatch.setattr(
        dev_secrets_store,
        "effective",
        lambda field, default=None: getattr(get_settings(), field, default),
    )
    monkeypatch.setattr(dev_secrets_store, "effective_secret", lambda field: None)
    init_provider_registry()
    runtime_settings.update(
        "cfg-test",
        {
            "ttsSpeaker": "4418bb06-8329-49a1-bb11-53bb64ca0547",
            "ttsModel": "sonic-3.5",
        },
    )
    from server.utils.errors import AppError

    with pytest.raises(AppError, match="unavailable"):
        resolve_tts_config("cfg-test", language_code="te-IN")


def test_active_call_stack_ignores_stale_runtime_provider(monkeypatch):
    import server.services.tts_config as tts_config

    monkeypatch.setenv("ENABLE_CARTESIA", "true")
    monkeypatch.setenv("CARTESIA_API_KEY", "sk-cartesia-test")
    get_settings.cache_clear()
    runtime_settings.update(
        "cfg-test",
        {
            "ttsModel": "sonic-3.5",
            "ttsSpeaker": "4418bb06-8329-49a1-bb11-53bb64ca0547",
        },
    )
    locked = SimpleNamespace(
        tts=SimpleNamespace(
            provider="sarvam",
            model="bulbul:v3",
            config={"speaker": "shubh"},
        )
    )
    monkeypatch.setattr(tts_config, "_stack_for_session", lambda *_args: locked)

    cfg = resolve_tts_config("cfg-test", call_id="active-call", language_code="en-IN")

    assert cfg["provider"] == "sarvam"
    assert cfg["model"] == "bulbul:v3"
    assert cfg["speaker"] == "shubh"


def test_explicit_prewarm_stack_ignores_stale_runtime_provider(monkeypatch):
    monkeypatch.setenv("ENABLE_CARTESIA", "true")
    monkeypatch.setenv("CARTESIA_API_KEY", "sk-cartesia-test")
    get_settings.cache_clear()
    runtime_settings.update(
        "cfg-test",
        {
            "ttsModel": "sonic-3.5",
            "ttsSpeaker": "4418bb06-8329-49a1-bb11-53bb64ca0547",
        },
    )
    locked = SimpleNamespace(
        tts=SimpleNamespace(
            provider="sarvam",
            model="bulbul:v3",
            config={"speaker": "shubh"},
        )
    )

    cfg = resolve_tts_config(
        "cfg-test",
        resolved_stack=locked,
        language_code="en-IN",
    )

    assert cfg["provider"] == "sarvam"
    assert cfg["model"] == "bulbul:v3"
    assert cfg["speaker"] == "shubh"


def test_cartesia_wrong_provider_speaker_is_rejected(monkeypatch):
    monkeypatch.setenv("ENABLE_CARTESIA", "true")
    monkeypatch.setenv("CARTESIA_API_KEY", "sk-cartesia-test")
    get_settings.cache_clear()
    init_provider_registry()
    with pytest.raises(TtsConfigError, match="Choose a voice"):
        resolve_tts_config("cfg-test", language_code="te-IN", speaker="priya", model="sonic-3.5")


def test_sarvam_tts_maps_en_us_to_provider_en_in():
    cfg = resolve_tts_config("cfg-test", language_code="en-US")
    assert cfg["provider"] == "sarvam"
    assert cfg["language_code"] == "en-IN"


def test_stateless_config_never_resolves_the_live_session_stack(monkeypatch):
    import server.services.tts_config as tts_config

    def fail_stack(*_args, **_kwargs):
        raise AssertionError("stateless synthesis must not resolve the live session stack")

    monkeypatch.setattr(tts_config, "_stack_for_session", fail_stack)
    cfg = resolve_tts_config(
        None,
        language_code="te-IN",
        speaker="pooja_te_conversation",
        model="bulbul:v4-flash",
        pace=1.0,
    )
    assert cfg["provider"] == "sarvam"
    assert cfg["model"] == "bulbul:v4-flash"
    assert cfg["speaker"] == "pooja_te_conversation"


def _saved_sarvam_stack():
    return SimpleNamespace(tts=SimpleNamespace(provider="sarvam", model="bulbul:v4-flash", config={
        "speaker": "pooja_te_conversation", "pace": 1.25, "temperature": 0.45,
        "pitch": -0.2, "volume": 1.15,
    }))


def test_session_uses_saved_stack_delivery_controls_before_env(monkeypatch):
    import server.services.tts_config as service

    monkeypatch.setattr(service, "_stack_for_session", lambda *_: _saved_sarvam_stack())
    cfg = resolve_tts_config("cfg-test")
    assert (cfg["pace"], cfg["temperature"]) == (1.25, 0.45)
    # v4-flash rejects pitch/loudness even when an older saved stack carries them.
    assert "pitch" not in cfg and "loudness" not in cfg
    assert resolve_tts_config("cfg-test", pace=0.9)["pace"] == 0.9


def test_active_sarvam_call_keeps_saved_controls_despite_runtime_and_request_changes(monkeypatch):
    monkeypatch.setattr(runtime_settings, "get", lambda *_: {"ttsPace": 1.8, "ttsTemperature": 0.9, "ttsPitch": 0.4, "ttsVolume": 2.0})
    cfg = resolve_tts_config("cfg-test", resolved_stack=_saved_sarvam_stack(),
        pace=0.7, temperature=0.2, pitch=0.3, volume=2.2, sample_rate=16000, codec="linear16")
    assert (cfg["pace"], cfg["temperature"]) == (1.25, 0.45)
    assert "pitch" not in cfg and "loudness" not in cfg
    assert cfg["sample_rate"] == 16000 and cfg["output_audio_codec"] == "linear16"


def test_active_cartesia_call_keeps_saved_emotion_speed_volume_and_carrier_rate(monkeypatch):
    import server.services.tts_config as service
    import server.providers.voice_inventory as inventory

    voice_id = "47c38ca4-5f35-497b-b1a3-415245fb35e1"
    monkeypatch.setattr(service, "_cartesia_available", lambda: True)
    monkeypatch.setattr(inventory, "validate_voice", lambda *_: {"providerVoiceId": voice_id})
    stack = SimpleNamespace(tts=SimpleNamespace(provider="cartesia", model="sonic-3.5", config={
        "speaker": voice_id, "speed": 1.15, "emotion": "happy", "volume": 1.25,
    }))
    monkeypatch.setattr(runtime_settings, "get", lambda *_: {"ttsSpeed": 0.8, "ttsEmotion": "sad", "ttsVolume": 0.7})
    cfg = resolve_tts_config("cfg-test", resolved_stack=stack, pace=0.6, emotion="angry", volume=1.7, sample_rate=16000)
    assert cfg["generation_config"] == {"speed": 1.15, "emotion": "happy", "volume": 1.25}
    assert cfg["sample_rate"] == 16000
