"""Regression: every saved universal TTS knob reaches each provider natively."""
from __future__ import annotations

import base64
import copy
import io
import json
import wave
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.services.tts_voice_direction import (
    normalize_tts_dynamics,
    provider_tts_payload,
    tts_knob_specs,
)


def _spec_map(provider: str, model: str) -> dict[str, dict]:
    return {spec["key"]: spec for spec in tts_knob_specs(provider, model)}


@pytest.mark.parametrize(
    "provider, model, expected",
    [
        ("sarvam", "bulbul:v3", ["speed", "temperature"]),
        ("sarvam", "bulbul:v4-flash", ["speed", "temperature"]),
        ("sarvam", "bulbul:v2", ["speed", "pitch", "volume"]),
        ("gnani", "timbre-v3.0", ["speed"]),
        ("cartesia", "sonic-3.5", ["speed", "emotion", "volume"]),
        ("gemini", "gemini-3.8-flash-tts", ["speed", "pitch"]),
    ],
)
def test_knob_specs_match_provider_capabilities(provider, model, expected):
    assert [spec["key"] for spec in tts_knob_specs(provider, model)] == expected


def test_knob_bounds_and_native_names_follow_the_engine():
    sarvam_v3 = _spec_map("sarvam", "bulbul:v3")
    assert sarvam_v3["speed"]["min"] == 0.5 and sarvam_v3["speed"]["max"] == 2.0
    assert sarvam_v3["speed"]["native"] == "pace"
    assert sarvam_v3["temperature"]["min"] == 0.01
    assert sarvam_v3["temperature"]["max"] == 1.0

    sarvam_v2 = _spec_map("sarvam", "bulbul:v2")
    assert sarvam_v2["speed"]["min"] == 0.3 and sarvam_v2["speed"]["max"] == 3.0
    assert sarvam_v2["volume"]["native"] == "loudness"

    gnani = _spec_map("gnani", "timbre-v3.0")
    assert gnani["speed"]["min"] == 0.85 and gnani["speed"]["max"] == 1.15
    assert "pitch" not in gnani and "volume" not in gnani

    cartesia = _spec_map("cartesia", "sonic-3.5")
    assert cartesia["speed"]["min"] == 0.6 and cartesia["speed"]["max"] == 1.5
    assert cartesia["emotion"]["kind"] == "select"
    assert {option["value"] for option in cartesia["emotion"]["options"]} >= {
        "calm",
        "happy",
        "confident",
    }

    gemini = _spec_map("gemini", "gemini-3.8-flash-tts")
    assert gemini["speed"]["min"] == 0.25 and gemini["speed"]["max"] == 2.0
    assert gemini["pitch"]["native"] == "pitch"


def test_normalize_drops_unsupported_knobs_and_clamps_to_the_model_band():
    assert normalize_tts_dynamics(
        "sarvam",
        "bulbul:v3",
        {"speed": 9, "temperature": 2, "pitch": 0.4, "volume": 1.5, "emotion": "happy"},
    ) == {"speed": 2.0, "temperature": 1.0}

    # The provider rejects pitch/loudness for v4-flash even though the endpoint
    # tolerates the fields; only pace and temperature reach the engine.
    assert normalize_tts_dynamics(
        "sarvam",
        "bulbul:v4-flash",
        {"speed": 0.1, "temperature": 0.7, "pitch": 2, "volume": 0.1},
    ) == {"speed": 0.5, "temperature": 0.7}

    assert normalize_tts_dynamics("gnani", "timbre-v3.0", {"speed": 1.4}) == {"speed": 1.15}


def test_normalize_rejects_unknown_emotions_and_non_numeric_values():
    assert normalize_tts_dynamics(
        "cartesia",
        "sonic-3.5",
        {"speed": "fast", "emotion": "not-a-provider-emotion", "volume": True, "pitch": 0.2},
    ) == {}
    assert normalize_tts_dynamics(
        "cartesia", "sonic-3.5", {"emotion": "Happy", "volume": 1.1}
    ) == {"emotion": "happy", "volume": 1.1}


def test_sarvam_payload_translates_loudness_and_filters_by_model():
    assert provider_tts_payload(
        "sarvam",
        "bulbul:v4-flash",
        {"speed": 1.2, "temperature": 0.7, "pitch": 0.2, "volume": 1.1},
    ) == {"pace": 1.2, "temperature": 0.7}

    assert provider_tts_payload(
        "sarvam",
        "bulbul:v3",
        {"speed": 1.2, "temperature": 0.7, "pitch": 0.2, "volume": 1.1},
    ) == {"pace": 1.2, "temperature": 0.7}

    assert provider_tts_payload(
        "sarvam",
        "bulbul:v2",
        {"speed": 1.2, "temperature": 0.7, "pitch": 0.2, "volume": 1.1},
    ) == {"pace": 1.2, "pitch": 0.2, "loudness": 1.1}


