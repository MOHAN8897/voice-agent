"""Phone speech pace must reach synthesis without retiming carrier PCM."""
from __future__ import annotations

import base64
import copy
import io
import json
import wave
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from server.providers.base import TTSConfig
from server.services.pstn_turn_tts import PstnTurnTtsSession


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["low", "medium", "custom_voice"])
async def test_saved_agent_speed_reaches_composed_call_snapshot(monkeypatch, tier):
    from server.services.saas import pstn_saas_stack, voice_stack_profiles

    original = {
        "pipeline": "composed_voice", "voice_flow": "composed_stages", "language": "te-IN",
        "stt": {"provider": "sarvam", "model": "saaras:v3", "config": {}},
        "llm": {"provider": "gemini", "model": "gemini-test", "config": {}},
        "tts": {"provider": "sarvam", "model": "bulbul:v3", "config": {"speaker": "shubh"}},
        "_voice_stack_snapshot": {"tier": tier},
    }
    monkeypatch.setattr(pstn_saas_stack, "load_agent_voice_config", AsyncMock(return_value={}))
    monkeypatch.setattr(
        voice_stack_profiles, "resolve_agent_selection",
        AsyncMock(return_value=(copy.deepcopy(original), {})),
    )
    stack = await pstn_saas_stack.saas_stack_override_for_agent({
        "agent_id": "pace-test", "default_tier": tier, "environment": "staging",
        "languages": ["te-IN"], "voice_settings": {"speed": 1.2},
    })
    assert stack["tts"]["config"]["pace"] == 1.2
    assert original["tts"]["config"] == {"speaker": "shubh"}


class _Socket:
    def __init__(self):
        self.sent = []

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    def __aiter__(self):
        async def messages():
            yield json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}})
        return messages()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider, pace", [("sarvam", 1.18), ("cartesia", 1.2), ("gnani", 1.15)])
async def test_composed_websocket_forwards_pace_to_provider(monkeypatch, provider, pace):
    import server.providers

    socket = _Socket()
    captured = []

    @asynccontextmanager
    async def connect(config):
        captured.append(config)
        yield socket

    adapter = SimpleNamespace(provider_id=provider, connect_stream=connect)
    registry = SimpleNamespace(
        is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
        get_tts=lambda _: adapter,
    )
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: registry)
    voice = SimpleNamespace(
        call_id=None, current_turn_id="turn", current_generation_id="generation",
        _wire_frames_out=0,
        _closed=False, sample_rate=16000, tts_output_codec="linear16",
        _interrupted_generation=None, emission_blocked=lambda: False,
    )
    session = PstnTurnTtsSession(voice)
    stack = SimpleNamespace(language="te-IN", tts=SimpleNamespace(
        provider=provider, model="test-model",
        config={"speaker": "test-voice", "api_mode": "websocket", "pace": pace},
    ))
    try:
        await session._open_composed(resolved_stack=stack, language_code="te-IN")
        assert captured[0].pace == pace
        assert socket.sent[0]["data"]["pace"] == pace
        if provider == "cartesia":
            assert captured[0].speed == pace
            assert socket.sent[0]["data"]["speed"] == pace
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_composed_sarvam_keeps_configured_default_pace(monkeypatch):
    import server.providers
    from server.config.env import get_settings

    monkeypatch.setattr(get_settings(), "sarvam_tts_pace", 1.08)
    socket = _Socket()

    @asynccontextmanager
    async def connect(_config):
        yield socket

    adapter = SimpleNamespace(provider_id="sarvam", connect_stream=connect)
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: SimpleNamespace(
        is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
        get_tts=lambda _: adapter,
    ))
    voice = SimpleNamespace(call_id=None, current_turn_id="turn", current_generation_id="g",
                            _wire_frames_out=0, sample_rate=16000,
                            tts_output_codec="linear16", _closed=False)
    session = PstnTurnTtsSession(voice)
    try:
        await session._open_composed(resolved_stack=SimpleNamespace(
            language="te-IN", tts=SimpleNamespace(provider="sarvam", model="bulbul:v3",
                config={"speaker": "shubh", "api_mode": "websocket"}),
        ), language_code="te-IN")
        assert socket.sent[0]["data"]["pace"] == 1.08
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("pace", [0.8, 1.0, 1.2])
async def test_gemini_tts_pace_is_metadata_not_spoken_text(monkeypatch, streaming, pace):
    from server.providers import gemini_tts

    requests = []
    pcm = b"\x01\x00" * 240
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)

    def handle(request):
        requests.append(json.loads(request.content))
        payload = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/l16;rate=24000" if streaming else "audio/wav",
            "data": base64.b64encode(pcm if streaming else output.getvalue()).decode(),
        }}]}, "finishReason": "STOP"}]}
        if streaming:
            return httpx.Response(200, text=f"data: {json.dumps(payload)}\n\n")
        return httpx.Response(200, json=payload)

    client_cls = httpx.AsyncClient
    monkeypatch.setattr(gemini_tts.httpx, "AsyncClient", lambda **kwargs:
        client_cls(transport=httpx.MockTransport(handle), **kwargs))
    config = TTSConfig(provider="gemini", model="gemini-3.8-flash-tts", speaker="Kore",
                       language="te-IN", pace=pace)
    adapter = gemini_tts.GeminiTTSAdapter(api_key="unit-key")
    text = "సరే, మీకు ఎలా సహాయం చేయగలను?"
    if streaming:
        chunks = [chunk async for chunk in adapter.stream_with_metadata(text, config)]
        assert chunks[0].sample_rate == 24000
    else:
        result = await adapter.synthesize_with_metadata(text, config)
        with wave.open(io.BytesIO(result.audio_bytes), "rb") as wav:
            assert wav.getframerate() == 24000
    part = requests[0]["contents"][0]["parts"][0]
    assert part["text"] == text
    style = part["speech_metadata"]["style"]
    assert "conversational" in style.lower()
    if pace != 1.0:
        assert f"{pace:.2f}x" in style


