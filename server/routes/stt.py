"""
STT route — server/routes/stt.py
POST /api/stt  multipart file → Sarvam saaras:v3
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from server.config.constants import constants
from server.services.sarvam_stt_service import transcribe
from server.utils.audio import is_allowed_audio, validate_audio_size
from server.utils.errors import AppError
from server.utils.logger import log_error

router = APIRouter()


@router.post("/api/stt")
async def stt_route(
    file: UploadFile = File(..., description="Audio file WAV/MP3 etc. ≤10MB, ≤30s"),
    language_code: str = Form("te-IN"),
    mode: str = Form("transcribe"),
):
    # Validate language_code
    if language_code not in constants.SUPPORTED_LANGUAGES and language_code != "unknown":
        # Allow any te-IN etc but default to te-IN if invalid
        language_code = "te-IN"
    if mode not in ("transcribe", "translate", "verbatim", "translit", "codemix"):
        mode = "transcribe"

    try:
        data = await file.read()
        validate_audio_size(data, constants.MAX_AUDIO_BYTES)
        if not is_allowed_audio(file.filename or "audio.wav", file.content_type or "audio/wav"):
            # Still try — Sarvam supports many formats
            pass

        result = await transcribe(
            audio_bytes=data,
            filename=file.filename or "audio.wav",
            content_type=file.content_type or "audio/wav",
            language_code=language_code,
            mode=mode,
        )
        return result
    except AppError as e:
        log_error("STT route error", code=e.code.value, status=e.status_code)
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e
    except Exception as e:
        log_error("STT unexpected", err=str(e)[:500])
        raise HTTPException(status_code=500, detail={"error": {"code": "provider_error", "message": "STT failed unexpectedly"}}) from e
