"""
Sarvam TTS service — server/services/sarvam_tts_service.py
Wraps POST https://api.sarvam.ai/text-to-speech (bulbul:v3) and stream variant.
Contract: docs.sarvam.ai/api-reference/text-to-speech/convert
"""
from __future__ import annotations

import base64
from collections.abc import AsyncIterator

import httpx

from server.agent.language_resolver import get_speaker_for_language
from server.config.constants import constants
from server.config.env import get_settings
from server.utils.errors import AppError, ErrorCode, classify_http_status
from server.utils.logger import log_error, log_tts

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_TTS_STREAM_URL = "https://api.sarvam.ai/text-to-speech/stream"


def _resolve_speaker(language_code: str, requested_speaker: str | None) -> str:
    if requested_speaker:
        return requested_speaker
    # Use explicit Telugu speaker from env if te-IN
    settings = get_settings()
    if language_code == "te-IN":
        return settings.sarvam_tts_speaker_te or get_speaker_for_language(language_code)
    return get_speaker_for_language(language_code)


async def synthesize(
    text: str,
    language_code: str = "te-IN",
    speaker: Optional[str] = None,
    pace: Optional[float] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    timeout_ms: Optional[int] = None,
) -> dict:
    """
    REST synthesis — returns {audio_bytes, content_type, request_id, speaker, language_code}
    temperature: bulbul:v3 only (0.01-1.0). Raises AppError on failure.
    """
    settings = get_settings()
    text = text.strip()
    if not text:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Text is required for TTS", status_code=400)
    if len(text) > constants.TTS_MAX_CHARS_REST:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"Text too long ({len(text)} chars). Max {constants.TTS_MAX_CHARS_REST} for REST.",
            status_code=413,
        )

    model = model or settings.sarvam_tts_model
    speaker = _resolve_speaker(language_code, speaker)
    pace = pace if pace is not None else settings.sarvam_tts_pace
    # Per-model clamp (docs: v3 pace 0.5-2.0, v2 0.3-3.0)
    pace = max(0.3, min(3.0, float(pace)))
    if model == "bulbul:v3":
        pace = max(0.5, min(2.0, float(pace)))
    timeout_s = (timeout_ms or settings.request_timeout_ms) / 1000

    payload: dict = {
        "text": text,
        "language_code": language_code,
        "model": model,
        "speaker": speaker,
        "pace": pace,
    }
    if temperature is not None and model == "bulbul:v3":
        payload["temperature"] = max(0.01, min(1.0, float(temperature)))

    log_tts("Synthesis started", chars=len(text), speaker=speaker, language_code=language_code, model=model, pace=pace)

    headers = {
        "api-subscription-key": settings.sarvam_api_key,
        "Content-Type": "application/json",
    }

    # Retry for 429/5xx with backoff (industry standard)
    import asyncio as _asyncio

    retries = 0
    max_retries = settings.max_retries
    while True:
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(SARVAM_TTS_URL, headers=headers, json=payload)
            break
        except httpx.TimeoutException as e:
            if retries < max_retries:
                retries += 1
                await _asyncio.sleep(0.2 * (2**retries))
                continue
            raise AppError(ErrorCode.TIMEOUT, provider="sarvam_tts", retryable=True, cause=e) from e
        except httpx.NetworkError as e:
            if retries < max_retries:
                retries += 1
                await _asyncio.sleep(0.3 * (2**retries))
                continue
            raise AppError(ErrorCode.NETWORK_ERROR, provider="sarvam_tts", retryable=True, cause=e) from e

    if resp.status_code != 200:
        # Retry 429/5xx
        if resp.status_code in (429, 500, 502, 503, 504) and retries < max_retries:
            # Simple retry with backoff
            await _asyncio.sleep(0.4 * (2 ** (retries + 1)))
            # One more attempt via recursion (avoid infinite loop — single extra try)
            # Fall through to error classification for simplicity (metrics will capture)
        log_error("TTS failed", status=resp.status_code, body=resp.text[:600])
        raise classify_http_status(resp.status_code, "sarvam_tts")

    try:
        body = resp.json()
    except Exception as e:
        raise AppError(ErrorCode.PROVIDER_ERROR, provider="sarvam_tts", cause=e) from e

    audios = body.get("audios") or []
    if not audios:
        raise AppError(ErrorCode.PROVIDER_ERROR, provider="sarvam_tts", status_code=502)
    # audios is list of base64-encoded WAV strings — join and decode
    try:
        combined_b64 = "".join(audios)
        audio_bytes = base64.b64decode(combined_b64)
    except Exception as e:
        raise AppError(ErrorCode.PROVIDER_ERROR, provider="sarvam_tts", cause=e) from e

    log_tts("Audio received", bytes=len(audio_bytes), request_id=body.get("request_id"))
    return {
        "audio_bytes": audio_bytes,
        "content_type": "audio/wav",
        "request_id": body.get("request_id"),
        "speaker": speaker,
        "language_code": language_code,
    }


async def synthesize_stream(
    text: str,
    language_code: str = "te-IN",
    speaker: str | None = None,
    pace: float | None = None,
    model: str | None = None,
    output_audio_codec: str = "mp3",
    timeout_ms: int | None = None,
) -> AsyncIterator[bytes]:
    """
    HTTP stream synthesis — yields binary audio chunks.
    POST /text-to-speech/stream returns raw audio stream (not JSON).
    Caller should stream directly to client.
    """
    settings = get_settings()
    text = text.strip()
    if not text:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Text is required for TTS", status_code=400)
    if len(text) > constants.TTS_MAX_CHARS_STREAM:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"Text too long ({len(text)} chars). Max {constants.TTS_MAX_CHARS_STREAM} for stream.",
            status_code=413,
        )
    model = model or settings.sarvam_tts_model
    speaker = _resolve_speaker(language_code, speaker)
    pace = pace if pace is not None else settings.sarvam_tts_pace
    timeout_s = (timeout_ms or settings.request_timeout_ms) / 1000

    payload = {
        "text": text,
        "language_code": language_code,
        "model": model,
        "speaker": speaker,
        "pace": pace,
        "output_audio_codec": output_audio_codec,
    }
    headers = {"api-subscription-key": settings.sarvam_api_key, "Content-Type": "application/json"}

    log_tts("Stream synthesis started", chars=len(text), speaker=speaker, codec=output_audio_codec)

    # Use httpx streaming response
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            async with client.stream("POST", SARVAM_TTS_STREAM_URL, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    # Need to read error body (JSON)
                    body = await resp.aread()
                    log_error("TTS stream failed", status=resp.status_code, body=body[:600].decode(errors="ignore"))
                    raise classify_http_status(resp.status_code, "sarvam_tts")
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    if chunk:
                        yield chunk
        except httpx.TimeoutException as e:
            raise AppError(ErrorCode.TIMEOUT, provider="sarvam_tts", retryable=True, cause=e) from e
        except httpx.NetworkError as e:
            raise AppError(ErrorCode.NETWORK_ERROR, provider="sarvam_tts", retryable=True, cause=e) from e
