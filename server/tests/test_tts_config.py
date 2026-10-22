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
    cfg = resolve_tts_config("cfg-test", language_code="te-IN")
    assert cfg["provider"] == "sarvam"
    assert cfg["model"] == "bulbul:v3"
    assert cfg["speaker"] == "shubh"


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


def test_cartesia_sarvam_speaker_coerced_to_default(monkeypatch):
    from server.config.constants import constants

    monkeypatch.setenv("ENABLE_CARTESIA", "true")
    monkeypatch.setenv("CARTESIA_API_KEY", "sk-cartesia-test")
    get_settings.cache_clear()
    init_provider_registry()
    cfg = resolve_tts_config(
        "cfg-test",
        language_code="te-IN",
        speaker="priya",
        model="sonic-3.5",
    )
    assert cfg["provider"] == "cartesia"
    assert cfg["speaker"] == constants.CARTESIA_DEFAULT_VOICE_ID


def test_cartesia_default_voice_survives_english_cap():
    from server.config.constants import constants
    from server.services.cartesia_voices import _FALLBACK_VOICES, _build_studio_catalog

    extras = [
        {
            "id": f"00000000-0000-4000-8000-{i:012d}",
            "name": f"Aaa{i}",
            "gender": "feminine",
            "languages": ["en"],
            "region": "english",
        }
        for i in range(40)
    ]
    _studio, groups = _build_studio_catalog(list(_FALLBACK_VOICES) + extras)
    ids = {v["id"] for v in groups["english"]}
    assert constants.CARTESIA_DEFAULT_VOICE_ID in ids
    assert len(groups["english"]) <= 24
    runtime_settings.update("cfg-test", {"ttsSpeaker": "priya"})
    cfg = merge_ws_tts_config(
        "cfg-test",
        {"speaker": "shubh", "language_code": "te-IN"},
        language_code="te-IN",
        ws_model="bulbul:v3",
    )
    assert cfg["speaker"] == "priya"


def test_sarvam_tts_maps_en_us_to_provider_en_in():
    cfg = resolve_tts_config("cfg-test", language_code="en-US")
    assert cfg["provider"] == "sarvam"
    assert cfg["language_code"] == "en-IN"