def test_gnani_payload_drops_undocumented_delivery_fields():
    payload = provider_tts_payload(
        "gnani", "timbre-v3.0", {"speed": 1.1, "pitch": 0.375, "volume": 1.25}
    )
    assert payload == {"pace": 1.1}
    assert provider_tts_payload("gnani", "timbre-v3.0", {"pitch": 0.75, "volume": 1.5}) == {}


def test_cartesia_payload_carries_speed_emotion_and_volume():
    assert provider_tts_payload(
        "cartesia", "sonic-3.5", {"speed": 1.2, "emotion": "happy", "volume": 1.1}
    ) == {"pace": 1.2, "speed": 1.2, "emotion": "happy", "volume": 1.1}


def test_gemini_payload_uses_delivery_directions_only():
    assert provider_tts_payload(
        "gemini",
        "gemini-3.8-flash-tts",
        {"speed": 1.1, "pitch": -0.2, "temperature": 0.8, "emotion": "happy", "volume": 1.2},
    ) == {"pace": 1.1, "pitch": -0.2}


class _Socket:
    def __init__(self):
        self.sent = []

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    def __aiter__(self):
        async def messages():
            yield json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}})

        return messages()


def _voice():
    return SimpleNamespace(
        call_id=None,
        current_turn_id="turn",
        current_generation_id="generation",
        _wire_frames_out=0,
        _closed=False,
        sample_rate=16000,
        tts_output_codec="linear16",
        _interrupted_generation=None,
        emission_blocked=lambda: False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider, model, saved, expected_wire, expected_config",
    [
        (
            "sarvam",
            "bulbul:v4-flash",
            {
                "speaker": "pooja_te_conversation",
                "speed": 1.2,
                "pace": 1.2,
                "temperature": 0.7,
                "pitch": 0.2,
                "volume": 1.1,
            },
            {"pace": 1.2, "temperature": 0.7},
            {
                "pace": 1.2,
                "speed": None,
                "temperature": 0.7,
                "pitch": None,
                "volume": None,
                "emotion": None,
            },
        ),
        (
            "sarvam",
            "bulbul:v3",
            {
                "speaker": "shubh",
                "speed": 1.1,
                "pace": 1.1,
                "temperature": 0.6,
                "pitch": 0.4,
                "volume": 1.3,
                "emotion": "happy",
            },
            {"pace": 1.1, "temperature": 0.6},
            {
                "pace": 1.1,
                "speed": None,
                "temperature": 0.6,
                "pitch": None,
                "volume": None,
                "emotion": None,
            },
        ),
        (
            "gnani",
            "timbre-v3.0",
            {"speaker": "Shivani", "speed": 1.1, "pace": 1.1, "pitch": 0.375, "volume": 1.25},
            {"pace": 1.1},
            {"pace": 1.1, "temperature": None, "pitch": None, "volume": None, "emotion": None},
        ),
        (
            "cartesia",
            "sonic-3.5",
            {
                "speaker": "47c38ca4-5f35-497b-b1a3-415245fb35e1",
                "speed": 1.2,
                "pace": 1.2,
                "emotion": "happy",
                "volume": 1.1,
                "pitch": 0.3,
                "temperature": 0.5,
            },
            {"pace": 1.2, "speed": 1.2, "emotion": "happy", "volume": 1.1},
            {"pace": 1.2, "temperature": None, "pitch": None, "volume": 1.1, "emotion": "happy"},
        ),
        (
            "gemini",
            "gemini-3.8-flash-tts",
            {
                "speaker": "Kore",
                "speed": 1.1,
                "pace": 1.1,
                "pitch": -0.2,
                "temperature": 0.8,
                "emotion": "happy",
                "volume": 1.2,
            },
            {"pace": 1.1, "pitch": -0.2},
            {"pace": 1.1, "temperature": None, "pitch": -0.2, "volume": None, "emotion": None},
        ),
    ],
)
async def test_composed_tts_forwards_every_supported_knob(
    monkeypatch, provider, model, saved, expected_wire, expected_config
):
    import server.providers

    socket = _Socket()
    captured = []

    @asynccontextmanager
    async def connect_stream(config):
        captured.append(config)
        yield socket

    adapter = SimpleNamespace(provider_id=provider, connect_stream=connect_stream)
    registry = SimpleNamespace(
        is_provider_enabled=lambda *_: True,
        is_model_allowed=lambda *_: True,
        get_tts=lambda _: adapter,
    )
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: registry)

    from server.services.pstn_turn_tts import PstnTurnTtsSession

    session = PstnTurnTtsSession(_voice())
    stack = SimpleNamespace(
        language="te-IN",
        tts=SimpleNamespace(
            provider=provider,
            model=model,
            config={"api_mode": "websocket", **saved},
        ),
    )
    try:
        await session._open_composed(resolved_stack=stack, language_code="te-IN")
        sent = socket.sent[0]["data"]
        for key, value in expected_wire.items():
            assert sent[key] == pytest.approx(value)
        if provider == "sarvam" and model in {"bulbul:v3", "bulbul:v4-flash"}:
            assert "pitch" not in sent and "loudness" not in sent
        for attr, value in expected_config.items():
            actual = getattr(captured[0], attr)
            if value is None:
                assert actual is None
            else:
                assert actual == pytest.approx(value)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_composed_sarvam_uses_default_pace_when_agent_saved_none(monkeypatch):
    import server.providers
    from server.config.env import get_settings

    monkeypatch.setattr(get_settings(), "sarvam_tts_pace", 1.08)
    socket = _Socket()

    @asynccontextmanager
    async def connect_stream(_config):
        yield socket

    adapter = SimpleNamespace(provider_id="sarvam", connect_stream=connect_stream)
    monkeypatch.setattr(
        server.providers,
        "get_provider_registry",
        lambda: SimpleNamespace(
            is_provider_enabled=lambda *_: True,
            is_model_allowed=lambda *_: True,
            get_tts=lambda _: adapter,
        ),
    )

    from server.services.pstn_turn_tts import PstnTurnTtsSession

    session = PstnTurnTtsSession(_voice())
    try:
        await session._open_composed(
            resolved_stack=SimpleNamespace(
                language="te-IN",
                tts=SimpleNamespace(
                    provider="sarvam",
                    model="bulbul:v3",
                    config={"speaker": "shubh", "api_mode": "websocket"},
                ),
            ),
            language_code="te-IN",
        )
        assert socket.sent[0]["data"]["pace"] == 1.08
        assert "temperature" not in socket.sent[0]["data"]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_gnani_ws_sends_only_documented_delivery_fields(monkeypatch):
    import server.services.gnani_tts_ws as gnani_ws

    sent = []

    class _Ws:
        async def send(self, payload):
            sent.append(json.loads(payload))

        async def recv(self):
            raise RuntimeError("closed")

        async def close(self):
            return None

    async def fake_connect(*_args, **_kwargs):
        return _Ws()

    monkeypatch.setattr(gnani_ws.websockets, "connect", fake_connect)
    monkeypatch.setattr(gnani_ws, "_gnani_api_key", lambda: "unit-key")

    async with gnani_ws.connect_gnani_tts_ws(model="timbre-v3.0") as socket:
        await socket.send(
            json.dumps(
                {
                    "type": "config",
                    "data": {
                        "speaker": "Shivani",
                        "language_code": "te-IN",
                        "pace": 1.1,
                        "pitch": 1.25,
                        "volume": 1.25,
                    },
                }
            )
        )
        await socket.send(json.dumps({"type": "text", "data": {"text": "నమస్కారం"}}))
        await socket.close()

    request = next(message for message in sent if message.get("text"))
    assert request["speed"] == pytest.approx(1.1)
    assert "pitch" not in request and "volume" not in request