@pytest.mark.asyncio
@pytest.mark.parametrize("wire_pace", [None, 1.3])
async def test_gemini_websocket_keeps_initial_or_explicit_pace(monkeypatch, wire_pace):
    from server.providers import gemini_tts
    from server.services import gemini_tts_ws

    captured = []

    class Adapter:
        def __init__(self, **_):
            pass

        async def stream_with_metadata(self, _text, config):
            captured.append(config)
            if False:
                yield None

    monkeypatch.setattr(gemini_tts, "GeminiTTSAdapter", Adapter)
    monkeypatch.setattr(gemini_tts_ws.dev_secrets_store, "effective_secret", lambda _: "unit-key")
    initial = TTSConfig(provider="gemini", model="gemini-3.8-flash-tts", pace=1.2)
    async with gemini_tts_ws.connect_gemini_tts_ws(model=initial.model, tts_config=initial) as socket:
        data = {"pace": wire_pace} if wire_pace is not None else {}
        await socket.send(json.dumps({"type": "config", "data": data}))
        await socket.send(json.dumps({"type": "text", "data": {"text": "Hello."}}))
        await socket.send(json.dumps({"type": "flush"}))
        await socket.close()
    assert captured[0].pace == (wire_pace if wire_pace is not None else 1.2)


@pytest.mark.asyncio
@pytest.mark.parametrize("speed", [0.25, 0.8, 1.2])
async def test_gemini_live_uses_saved_speed_and_keeps_it_on_instruction_refresh(monkeypatch, speed):
    from server.realtime.providers import gemini_voice

    captured = []
    session = SimpleNamespace(send_client_content=AsyncMock())

    @asynccontextmanager
    async def connect(**kwargs):
        captured.append(kwargs["config"])
        yield session

    client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
    monkeypatch.setattr(gemini_voice.genai, "Client", lambda **_: client)
    adapter = gemini_voice.GeminiLiveVoiceAdapter(api_key="unit-key")
    monkeypatch.setattr(adapter, "_pump", AsyncMock())
    try:
        await adapter.connect(model="gemini-3.8-live", instructions="Speak only Telugu.", speed=speed)
        instruction = captured[0].system_instruction.parts[0].text
        assert f"{speed:.2f}x" in instruction
        assert "conversational" in instruction.lower()
        assert "Speak only Telugu." in instruction
        await adapter.update_instructions("Updated business facts. Speak only Telugu.")
        assert f"{speed:.2f}x" in adapter.instructions
        assert adapter.instructions.count("SPEAKING PACE") == 1
        assert "speed" not in adapter.last_session["effective_vad"]["ignored_ui"]
    finally:
        await adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("speed", [0.8, 1.2])
async def test_gemini_side_greeting_keeps_selected_speed(monkeypatch, speed):
    from server.services import pstn_realtime_greeting_prewarm as prewarm

    adapter = SimpleNamespace(connect=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(prewarm, "synthesize_realtime_greeting_frames",
                        AsyncMock(return_value=([b"audio"], "Hello.", None)))
    frames, _, _ = await prewarm.synthesize_gemini_greeting_on_side_session(
        greeting_text="Hello.", sample_rate=16000, tts_output_codec="linear16",
        model="gemini-3.8-live", speed=speed, adapter_factory=lambda: adapter,
    )
    assert frames == [b"audio"]
    assert adapter.connect.await_args.kwargs["speed"] == speed
    adapter.close.assert_awaited_once()


@pytest.mark.parametrize("pace", [True, 0, -1, float("nan"), float("inf"), "invalid"])
def test_invalid_pace_fails_before_synthesis(pace):
    from server.services.tts_voice_direction import resolve_speech_pace

    with pytest.raises(ValueError, match="finite positive"):
        resolve_speech_pace("gemini", pace)
