"""
TTS routes — server/routes/tts.py
POST /api/tts       → REST (base64 decode, returns audio/wav)
POST /api/tts/stream→ proxy binary stream (audio/mpeg)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from server.config.constants import constants
from server.services.registry_tts_service import synthesize_via_registry
from server.services.sarvam_tts_service import synthesize, synthesize_stream
from server.utils.errors import AppError
from server.utils.logger import log_error

router = APIRouter()


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=3500, description="Text to synthesize — Telugu + code-mix OK")
    language_code: str = Field("te-IN")
    sessionId: str = Field("default", max_length=100, description="Session for runtime TTS overrides")
    callId: str | None = Field(None, max_length=64, description="Active call — resolves stack TTS provider")
    speaker: str | None = Field(None, description="Override speaker; else resolved from runtime/env")
    pace: float | None = Field(None, ge=0.5, le=2.0)
    model: str | None = None
    temperature: float | None = Field(None, ge=0.01, le=1.0)


@router.post("/api/tts")
async def tts_rest(body: TTSRequest):
    # Enforce REST limit strictly
    if len(body.text) > constants.TTS_MAX_CHARS_REST:
        raise HTTPException(
            status_code=413,
            detail={"error": {"code": "validation_error", "message": f"Text too long. Max {constants.TTS_MAX_CHARS_REST} for REST. Use /api/tts/stream for up to 3500."}},
        )
    # Validate language
    lang = body.language_code if body.language_code in constants.SUPPORTED_LANGUAGES else "te-IN"
    try:
        result = await synthesize_via_registry(
            text=body.text,
            language_code=lang,
            speaker=body.speaker,
            pace=body.pace,
            model=body.model,
            temperature=body.temperature,
            session_id=body.sessionId,
            call_id=body.callId,
        )
        if body.callId and result.get("audio_bytes"):
            import asyncio

            from server.call.audio_archive import audio_archive

            archive_bytes = result.get("pcm_for_archive") or result["audio_bytes"]
            asyncio.create_task(audio_archive.append_agent_audio(body.callId, archive_bytes))
        return Response(
            content=result["audio_bytes"],
            media_type=result["content_type"],
            headers={
                "X-Request-Id": result.get("request_id") or "",
                "X-Speaker": result.get("speaker") or "",
                "X-TTS-Provider": result.get("provider") or "",
            },
        )
    except AppError as e:
        log_error("TTS route error", code=e.code.value, status=e.status_code)
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e


@router.post("/api/tts/stream")
async def tts_stream(body: TTSRequest):
    lang = body.language_code if body.language_code in constants.SUPPORTED_LANGUAGES else "te-IN"
    if len(body.text) > constants.TTS_MAX_CHARS_STREAM:
        raise HTTPException(status_code=413, detail={"error": {"code": "validation_error", "message": f"Text too long. Max {constants.TTS_MAX_CHARS_STREAM} chars."}})
    try:
        generator = synthesize_stream(
            text=body.text,
            language_code=lang,
            speaker=body.speaker,
            pace=body.pace,
            model=body.model,
            output_audio_codec="mp3",
            session_id=body.sessionId,
            temperature=body.temperature,
        )
        return StreamingResponse(generator, media_type="audio/mpeg", headers={"Cache-Control": "no-cache"})
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e