def _wav_bytes(frames: bytes = b"\x01\x00" * 240, rate: int = 16000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        wav.writeframes(frames)
    return output.getvalue()


@pytest.mark.asyncio
async def test_gnani_rest_preview_omits_undocumented_fields_like_live(monkeypatch):
    import httpx

    from server.providers.gnani_tts import GnaniTTSAdapter
    from server.providers.base import TTSConfig

    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, content=_wav_bytes())

    client_cls = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client_cls(transport=httpx.MockTransport(handle), **kwargs)
    )
    monkeypatch.setattr(GnaniTTSAdapter, "_api_key", lambda self: "unit-key")

    adapter = GnaniTTSAdapter()
    config = TTSConfig(
        provider="gnani",
        model="timbre-v3.0",
        speaker="Shivani",
        language="te-IN",
        pace=1.1,
        pitch=0.375,
        volume=1.25,
    )
    await adapter.synthesize_rest("నమస్కారం", config)

    payload = requests[0]
    assert payload["speed"] == pytest.approx(1.1)
    assert "pitch" not in payload and "volume" not in payload

    await adapter.synthesize_rest(
        "నమస్కారం",
        TTSConfig(provider="gnani", model="timbre-v3.0", speaker="Shivani",
                  language="te-IN", pace=1.0, pitch=0.75),
    )
    assert "pitch" not in requests[1]


