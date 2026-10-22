from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from server.providers import gemini_tts
from server.providers.base import TTSConfig
from server.services.pstn_turn_tts import PstnTurnTtsSession


def _config(model: str = "gemini-3.8-flash-lite-tts") -> TTSConfig:
    return TTSConfig(provider="gemini", model=model, speaker="Kore", language="te-IN")


def _audio_event(audio: bytes, *, mime_type: str = "audio/l16;rate=24000") -> dict:
    return {"candidates": [{"content": {"parts": [{"inlineData": {
        "mimeType": mime_type, "data": base64.b64encode(audio).decode("ascii"),
    }}]}}]}


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


class _ResponseStream(httpx.AsyncByteStream):
    def __init__(self, first: bytes, rest: bytes = b"", *, gated: bool = False) -> None:
        self.first = first
        self.rest = rest
        self.release = asyncio.Event()
        self.waiting = asyncio.Event()
        self.closed = False
        if not gated:
            self.release.set()

    async def __aiter__(self):
        yield self.first
        self.waiting.set()
        await self.release.wait()
        if self.rest:
            yield self.rest

    async def aclose(self) -> None:
        self.closed = True


def _patch_http(monkeypatch, stream: _ResponseStream, *, status: int = 200) -> list:
    requests = []
    original = httpx.AsyncClient

    def handle(request):
        requests.append(request)
        return httpx.Response(status, headers={"content-type": "text/event-stream"}, stream=stream)

    monkeypatch.setattr(
        gemini_tts.httpx, "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setattr(gemini_tts, "get_settings", lambda: SimpleNamespace(request_timeout_ms=1000))
    return requests


@pytest.mark.asyncio
async def test_stream_yields_pcm_before_response_completes_and_counts_usage_once(monkeypatch):
    first = _audio_event(b"\x01\x02\x03")
    first["usageMetadata"] = {"promptTokenCount": 3, "candidatesTokenCount": 5}
    second = _audio_event(b"\x04\x05\x06")
    second["usageMetadata"] = {"promptTokenCount": 3, "candidatesTokenCount": 8}
    end = {"candidates": [{"finishReason": "STOP"}], "usageMetadata": second["usageMetadata"]}
    response = _ResponseStream(_sse(first), _sse(second) + _sse(end), gated=True)
    requests = _patch_http(monkeypatch, response)
    stream = gemini_tts.GeminiTTSAdapter(api_key="unit-key").stream_with_metadata("Hello", _config())

    initial = await asyncio.wait_for(anext(stream), timeout=1)
    assert initial.audio_bytes == b"\x01\x02"
    assert initial.sample_rate == 24000
    assert not response.release.is_set()
    assert not response.closed
    response.release.set()
    remaining = [chunk async for chunk in stream]

    assert b"".join(chunk.audio_bytes for chunk in [initial, *remaining]) == b"\x01\x02\x03\x04\x05\x06"
    assert sum(chunk.usage.get("input_tokens", 0) for chunk in [initial, *remaining]) == 3
    assert sum(chunk.usage.get("output_audio_tokens", 0) for chunk in [initial, *remaining]) == 8
    assert response.closed
    request = requests[0]
    assert request.url.path.endswith("/gemini-3.8-flash-lite-tts:streamGenerateContent")
    assert request.url.params["alt"] == "sse"
    generation = json.loads(request.content)["generationConfig"]
    assert generation["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert generation["speechConfig"]["languageCode"] == "te-IN"
    assert "responseFormat" not in generation


@pytest.mark.asyncio
@pytest.mark.parametrize("first, expected", [
    (_sse(_audio_event(b"\x00\x00", mime_type="audio/wav")), "raw PCM16"),
    (_sse(_audio_event(b"\x00\x00", mime_type="audio/l16;rate=16000")), "sample format"),
    (_sse(_audio_event(b"\x00\x00", mime_type="audio/l16;channels=2")), "sample format"),
    (b'data: {"candidates": [}\n\n', "malformed streaming JSON"),
    (_sse({"error": {"message": "do not expose upstream details"}}), "streaming error"),
    (_sse({"candidates": [{"finishReason": "SAFETY"}]}), "without complete audio"),
    (_sse({"candidates": [{"finishReason": "STOP"}]}), "no audio"),
    (_sse(_audio_event(b"\x00")) + _sse({"candidates": [{"finishReason": "STOP"}]}), "incomplete PCM16"),
    (_sse(_audio_event(b"\x00\x00")), "before completion"),
    (b'data: {"candidates":[{"content":{"parts":[{"inlineData":{"mimeType":"audio/l16","data":"!"}}]}}]}\n\n', "malformed base64"),
])
async def test_stream_rejects_invalid_audio_and_incomplete_responses(monkeypatch, first, expected):
    response = _ResponseStream(first)
    _patch_http(monkeypatch, response)
    with pytest.raises(RuntimeError, match=expected):
        async for _ in gemini_tts.GeminiTTSAdapter(api_key="unit-key").stream_with_metadata(
            "Hello", _config(),
        ):
            pass
    assert response.closed


@pytest.mark.asyncio
async def test_stream_fails_without_credentials_and_does_not_open_http(monkeypatch):
    adapter = gemini_tts.GeminiTTSAdapter()
    monkeypatch.setattr(adapter, "_api_key", lambda: "")
    client = AsyncMock()
    monkeypatch.setattr(gemini_tts.httpx, "AsyncClient", client)
    with pytest.raises(RuntimeError, match="not configured"):
        await anext(adapter.stream_with_metadata("Hello", _config()))
    client.assert_not_called()


@pytest.mark.asyncio
async def test_stream_rejects_unverified_model_before_http(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(gemini_tts.httpx, "AsyncClient", client)
    adapter = gemini_tts.GeminiTTSAdapter(api_key="unit-key")
    with pytest.raises(ValueError, match="does not support streaming"):
        await anext(adapter.stream_with_metadata("Hello", _config("gemini-2.5-pro-preview-tts")))
    client.assert_not_called()


@pytest.mark.asyncio
async def test_stream_http_failure_is_sanitized_and_closes_response(monkeypatch):
    response = _ResponseStream(b"upstream private details")
    _patch_http(monkeypatch, response, status=403)
    with pytest.raises(RuntimeError, match="^Gemini TTS HTTP 403$"):
        await anext(gemini_tts.GeminiTTSAdapter(api_key="unit-key").stream_with_metadata("Hi", _config()))
    assert response.closed


@pytest.mark.asyncio
async def test_stream_timeout_is_bounded_and_closes_response(monkeypatch):
    class TimedOutStream(_ResponseStream):
        async def __aiter__(self):
            raise httpx.ReadTimeout("private upstream details")
            yield b""  # pragma: no cover

    response = TimedOutStream(b"")
    _patch_http(monkeypatch, response)
    with pytest.raises(TimeoutError, match="timed out"):
        await anext(gemini_tts.GeminiTTSAdapter(api_key="unit-key").stream_with_metadata("Hi", _config()))
    assert response.closed


def _voice(*, sample_rate=16000, codec="linear16") -> SimpleNamespace:
    return SimpleNamespace(
        call_id=None, current_turn_id="turn-1", current_generation_id="generation-1",
        _interrupted_generation=None, _closed=False, _wire_frames_out=0,
        current_output_codec="L16", sample_rate=sample_rate, tts_output_codec=codec,
        emission_blocked=lambda: False, _emit_agent_wire=AsyncMock(),
    )


async def _open_session(monkeypatch, voice) -> PstnTurnTtsSession:
    import server.providers

    adapter = gemini_tts.GeminiTTSAdapter(api_key="unit-key")
    registry = SimpleNamespace(
        is_provider_enabled=lambda provider, stage: (provider, stage) == ("gemini", "tts"),
        is_model_allowed=lambda _provider, _stage, model: model == _config().model,
        get_tts=lambda _provider: adapter,
    )
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: registry)
    selection = SimpleNamespace(
        provider="gemini", model=_config().model,
        config={"api_mode": "streaming_rest", "speaker": "Kore"},
    )
    session = PstnTurnTtsSession(voice)
    await session._open_composed(
        resolved_stack=SimpleNamespace(tts=selection, language="te-IN"), language_code="te-IN",
    )
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("sample_rate, codec, frame_size", [(16000, "linear16", 640), (8000, "mulaw", 160)])
async def test_pstn_stream_plays_wire_frames_before_synthesis_completes(
    monkeypatch, sample_rate, codec, frame_size,
):
    pcm = b"\x01\x00" * 2400  # 100ms PCM24k
    end = {
        "candidates": [{"finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 8},
    }
    response = _ResponseStream(_sse(_audio_event(pcm)), _sse(end), gated=True)
    _patch_http(monkeypatch, response)
    voice = _voice(sample_rate=sample_rate, codec=codec)
    emitted = asyncio.Event()
    voice._emit_agent_wire.side_effect = lambda _frame: emitted.set()
    session = await _open_session(monkeypatch, voice)
    send = asyncio.create_task(session.send_text("Hello"))
    await asyncio.wait_for(emitted.wait(), timeout=1)

    assert not send.done()
    assert not response.release.is_set()
    assert session._tts_rate == 24000
    assert all(len(call.args[0]) == frame_size for call in voice._emit_agent_wire.call_args_list)
    response.release.set()
    await send
    await session.finish()
    assert session._tts_pcm_samples == 2400
    assert session._tts_audio_seconds == 0.1
    assert session._chars_sent == 5
    assert session._tts_native_usage["input_tokens"] == 3
    assert session._tts_native_usage["output_audio_tokens"] == 8
    assert response.closed
    await session.close()


@pytest.mark.asyncio
async def test_pstn_interrupt_cancels_blocked_http_and_drops_pending_audio(monkeypatch):
    response = _ResponseStream(_sse(_audio_event(b"\x00\x00" * 2400)), gated=True)
    _patch_http(monkeypatch, response)
    voice = _voice()
    session = await _open_session(monkeypatch, voice)
    send = asyncio.create_task(session.send_text("Hello"))
    await asyncio.wait_for(response.waiting.wait(), timeout=1)
    before = voice._emit_agent_wire.call_count
    await asyncio.wait_for(session.interrupt(), timeout=1)
    with pytest.raises(asyncio.CancelledError):
        await send

    assert response.closed
    assert not session._audio_buf
    assert session._pcm_resampler is None
    await session.finish()
    assert voice._emit_agent_wire.call_count == before


@pytest.mark.asyncio
async def test_pstn_stale_generation_closes_stream_without_late_frames(monkeypatch):
    first = _sse(_audio_event(b"\x00\x00" * 2401))
    rest = _sse(_audio_event(b"\x01\x00" * 2400)) + _sse({"candidates": [{"finishReason": "STOP"}]})
    response = _ResponseStream(first, rest, gated=True)
    _patch_http(monkeypatch, response)
    voice = _voice()
    session = await _open_session(monkeypatch, voice)
    send = asyncio.create_task(session.send_text("Hello"))
    await asyncio.wait_for(response.waiting.wait(), timeout=1)
    before = voice._emit_agent_wire.call_count
    assert session._audio_buf  # A partial carrier frame must also be discarded.
    voice.current_generation_id = "generation-2"
    response.release.set()
    await send
    await session.finish()

    assert response.closed
    assert voice._emit_agent_wire.call_count == before
    assert not session._audio_buf
    assert session._pcm_resampler is None
    await session.close()


def test_registry_advertises_streaming_per_supported_model(monkeypatch):
    from server.providers.registry import ProviderRegistry
    from server.services.dev_secrets_store import dev_secrets_store

    monkeypatch.setattr(dev_secrets_store, "effective", lambda field, default=None: default)
    settings = SimpleNamespace(
        enable_gemini=True, gemini_api_key="unit-key",
        allowed_gemini_llm_models=[], gemini_model="gemini-3.5-flash-lite",
        allowed_gemini_tts_models=["gemini-2.5-pro-preview-tts", "gemini-3.8-flash-lite-tts"],
    )
    registry = ProviderRegistry.__new__(ProviderRegistry)
    catalog = registry._gemini_provider_entry(settings)
    old, streaming = catalog["models"]["tts"]
    assert old["api_modes"] == ["unary_rest"]
    assert old["streaming"] is False
    assert streaming["api_modes"] == ["unary_rest", "streaming_rest"]
    assert streaming["api_mode"] == "unary_rest"
    assert streaming["streaming"] is True
