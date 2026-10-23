"""Speech failures must not change a selected model or voice."""
import copy
import json

import httpx
import pytest

from server.providers import gemini_tts, sarvam_tts
from server.providers.base import TTSConfig


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("failure", ["quota", "unavailable", "timeout", "empty"])
async def test_gemini_tts_failure_never_uses_another_model(monkeypatch, streaming, failure):
    requests = []

    def respond(request):
        requests.append(request)
        assert "/models/gemini-3.8-flash-lite-tts:" in request.url.path
        if failure == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout")
        if failure in {"quota", "unavailable"}:
            return httpx.Response(429 if failure == "quota" else 503, text="private provider detail")
        packet = {"candidates": [{"content": {"role": "model", "parts": []}, "finishReason": "STOP"}]}
        return httpx.Response(200, text="data: " + json.dumps(packet) + "\n\n") if streaming else httpx.Response(200, json=packet)

    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs))
    adapter = gemini_tts.GeminiTTSAdapter(api_key="offline-key")
    config = TTSConfig(provider="gemini", model="gemini-3.8-flash-lite-tts", speaker="Zephyr")
    before = copy.deepcopy(config)
    with pytest.raises((RuntimeError, TimeoutError)) as exc:
        if streaming:
            _ = [chunk async for chunk in adapter.stream_with_metadata("Hello", config)]
        else:
            await adapter.synthesize_with_metadata("Hello", config)
    assert "private provider detail" not in str(exc.value)
    assert config == before and len(requests) == 1


@pytest.mark.parametrize("model,speaker,language", [
    ("missing-model", "shubh", "te-IN"),
    ("bulbul:v3", "missing-voice", "te-IN"),
    ("bulbul:v4-flash", "shubh", "te-IN"),
    ("bulbul:v4-flash", "kavitha_te_conversation", "ml-IN"),
])
def test_invalid_sarvam_selection_is_rejected_without_replacing_it(model, speaker, language):
    config = TTSConfig(provider="sarvam", model=model, speaker=speaker, language=language)
    before = copy.deepcopy(config)
    with pytest.raises(ValueError):
        sarvam_tts.SarvamTTSAdapter().connect_stream(config)
    assert config == before


def test_valid_v4_persona_keeps_the_selected_model(monkeypatch):
    connected = []
    monkeypatch.setattr(sarvam_tts, "connect_tts_ws", lambda **kwargs: connected.append(kwargs))
    config = TTSConfig(provider="sarvam", model="bulbul:v4-flash", speaker="kavitha_te_conversation", language="te-IN")
    sarvam_tts.SarvamTTSAdapter().connect_stream(config)
    assert connected == [{"model": "bulbul:v4-flash"}]
    assert config.speaker == "kavitha_te_conversation"


@pytest.mark.parametrize("model", ["gemini-3.8-live", "gemini-3.8-flash", "gemini-2.0-flash"])
def test_text_and_live_models_are_never_advertised_as_streaming_tts(model):
    assert gemini_tts.supports_gemini_tts_streaming(model) is False
    with pytest.raises(NotImplementedError):
        gemini_tts.GeminiTTSAdapter().connect_stream(TTSConfig(provider="gemini", model=model, speaker="Zephyr"))