@pytest.mark.asyncio
async def test_sarvam_rest_sends_only_supported_knobs_per_model(monkeypatch):
    import server.services.sarvam_tts_service as sarvam_service

    requests = []

    class _Response:
        status_code = 200

        def json(self):
            return {"audios": [base64.b64encode(_wav_bytes(rate=24000)).decode()], "request_id": "req"}

    class _Client:
        async def post(self, url, headers=None, json=None, timeout=None):
            requests.append(json)
            return _Response()

    monkeypatch.setattr(sarvam_service, "get_sarvam_client", lambda: _Client())

    await sarvam_service.synthesize(
        "నమస్కారం",
        language_code="te-IN",
        speaker="pooja_te_conversation",
        model="bulbul:v4-flash",
        pace=1.2,
        temperature=0.7,
        pitch=0.2,
        volume=1.1,
        session_id=None,
    )
    payload = requests[0]
    assert payload["pace"] == pytest.approx(1.2)
    assert "pitch" not in payload and "loudness" not in payload
    assert payload["temperature"] == pytest.approx(0.7)

    await sarvam_service.synthesize(
        "నమస్కారం",
        language_code="te-IN",
        speaker="shubh",
        model="bulbul:v3",
        pace=1.2,
        temperature=0.7,
        pitch=0.2,
        volume=1.1,
        session_id=None,
    )
    payload = requests[1]
    assert "pitch" not in payload and "loudness" not in payload
    assert payload["temperature"] == pytest.approx(0.7)

    await sarvam_service.synthesize(
        "నమస్కారం",
        language_code="te-IN",
        speaker="anushka",
        model="bulbul:v2",
        pace=1.2,
        temperature=0.7,
        pitch=0.2,
        volume=1.1,
        session_id=None,
    )
    payload = requests[2]
    assert "temperature" not in payload
    assert payload["pitch"] == pytest.approx(0.2)
    assert payload["loudness"] == pytest.approx(1.1)


@pytest.mark.asyncio
async def test_sarvam_rest_adapter_forwards_pitch_and_volume(monkeypatch):
    from server.providers import sarvam_tts
    from server.providers.base import TTSConfig

    calls = []

    async def fake_synthesize(text, **kwargs):
        calls.append(kwargs)
        return {"audio_bytes": _wav_bytes(rate=24000), "content_type": "audio/wav"}

    monkeypatch.setattr(sarvam_tts.sarvam_tts_service, "synthesize", fake_synthesize)

    await sarvam_tts.SarvamTTSAdapter().synthesize_rest(
        "నమస్కారం",
        TTSConfig(
            provider="sarvam",
            model="bulbul:v2",
            speaker="anushka",
            language="te-IN",
            pace=1.2,
            temperature=0.7,
            pitch=0.2,
            volume=1.1,
        ),
    )
    assert calls[0]["pitch"] == pytest.approx(0.2)
    assert calls[0]["volume"] == pytest.approx(1.1)


@pytest.mark.asyncio
async def test_registry_rest_applies_pitch_and_volume_for_non_sarvam_stacks(monkeypatch):
    import server.services.registry_tts_service as registry_service
    from server.config.env import get_settings

    captured = []

    class _Adapter:
        async def synthesize_rest(self, _text, config):
            captured.append(config)
            return _wav_bytes()

    adapter = _Adapter()
    monkeypatch.setattr(
        registry_service,
        "_stack_for_tts",
        lambda **_kwargs: SimpleNamespace(
            tts=SimpleNamespace(
                provider="gnani",
                model="timbre-v3.0",
                config={"speaker": "Shivani"},
            )
        ),
    )
    monkeypatch.setattr(
        registry_service,
        "get_provider_registry",
        lambda: SimpleNamespace(
            is_provider_enabled=lambda *_: True,
            get_tts=lambda _: adapter,
        ),
    )
    monkeypatch.setattr(get_settings(), "use_provider_registry", True)

    await registry_service.synthesize_via_registry(
        text="నమస్కారం",
        language_code="te-IN",
        session_id="registry-knob-test",
        pace=1.1,
        temperature=0.8,
        pitch=0.375,
        volume=1.25,
    )

    assert captured[0].pitch is None
    assert captured[0].volume is None
    assert captured[0].pace == pytest.approx(1.1)


