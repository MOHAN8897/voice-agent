"""Gemini text-to-speech with validated unary WAV and streaming PCM transports."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from server.config.env import get_settings
from server.providers.audio_media import PcmWavMetadata, parse_pcm16_wav
from server.providers.base import TTSConfig
from server.providers.gemini_llm import gemini_usage_from_metadata
from server.services.dev_secrets_store import dev_secrets_store

GEMINI_GENERATE_CONTENT_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_TTS_REQUEST_SAMPLE_RATE = 24000
GEMINI_STREAMING_TTS_MODELS = frozenset({
    "gemini-3.1-flash-tts-preview",
    "gemini-3.8-flash-tts",
    "gemini-3.8-flash-lite-tts",
})


def supports_gemini_tts_streaming(model: str) -> bool:
    """Only advertise models whose raw PCM streaming contract is documented."""
    return str(model or "").strip().removeprefix("models/") in GEMINI_STREAMING_TTS_MODELS


@dataclass(frozen=True)
class GeminiTTSResult:
    """Per-request synthesis data; sample rate comes from the returned WAV."""

    audio_bytes: bytes
    content_type: str
    media: PcmWavMetadata
    usage: dict[str, int]


@dataclass(frozen=True)
class GeminiTTSChunk:
    """Headerless signed little-endian PCM16 and incremental native token usage."""

    audio_bytes: bytes
    sample_rate: int
    usage: dict[str, int]


async def _sse_payloads(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    data: list[str] = []
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif line != "":
            continue
        if line == "" and data:
            raw = "\n".join(data)
            data.clear()
            if raw == "[DONE]":
                return
            yield _stream_payload(raw)
    if data:
        yield _stream_payload("\n".join(data))


def _stream_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Gemini TTS returned malformed streaming JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("Gemini TTS returned malformed streaming JSON")
    if payload.get("error"):
        raise RuntimeError("Gemini TTS returned a streaming error")
    return payload


def _decode_pcm(inline_data: dict[str, Any]) -> bytes:
    mime_type = str(inline_data.get("mimeType") or inline_data.get("mime_type") or "")
    fields = [part.strip().lower() for part in mime_type.split(";")]
    if fields[0] not in {"audio/l16", "audio/pcm"}:
        raise RuntimeError("Gemini TTS streaming requires raw PCM16 audio")
    parameters = dict(part.split("=", 1) for part in fields[1:] if "=" in part)
    if parameters.get("rate", "24000") != "24000" or parameters.get("channels", "1") != "1":
        raise RuntimeError("Gemini TTS streaming returned an unsupported PCM sample format")
    encoded = inline_data.get("data")
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError("Gemini TTS returned an empty audio block")
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise RuntimeError("Gemini TTS returned malformed base64 audio") from exc
    if not audio:
        raise RuntimeError("Gemini TTS returned an empty audio block")
    return audio


def _audio_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Gemini TTS returned no audio candidates")
    candidate = candidates[0]
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise TypeError("Gemini TTS returned no audio parts")
    audio: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        inline_data = part.get("inlineData") or part.get("inline_data")
        if isinstance(inline_data, dict):
            audio.append(inline_data)
    if not audio:
        raise RuntimeError("Gemini TTS returned no audio parts")
    if len(audio) != 1:
        raise RuntimeError("Gemini TTS must return exactly one complete audio block")
    return audio


def _decode_wav(inline_data: dict[str, Any]) -> tuple[bytes, PcmWavMetadata, str]:
    mime_type = str(inline_data.get("mimeType") or inline_data.get("mime_type") or "")
    media_type = mime_type.split(";", 1)[0].strip().lower()
    if media_type not in {"audio/wav", "audio/x-wav"}:
        raise RuntimeError("Gemini TTS returned audio outside the requested WAV format")
    encoded = inline_data.get("data")
    if not isinstance(encoded, str) or not encoded.strip():
        raise RuntimeError("Gemini TTS returned an empty audio block")
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise RuntimeError("Gemini TTS returned malformed base64 audio") from exc
    try:
        media = parse_pcm16_wav(audio)
    except ValueError as exc:
        raise RuntimeError("Gemini TTS returned invalid PCM16 WAV audio") from exc
    return audio, media, "audio/wav"


class GeminiTTSAdapter:
    """Gemini TTS is separate from Gemini Live; transport is pinned by the stack."""

    provider_id = "gemini"

    def __init__(self, *, api_key: str | None = None) -> None:
        self._provided_api_key = api_key

    def _api_key(self) -> str:
        settings = get_settings()
        return (
            self._provided_api_key
            or dev_secrets_store.effective_secret("gemini_api_key")
            or settings.gemini_api_key
            or ""
        ).strip()

    @staticmethod
    def _timeout() -> httpx.Timeout:
        timeout_s = max(0.1, get_settings().request_timeout_ms / 1000)
        return httpx.Timeout(
            timeout=timeout_s,
            connect=min(timeout_s, 10.0),
            read=timeout_s,
            write=timeout_s,
            pool=timeout_s,
        )

    def connect_stream(self, config: TTSConfig):
        _ = config
        raise NotImplementedError(
            "Gemini TTS WebSocket is not exposed by this unary adapter interface; "
            "use stream_with_metadata for SSE"
        )

    async def stream_with_metadata(
        self, text: str, config: TTSConfig,
    ) -> AsyncIterator[GeminiTTSChunk]:
        """Yield audio as each SSE event arrives; closing the iterator closes HTTP."""
        if config.provider != self.provider_id:
            raise ValueError("Gemini TTS config provider does not match the resolved stack")
        key = self._api_key()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        model = (config.model or "").strip().removeprefix("models/")
        if not supports_gemini_tts_streaming(model):
            raise ValueError("The selected Gemini TTS model does not support streaming")
        speaker = (config.speaker or "").strip()
        if not speaker:
            raise ValueError("Gemini TTS requires the voice selected in the resolved stack")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Gemini TTS requires non-empty text")
        url = f"{GEMINI_GENERATE_CONTENT_BASE}/{quote(model, safe='-_.')}:streamGenerateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": text.strip()}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "languageCode": config.language,
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": speaker}},
                },
            },
        }
        # The streaming default is raw PCM24k. Do not request unary WAV or assume
        # the requested sample rate is honored; resample at the media boundary.
        pending = b""
        received_audio = False
        completed = False
        native_usage: dict[str, int] = {}
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout()) as client,
                client.stream(
                    "POST", url, params={"alt": "sse"},
                    headers={
                        "x-goog-api-key": key,
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                    json=body,
                ) as response,
            ):
                if response.status_code >= 400:
                    raise RuntimeError(f"Gemini TTS HTTP {response.status_code}")
                async for payload in _sse_payloads(response):
                    feedback = payload.get("promptFeedback") or {}
                    if isinstance(feedback, dict) and feedback.get("blockReason"):
                        raise RuntimeError("Gemini TTS streaming request was blocked")
                    candidates = payload.get("candidates") or []
                    if not isinstance(candidates, list):
                        raise TypeError("Gemini TTS returned malformed streaming candidates")
                    audio = bytearray()
                    if candidates:
                        candidate = candidates[0]
                        if not isinstance(candidate, dict):
                            raise RuntimeError("Gemini TTS returned malformed streaming candidate")
                        finish = candidate.get("finishReason") or candidate.get("finish_reason")
                        if finish and finish != "STOP":
                            raise RuntimeError("Gemini TTS streaming ended without complete audio")
                        completed = completed or finish == "STOP"
                        content = candidate.get("content") or {}
                        parts = content.get("parts") if isinstance(content, dict) else None
                        if parts is not None and not isinstance(parts, list):
                            raise RuntimeError("Gemini TTS returned malformed streaming parts")
                        for part in parts or []:
                            if not isinstance(part, dict):
                                continue
                            inline = part.get("inlineData") or part.get("inline_data")
                            if isinstance(inline, dict):
                                audio.extend(_decode_pcm(inline))
                    received_audio = received_audio or bool(audio)
                    pcm = pending + bytes(audio)
                    aligned_size = len(pcm) - len(pcm) % 2
                    pending = pcm[aligned_size:]
                    meta = payload.get("usageMetadata") or payload.get("usage_metadata")
                    usage_delta: dict[str, int] = {}
                    for name, count in gemini_usage_from_metadata(meta, native_audio=True).items():
                        previous = native_usage.get(name, 0)
                        if count > previous:
                            usage_delta[name] = count - previous
                            native_usage[name] = count
                    if aligned_size or usage_delta:
                        yield GeminiTTSChunk(
                            audio_bytes=pcm[:aligned_size],
                            sample_rate=GEMINI_TTS_REQUEST_SAMPLE_RATE,
                            usage=usage_delta,
                        )
        except httpx.TimeoutException as exc:
            raise TimeoutError("Gemini TTS streaming request timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("Gemini TTS streaming transport failed") from exc
        if pending:
            raise RuntimeError("Gemini TTS streaming returned an incomplete PCM16 sample")
        if not received_audio:
            raise RuntimeError("Gemini TTS streaming returned no audio")
        if not completed:
            raise RuntimeError("Gemini TTS streaming ended before completion")

    async def synthesize_rest(self, text: str, config: TTSConfig) -> bytes:
        result = await self.synthesize_with_metadata(text, config)
        return result.audio_bytes

    async def synthesize_with_metadata(self, text: str, config: TTSConfig) -> GeminiTTSResult:
        if config.provider != self.provider_id:
            raise ValueError("Gemini TTS config provider does not match the resolved stack")
        key = self._api_key()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        model = (config.model or "").strip()
        if not model:
            raise ValueError("Gemini TTS requires the model selected in the resolved stack")
        speaker = (config.speaker or "").strip()
        if not speaker:
            raise ValueError("Gemini TTS requires the voice selected in the resolved stack")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Gemini TTS requires non-empty text")

        model_path = model.removeprefix("models/")
        url = f"{GEMINI_GENERATE_CONTENT_BASE}/{quote(model_path, safe='-_.')}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": text.strip()}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "responseFormat": {
                    "audio": {
                        "mimeType": "AUDIO_WAV",
                        "sampleRate": GEMINI_TTS_REQUEST_SAMPLE_RATE,
                    }
                },
                "speechConfig": {
                    "languageCode": config.language,
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": speaker}},
                },
            },
        }
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            try:
                response = await client.post(
                    url,
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=body,
                )
            except httpx.TimeoutException as exc:
                raise TimeoutError("Gemini TTS request timed out") from exc
            except httpx.HTTPError as exc:
                raise RuntimeError("Gemini TTS transport failed") from exc
        if response.status_code >= 400:
            raise RuntimeError(f"Gemini TTS HTTP {response.status_code}")
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Gemini TTS returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise TypeError("Gemini TTS returned malformed JSON")

        inline_data = _audio_parts(payload)[0]
        audio, media, content_type = _decode_wav(inline_data)
        usage_metadata = payload.get("usageMetadata") or payload.get("usage_metadata")
        usage = (
            gemini_usage_from_metadata(usage_metadata, native_audio=True)
            if isinstance(usage_metadata, dict)
            else {}
        )
        return GeminiTTSResult(
            audio_bytes=audio,
            content_type=content_type,
            media=media,
            usage=usage,
        )
