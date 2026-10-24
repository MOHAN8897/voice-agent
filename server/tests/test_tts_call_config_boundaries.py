"""Pinned call speech settings survive REST and telephony adapter boundaries."""
from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.providers.base import TTSConfig
from server.services import registry_tts_service, sarvam_tts_service, tts_config
from server.utils.pcm_wav import pcm16_to_wav


SAVED_VOICE = "4418bb06-8329-49a1-bb11-53bb64ca0547"
OTHER_VOICE = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"


def test_locked_cartesia_l16_ignores_client_voice_model_and_delivery_but_keeps_carrier_format(monkeypatch):
    from server.providers import voice_inventory

    stack = SimpleNamespace(tts=SimpleNamespace(provider="cartesia", model="sonic-3.5", config={
        "speaker": SAVED_VOICE, "speed": 0.85, "volume": 1.4, "emotion": "calm",
    }))
    monkeypatch.setattr(tts_config, "_cartesia_available", lambda: True)
    monkeypatch.setattr(voice_inventory, "validate_voice", lambda provider, model, speaker, language: {"providerVoiceId": speaker})
    cfg = tts_config.merge_pstn_tts_config(
        "live", {"speaker": OTHER_VOICE, "pace": 1.45, "sample_rate": 48000, "output_audio_codec": "mp3"},
        call_id="call-1", resolved_stack=stack, ws_model="sonic-3", wire_mode="rtp_l16", language_code="en-IN",
    )
    assert cfg["speaker"] == SAVED_VOICE
    assert cfg["model"] == "sonic-3.5"
    assert cfg["speed"] == 0.85
    assert cfg["volume"] == 1.4
    assert cfg["emotion"] == "calm"
    assert cfg["output_audio_codec"] == "linear16"
    assert cfg["speech_sample_rate"] == "16000"
    assert cfg["sample_rate"] == 16000


@pytest.mark.asyncio
async def test_sarvam_rest_adapter_does_not_resolve_mutable_default_session(monkeypatch):
    from server.providers import sarvam_tts

    wav = pcm16_to_wav(b"\x00\x00" * 160, sample_rate=16000)
    synthesize = AsyncMock(return_value={"audio_bytes": wav, "content_type": "audio/wav"})
    monkeypatch.setattr(sarvam_tts.sarvam_tts_service, "synthesize", synthesize)
    config = TTSConfig(provider="sarvam", model="bulbul:v2", language="te-IN",
                       speaker="anushka", pace=0.9, pitch=-0.2, volume=1.3)
    assert await sarvam_tts.SarvamTTSAdapter().synthesize_rest("Hello", config) == wav
    assert synthesize.await_args.kwargs["session_id"] is None
    assert synthesize.await_args.kwargs["speaker"] == "anushka"
    assert synthesize.await_args.kwargs["pitch"] == -0.2
    assert synthesize.await_args.kwargs["volume"] == 1.3


@pytest.mark.asyncio
@pytest.mark.parametrize("registry_enabled", [True, False])
async def test_locked_registry_sarvam_rest_uses_snapshot_through_actual_service(monkeypatch, registry_enabled):
    stack = SimpleNamespace(tts=SimpleNamespace(provider="sarvam", model="bulbul:v4-flash", config={
        "speaker": "pooja_te_conversation", "pace": 0.9, "temperature": 0.6, "pitch": -0.2, "loudness": 1.3,
    }))
    monkeypatch.setattr(registry_tts_service, "_stack_for_tts", lambda **kwargs: stack)
    monkeypatch.setattr(registry_tts_service, "get_settings", lambda: SimpleNamespace(use_provider_registry=registry_enabled))
    monkeypatch.setattr(registry_tts_service, "get_provider_registry", lambda: SimpleNamespace())

    def fail_mutable_stack(*args, **kwargs):
        raise AssertionError("The admitted stack must not be resolved again from mutable session settings")

    monkeypatch.setattr(tts_config, "_stack_for_session", fail_mutable_stack)
    wav = pcm16_to_wav(b"\x00\x00" * 160, sample_rate=16000)
    post = AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {
        "audios": [base64.b64encode(wav).decode()], "request_id": "test",
    }))
    monkeypatch.setattr(sarvam_tts_service, "get_sarvam_client", lambda: SimpleNamespace(post=post))
    result = await registry_tts_service.synthesize_via_registry(
        text="Hello", language_code="te-IN", session_id="live", call_id="call-1",
        model="bulbul:v3", speaker="ritu", pace=1.8, temperature=0.1, pitch=0.5, volume=1.8,
    )
    assert result["provider"] == "sarvam"
    payload = post.await_args.kwargs["json"]
    assert payload["model"] == "bulbul:v4-flash"
    assert payload["speaker"] == "pooja_te_conversation"
    assert payload["pace"] == 0.9
    assert payload["temperature"] == 0.6
    # v4-flash rejects pitch/loudness; saved values must not leak to the provider.
    assert "pitch" not in payload and "loudness" not in payload