def test_browser_ws_config_forwards_sarvam_family_knobs():
    from server.routes.ws import _upstream_tts_config_payload

    out = _upstream_tts_config_payload(
        {
            "provider": "sarvam",
            "speaker": "anushka",
            "language_code": "te-IN",
            "pace": 1.2,
            "pitch": 0.2,
            "loudness": 1.1,
            "min_buffer_size": 30,
            "max_chunk_length": 80,
            "output_audio_codec": "linear16",
            "output_audio_bitrate": "128k",
            "model": "bulbul:v2",
            "sample_rate": 24000,
        }
    )
    assert out["pace"] == pytest.approx(1.2)
    assert "temperature" not in out
    assert out["pitch"] == pytest.approx(0.2)
    assert out["loudness"] == pytest.approx(1.1)


def test_browser_ws_merge_filters_v4_to_pace_and_temperature():
    from server.services.tts_config import merge_ws_tts_config

    merged = merge_ws_tts_config(
        None,
        {
            "language_code": "te-IN",
            "speaker": "pooja_te_conversation",
            "pace": 1.2,
            "temperature": 0.7,
            "pitch": 0.2,
            "volume": 1.1,
        },
        language_code="te-IN",
        ws_model="bulbul:v4-flash",
    )
    assert merged["pace"] == pytest.approx(1.2)
    assert merged["temperature"] == pytest.approx(0.7)
    assert "pitch" not in merged and "loudness" not in merged


def test_browser_ws_config_forwards_cartesia_generation_knobs():
    from server.routes.ws import _upstream_tts_config_payload

    generation = {"emotion": "happy", "speed": 1.2, "volume": 1.1}
    out = _upstream_tts_config_payload(
        {
            "provider": "cartesia",
            "speaker": "47c38ca4-5f35-497b-b1a3-415245fb35e1",
            "language_code": "te-IN",
            "pace": 1.2,
            "speed": 1.2,
            "emotion": "happy",
            "volume": 1.1,
            "generation_config": generation,
            "min_buffer_size": 30,
            "max_chunk_length": 80,
            "output_audio_codec": "linear16",
            "output_audio_bitrate": "128k",
            "model": "sonic-3.5",
            "sample_rate": 24000,
        }
    )
    assert out["speed"] == pytest.approx(1.2)
    assert out["emotion"] == "happy"
    assert out["volume"] == pytest.approx(1.1)
    assert out["generation_config"] == generation


@pytest.mark.asyncio
async def test_preview_applies_the_same_gnani_knobs_as_live(monkeypatch):
    from server.services.saas import voice_preview

    captured = []

    async def fake_synthesize(line, voice, speed, language=None, model=None, pitch=None, volume=None):
        captured.append({"speed": speed, "pitch": pitch, "volume": volume})
        return _wav_bytes()

    monkeypatch.setattr(voice_preview, "_synthesize_gnani", fake_synthesize)

    await voice_preview.synthesize_preview(
        "పరీక్ష ప్రీవ్యూ వాక్యం.",
        voice_id="Shivani",
        language="te-IN",
        speed=1.1,
        pitch=0.375,
        temperature=0.8,
        emotion="happy",
        volume=1.25,
        provider="gnani",
        model="timbre-v3.0",
    )

    assert captured[0] == {"speed": pytest.approx(1.1), "pitch": None, "volume": None}


@pytest.mark.asyncio
async def test_agent_speed_override_pins_pace_and_speed_together(monkeypatch):
    from server.services.saas import pstn_saas_stack, voice_stack_profiles

    original = {
        "pipeline": "composed_voice",
        "voice_flow": "composed_stages",
        "language": "te-IN",
        "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {}},
        "llm": {"provider": "gemini", "model": "gemini-test", "config": {}},
        "tts": {
            "provider": "gnani",
            "model": "timbre-v3.0",
            "config": {"speaker": "Shivani", "speed": 1.15, "pace": 1.15},
        },
        "_voice_stack_snapshot": {"tier": "medium"},
    }
    monkeypatch.setattr(pstn_saas_stack, "load_agent_voice_config", AsyncMock(return_value={}))
    monkeypatch.setattr(
        voice_stack_profiles,
        "resolve_agent_selection",
        AsyncMock(return_value=(copy.deepcopy(original), {})),
    )

    stack = await pstn_saas_stack.saas_stack_override_for_agent(
        {
            "agent_id": "knob-test",
            "default_tier": "medium",
            "environment": "staging",
            "languages": ["te-IN"],
            "voice_settings": {"speed": 1.05},
        }
    )
    assert stack["tts"]["config"]["pace"] == pytest.approx(1.05)
    assert stack["tts"]["config"]["speed"] == pytest.approx(1.05)
