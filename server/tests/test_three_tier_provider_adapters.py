"""Focused contract tests for the composed-stack provider adapters (no network)."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import wave
from types import SimpleNamespace
from typing import Any

import httpx
import pytest


def _wav_bytes(*, sample_rate: int = 24000, frames: int = 160) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


def _settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "request_timeout_ms": 500,
        "max_response_length": 100,
        "sarvam_api_key": None,
        "gemini_api_key": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _JsonResponse:
    def __init__(self, payload: Any, *, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class _FakeHttpClient:
    def __init__(self, *, response: Any = None, post_error: Exception | None = None) -> None:
        self.response = response
        self.post_error = post_error
        self.closed = False
        self.entered = False
        self.captured: dict[str, Any] = {}

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.closed = True

    async def post(self, url: str, **kwargs: Any):
        self.captured = {"url": url, **kwargs}
        if self.post_error:
            raise self.post_error
        return self.response


def _patch_client(monkeypatch, module: str, fake: _FakeHttpClient) -> None:
    monkeypatch.setattr(f"{module}.httpx.AsyncClient", lambda **_kwargs: fake)


@pytest.mark.asyncio
async def test_sarvam_llm_uses_selected_model_and_emits_terminal_usage(monkeypatch):
    from server.providers import sarvam_llm

    monkeypatch.setattr(sarvam_llm, "get_settings", lambda: _settings())
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hello"}}]}),
        "data: "
        + json.dumps(
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 40,
                    "completion_tokens": 12,
                    "total_tokens": 52,
                    "prompt_tokens_details": {"cached_tokens": 8},
                },
            }
        ),
        "data: [DONE]",
    ]

    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

    class Client(_FakeHttpClient):
        def stream(self, method: str, url: str, **kwargs: Any):
            self.captured = {"method": method, "url": url, **kwargs}
            return Response()

    fake = Client()
    _patch_client(monkeypatch, "server.providers.sarvam_llm", fake)
    events = [
        event
        async for event in sarvam_llm.SarvamLLMAdapter(api_key="test-key").stream_live_turn(
            input_messages=[{"role": "user", "content": "Hi"}],
            model="sarvam-105b", api_mode="chat_completions_v2",
        )
    ]

    assert fake.closed
    assert fake.captured["url"] == sarvam_llm.SARVAM_CHAT_COMPLETIONS_V2_URL
    assert fake.captured["headers"]["api-subscription-key"] == "test-key"
    assert fake.captured["json"]["model"] == "sarvam-105b"
    assert fake.captured["json"]["stream_options"] == {"include_usage": True}
    assert events[0]["delta"] == "Hello"
    assert events[-1]["done"] is True
    assert events[-1]["usage"] == {
        "input_tokens": 40,
        "output_tokens": 12,
        "total_tokens": 52,
        "cached_tokens": 8,
        "cache_write_tokens": 0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lines, message",
    [
        (["data: not-json"], "malformed SSE"),
        (["data: [DONE]"], "empty response"),
    ],
)
async def test_sarvam_llm_rejects_malformed_and_empty_streams(monkeypatch, lines, message):
    from server.providers import sarvam_llm

    monkeypatch.setattr(sarvam_llm, "get_settings", lambda: _settings())

    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

    class Client(_FakeHttpClient):
        def stream(self, *_args, **_kwargs):
            return Response()

    fake = Client()
    _patch_client(monkeypatch, "server.providers.sarvam_llm", fake)
    adapter = sarvam_llm.SarvamLLMAdapter(api_key="test-key")
    with pytest.raises(RuntimeError, match=message):
        async for _ in adapter.stream_live_turn(
            input_messages=[{"role": "user", "content": "Hi"}], model="sarvam-105b"
        ):
            pass
    assert fake.closed


@pytest.mark.asyncio
async def test_sarvam_llm_timeout_and_missing_model_fail_closed(monkeypatch):
    from server.providers import sarvam_llm

    monkeypatch.setattr(sarvam_llm, "get_settings", lambda: _settings())

    class Client(_FakeHttpClient):
        def stream(self, *_args, **_kwargs):
            raise httpx.ReadTimeout("timeout")

    timeout_client = Client()
    _patch_client(monkeypatch, "server.providers.sarvam_llm", timeout_client)
    adapter = sarvam_llm.SarvamLLMAdapter(api_key="test-key")
    with pytest.raises(TimeoutError, match="timed out"):
        async for _ in adapter.stream_live_turn(
            input_messages=[{"role": "user", "content": "Hi"}], model="sarvam-105b"
        ):
            pass
    assert timeout_client.closed
    with pytest.raises(ValueError, match="resolved stack"):
        async for _ in adapter.stream_live_turn(input_messages=[{"role": "user", "content": "Hi"}]):
            pass


@pytest.mark.asyncio
async def test_sarvam_llm_cancellation_closes_response_and_client(monkeypatch):
    from server.providers import sarvam_llm

    monkeypatch.setattr(sarvam_llm, "get_settings", lambda: _settings())
    waiting = asyncio.Event()
    closed = {"response": False}

    class Response:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            closed["response"] = True

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"Hi"}}]}'
            waiting.set()
            await asyncio.Event().wait()

    class Client(_FakeHttpClient):
        def stream(self, *_args, **_kwargs):
            return Response()

    fake = Client()
    _patch_client(monkeypatch, "server.providers.sarvam_llm", fake)
    generator = sarvam_llm.SarvamLLMAdapter(api_key="test-key").stream_live_turn(
        input_messages=[{"role": "user", "content": "Hi"}], model="sarvam-105b"
    )
    assert (await anext(generator))["delta"] == "Hi"
    pending = asyncio.create_task(anext(generator))
    await waiting.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await generator.aclose()
    assert closed["response"]
    assert fake.closed


@pytest.mark.asyncio
async def test_gemini_tts_requests_and_validates_wav_and_returns_usage(monkeypatch):
    from server.providers import gemini_tts
    from server.providers.base import TTSConfig

    monkeypatch.setattr(gemini_tts, "get_settings", lambda: _settings())
    audio = _wav_bytes(sample_rate=16000)
    fake = _FakeHttpClient(
        response=_JsonResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "audio/wav",
                                        "data": base64.b64encode(audio).decode("ascii"),
                                    }
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 12,
                    "candidatesTokenCount": 90,
                    "totalTokenCount": 102,
                },
            }
        )
    )
    _patch_client(monkeypatch, "server.providers.gemini_tts", fake)
    config = TTSConfig(
        provider="gemini", model="gemini-3.8-flash-tts", language="te-IN", speaker="voice-from-config"
    )
    result = await gemini_tts.GeminiTTSAdapter(api_key="test-key").synthesize_with_metadata(
        "Hello", config
    )

    assert fake.closed
    assert fake.captured["url"].endswith("/gemini-3.8-flash-tts:generateContent")
    assert fake.captured["headers"]["x-goog-api-key"] == "test-key"
    generation = fake.captured["json"]["generationConfig"]
    assert generation["responseModalities"] == ["AUDIO"]
    assert generation["responseFormat"]["audio"]["mimeType"] == "AUDIO_WAV"
    assert (
        generation["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
        == "voice-from-config"
    )
    assert result.audio_bytes == audio
    assert result.content_type == "audio/wav"
    assert result.media.sample_rate == 16000
    assert result.usage["input_tokens"] == 12
    assert result.usage["output_tokens"] == 90
    assert result.usage["output_audio_tokens"] == 90


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, message",
    [
        (ValueError("invalid json"), "malformed JSON"),
        ({"candidates": []}, "no audio candidates"),
        ({"candidates": [{"content": {"parts": []}}]}, "no audio parts"),
        (
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"inlineData": {"mimeType": "audio/l16", "data": "AA=="}}]
                        }
                    }
                ]
            },
            "outside the requested WAV",
        ),
        (
            {
                "candidates": [
                    {"content": {"parts": [{"inlineData": {"mimeType": "audio/wav", "data": ""}}]}}
                ]
            },
            "empty audio block",
        ),
    ],
)
async def test_gemini_tts_rejects_malformed_empty_and_unrequested_audio(
    monkeypatch, payload, message
):
    from server.providers import gemini_tts
    from server.providers.base import TTSConfig

    monkeypatch.setattr(gemini_tts, "get_settings", lambda: _settings())
    fake = _FakeHttpClient(response=_JsonResponse(payload))
    _patch_client(monkeypatch, "server.providers.gemini_tts", fake)
    adapter = gemini_tts.GeminiTTSAdapter(api_key="test-key")
    with pytest.raises(RuntimeError, match=message):
        await adapter.synthesize_rest(
            "Hello",
            TTSConfig(provider="gemini", model="gemini-3.8-flash-tts", speaker="voice-from-config"),
        )
    assert fake.closed


@pytest.mark.asyncio
async def test_gemini_tts_rejects_malformed_wav_and_timeout(monkeypatch):
    from server.providers import gemini_tts
    from server.providers.base import TTSConfig

    monkeypatch.setattr(gemini_tts, "get_settings", lambda: _settings())
    invalid_audio = base64.b64encode(b"not a wav container" * 4).decode("ascii")
    fake = _FakeHttpClient(
        response=_JsonResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"inlineData": {"mimeType": "audio/wav", "data": invalid_audio}}
                            ]
                        }
                    }
                ]
            }
        )
    )
    _patch_client(monkeypatch, "server.providers.gemini_tts", fake)
    adapter = gemini_tts.GeminiTTSAdapter(api_key="test-key")
    config = TTSConfig(provider="gemini", model="gemini-3.8-flash-tts", speaker="voice-from-config")
    with pytest.raises(RuntimeError, match="invalid PCM16 WAV"):
        await adapter.synthesize_rest("Hello", config)
    assert fake.closed

    timeout_client = _FakeHttpClient(post_error=httpx.ReadTimeout("timeout"))
    _patch_client(monkeypatch, "server.providers.gemini_tts", timeout_client)
    with pytest.raises(TimeoutError, match="timed out"):
        await adapter.synthesize_rest("Hello", config)
    assert timeout_client.closed


@pytest.mark.asyncio
async def test_gemini_tts_cancellation_closes_request_and_legacy_streaming_is_unsupported(
    monkeypatch,
):
    from server.providers import gemini_tts
    from server.providers.base import TTSConfig

    monkeypatch.setattr(gemini_tts, "get_settings", lambda: _settings())
    waiting = asyncio.Event()

    class Client(_FakeHttpClient):
        async def post(self, url: str, **kwargs: Any):
            self.captured = {"url": url, **kwargs}
            waiting.set()
            await asyncio.Event().wait()

    fake = Client()
    _patch_client(monkeypatch, "server.providers.gemini_tts", fake)
    adapter = gemini_tts.GeminiTTSAdapter(api_key="test-key")
    config = TTSConfig(provider="gemini", model="gemini-3.8-flash-tts", speaker="voice-from-config")
    request = asyncio.create_task(adapter.synthesize_rest("Hello", config))
    await waiting.wait()
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert fake.closed
    with pytest.raises(NotImplementedError, match="unary adapter"):
        adapter.connect_stream(TTSConfig(provider="gemini", model="gemini-2.5-pro-preview-tts", speaker="Zephyr"))


@pytest.mark.asyncio
async def test_sarvam_tts_validates_wav_and_propagates_cancellation(monkeypatch):
    from server.providers import sarvam_tts
    from server.providers.base import TTSConfig

    valid_audio = _wav_bytes()

    async def synthesize(*_args, **_kwargs):
        return {"audio_bytes": valid_audio, "content_type": "audio/wav"}

    monkeypatch.setattr(sarvam_tts.sarvam_tts_service, "synthesize", synthesize)
    config = TTSConfig(provider="sarvam", model="bulbul:v3", speaker="shubh")
    assert await sarvam_tts.SarvamTTSAdapter().synthesize_rest("Hello", config) == valid_audio

    with pytest.raises(ValueError, match="configured provider catalog"):
        await sarvam_tts.SarvamTTSAdapter().synthesize_rest(
            "Hello", TTSConfig(provider="sarvam", model="unconfigured-model", speaker="shubh")
        )
    with pytest.raises(ValueError, match="selected model's configured catalog"):
        await sarvam_tts.SarvamTTSAdapter().synthesize_rest(
            "Hello", TTSConfig(provider="sarvam", model="bulbul:v3", speaker="not-a-listed-voice")
        )

    async def malformed(*_args, **_kwargs):
        return {"audio_bytes": b"", "content_type": "audio/wav"}

    monkeypatch.setattr(sarvam_tts.sarvam_tts_service, "synthesize", malformed)
    with pytest.raises(RuntimeError, match="invalid WAV"):
        await sarvam_tts.SarvamTTSAdapter().synthesize_rest("Hello", config)

    waiting = asyncio.Event()

    async def pending(*_args, **_kwargs):
        waiting.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(sarvam_tts.sarvam_tts_service, "synthesize", pending)
    task = asyncio.create_task(sarvam_tts.SarvamTTSAdapter().synthesize_rest("Hello", config))
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
