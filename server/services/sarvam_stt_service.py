"""
Sarvam STT service — server/services/sarvam_stt_service.py
Wraps POST https://api.sarvam.ai/speech-to-text  (saaras:v3)
Direct httpx, no SDK version pin risk. Auth: api-subscription-key header.
"""
from __future__ import annotations

import httpx

from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store
from server.utils.errors import AppError, ErrorCode, classify_http_status
from server.utils.http_clients import get_sarvam_client
from server.utils.logger import log_error, log_stt

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


async def transcribe(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    content_type: str = "audio/wav",
    language_code: str = "te-IN",
    model: str | None = None,
    mode: str = "transcribe",
    timeout_ms: int | None = None,
) -> dict:
    """
    Sends audio to Sarvam STT and returns {transcript, language_code, request_id, raw}.
    Raises AppError on failure (classified).
    """
    settings = get_settings()
    api_key = dev_secrets_store.effective_secret("sarvam_api_key") or settings.sarvam_api_key or ""
    model = model or settings.sarvam_stt_model
    timeout_s = (timeout_ms or settings.request_timeout_ms) / 1000

    log_stt("Audio submitted", bytes=len(audio_bytes), language_code=language_code, model=model, mode=mode)

    # httpx multipart
    files = {"file": (filename, audio_bytes, content_type)}
    data = {
        "model": model,
        "language_code": language_code,
        "mode": mode,
    }

    headers = {"api-subscription-key": api_key}

    try:
        client = get_sarvam_client()
        resp = await client.post(SARVAM_STT_URL, headers=headers, files=files, data=data, timeout=timeout_s)
    except httpx.TimeoutException as e:
        raise AppError(ErrorCode.TIMEOUT, provider="sarvam_stt", retryable=True, cause=e) from e
    except httpx.NetworkError as e:
        raise AppError(ErrorCode.NETWORK_ERROR, provider="sarvam_stt", retryable=True, cause=e) from e

    if resp.status_code != 200:
        log_error("STT failed", status=resp.status_code, body=resp.text[:500])
        raise classify_http_status(resp.status_code, "sarvam_stt")

    try:
        body = resp.json()
    except Exception as e:
        raise AppError(ErrorCode.PROVIDER_ERROR, provider="sarvam_stt", cause=e) from e

    transcript = (body.get("transcript") or "").strip()
    # Sarvam may return empty transcript for silence/noise
    if not transcript:
        # Not an error — let caller prompt retry, but still return
        log_stt("Empty transcript", request_id=body.get("request_id"))

    result = {
        "transcript": transcript,
        "language_code": body.get("language_code") or language_code,
        "request_id": body.get("request_id"),
        "raw": body,
    }
    log_stt("Transcript received", chars=len(transcript), language_code=result["language_code"])
    return result