@pytest.mark.asyncio
async def test_locked_registry_cartesia_rest_uses_snapshot_through_provider_payload(monkeypatch):
    from server.call.audio_archive import audio_archive
    from server.providers import cartesia_tts, voice_inventory

    stack = SimpleNamespace(tts=SimpleNamespace(provider="cartesia", model="sonic-3.5", config={
        "speaker": SAVED_VOICE, "speed": 0.85, "volume": 1.4, "emotion": "calm",
    }))
    adapter = cartesia_tts.CartesiaTTSAdapter()
    monkeypatch.setattr(registry_tts_service, "_stack_for_tts", lambda **kwargs: stack)
    monkeypatch.setattr(registry_tts_service, "get_settings", lambda: SimpleNamespace(use_provider_registry=True))
    monkeypatch.setattr(registry_tts_service, "get_provider_registry", lambda: SimpleNamespace(
        is_provider_enabled=lambda *args: True, get_tts=lambda provider: adapter,
    ))
    monkeypatch.setattr(tts_config, "_cartesia_available", lambda: True)
    monkeypatch.setattr(tts_config.runtime_settings, "get", lambda session: {
        "ttsSpeaker": OTHER_VOICE, "ttsModel": "sonic-3", "ttsSpeed": 1.5, "ttsVolume": 0.6, "ttsEmotion": "angry",
    })
    monkeypatch.setattr(voice_inventory, "default_voice", lambda provider, model, language, preferred=None: preferred)
    monkeypatch.setattr(voice_inventory, "validate_voice", lambda provider, model, speaker, language: {"providerVoiceId": speaker})
    monkeypatch.setattr(adapter, "_api_key", lambda: "unit-test")
    monkeypatch.setattr(audio_archive, "set_agent_sample_rate", lambda *args: None)
    post = AsyncMock(return_value=SimpleNamespace(content=b"\x00\x00" * 160, raise_for_status=lambda: None))

    class HttpContext:
        async def __aenter__(self):
            return SimpleNamespace(post=post)

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(cartesia_tts.httpx, "AsyncClient", lambda **kwargs: HttpContext())
    result = await registry_tts_service.synthesize_via_registry(
        text="Hello", language_code="en-IN", session_id="live", call_id="call-1",
        model="sonic-3", speaker=OTHER_VOICE, pace=1.4, volume=0.7,
    )
    assert result["speaker"] == SAVED_VOICE
    assert result["provider"] == "cartesia"
    payload = post.await_args.kwargs["json"]
    assert payload["voice"]["id"] == SAVED_VOICE
    assert payload["model_id"] == "sonic-3.5"
    assert payload["generation_config"] == {"emotion": "calm", "speed": 0.85, "volume": 1.4}
    assert payload["output_format"]["sample_rate"] == 16000


@pytest.mark.asyncio
@pytest.mark.parametrize("registry_enabled", [True, False])
async def test_disabled_selected_provider_never_routes_call_to_another_provider(monkeypatch, registry_enabled):
    from server.utils.errors import AppError

    stack = SimpleNamespace(tts=SimpleNamespace(provider="cartesia", model="sonic-3.5", config={"speaker": SAVED_VOICE}))
    monkeypatch.setattr(registry_tts_service, "_stack_for_tts", lambda **kwargs: stack)
    monkeypatch.setattr(registry_tts_service, "get_settings", lambda: SimpleNamespace(use_provider_registry=registry_enabled))
    monkeypatch.setattr(registry_tts_service, "get_provider_registry", lambda: SimpleNamespace(is_provider_enabled=lambda *args: False))
    sarvam = AsyncMock()
    monkeypatch.setattr(registry_tts_service, "sarvam_synthesize", sarvam)
    with pytest.raises(AppError) as error:
        await registry_tts_service.synthesize_via_registry(text="Hello", session_id="live", call_id="call-1")
    assert error.value.status_code == 503
    assert str(error.value) == "The selected speech service is unavailable."
    sarvam.assert_not_awaited()


@pytest.mark.asyncio
async def test_unlocked_registry_disabled_preview_preserves_legacy_session_behavior(monkeypatch):
    stack = SimpleNamespace(tts=SimpleNamespace(provider="sarvam", model="bulbul:v3", config={}))
    monkeypatch.setattr(registry_tts_service, "_stack_for_tts", lambda **kwargs: stack)
    monkeypatch.setattr(registry_tts_service, "get_settings", lambda: SimpleNamespace(use_provider_registry=False))
    sarvam = AsyncMock(return_value={"audio_bytes": b"test", "content_type": "audio/wav"})
    monkeypatch.setattr(registry_tts_service, "sarvam_synthesize", sarvam)
    await registry_tts_service.synthesize_via_registry(text="Hello", session_id="preview", pace=1.2, speaker="ritu", model="bulbul:v3")
    assert sarvam.await_args.kwargs["session_id"] == "preview"
    assert sarvam.await_args.kwargs["pace"] == 1.2
    assert sarvam.await_args.kwargs["speaker"] == "ritu"
