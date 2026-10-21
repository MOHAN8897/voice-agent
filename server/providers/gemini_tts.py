"""Unary Gemini text-to-speech adapter with explicit WAV validation."""

from __future__ import annotations

import base64
import binascii
import json
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


@dataclass(frozen=True)
class GeminiTTSResult:
    """Per-request synthesis data; sample rate comes from the returned WAV."""

    audio_bytes: bytes
    content_type: str
    media: PcmWavMetadata
    usage: dict[str, int]


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
    """Gemini TTS is separate from Gemini Live and currently uses unary REST."""

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
        raise NotImplementedError("Gemini TTS streaming is not exposed by this unary adapter")

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
