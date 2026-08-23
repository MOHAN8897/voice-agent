"""
Voice Turn route — server/routes/voice.py
POST /api/voice/turn  → end-to-end: file (audio) → STT → Brain → TTS
Returns JSON with transcript, brain_text, audio (base64) + PERF metrics.
Streaming variant POST /api/voice/turn/stream would yield audio chunks (Phase 5).
"""
from __future__ import annotations

import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from server.agent.instruction_store import instruction_store
from server.config.constants import constants
from server.services.runtime_settings import runtime_settings
from server.session.voice_session import VoiceSessionController
from server.utils.audio import validate_audio_size
from server.utils.errors import AppError
from server.utils.logger import log_error

router = APIRouter()


def _runtime(session_id: str) -> dict:
    try:
        return runtime_settings.get(session_id)
    except Exception:
        return {}


@router.post("/api/voice/turn")
async def voice_turn(
    file: UploadFile = File(..., description="Audio WAV/MP3/WEBM ≤10MB"),
    language_code: str = Form("te-IN"),
    mode: str = Form("transcribe"),
    sessionId: str = Form("default"),
    userInstructions: str = Form(""),
    businessInstructions: str = Form(""),
    ttsSpeaker: str = Form(""),
):
    controller = VoiceSessionController()
    rt = _runtime(sessionId)
    try:
        data = await file.read()
        validate_audio_size(data, constants.MAX_AUDIO_BYTES)
        # lang validation
        if language_code not in constants.SUPPORTED_LANGUAGES:
            language_code = "te-IN"
        if mode not in ("transcribe", "translate", "verbatim", "translit", "codemix"):
            mode = "transcribe"

        # Prefer explicit param → runtime override (Fine-tune console) → env default
        stt_model_rt = rt.get("sttModel")
        stt_mode_eff = mode if mode != "transcribe" else rt.get("sttMode", "transcribe")
        # Dual-channel prompting: request wins; else stored behaviour/business
        eff_behaviour = userInstructions if userInstructions else instruction_store.get_behaviour(sessionId)
        eff_business = instruction_store.get_business(sessionId)
        result = await controller.run_turn(
            audio_bytes=data,
            filename=file.filename or "audio.wav",
            content_type=file.content_type or "audio/wav",
            language_code=language_code,
            stt_mode=stt_mode_eff,
            stt_model=stt_model_rt,
            session_id=sessionId,
            user_instructions=eff_behaviour,
            business_instructions=eff_business,
            tts_speaker=ttsSpeaker or rt.get("ttsSpeaker"),
            tts_model=rt.get("ttsModel"),
            tts_temperature=rt.get("ttsTemperature"),
            openai_model=rt.get("openaiModel"),
            openai_temperature=rt.get("openaiTemperature"),
            openai_max_tokens=rt.get("openaiMaxTokens"),
            synthesize_audio=True,
        )

        # Empty transcript → return gracefully without TTS
        if not result.transcript:
            return JSONResponse(
                content={
                    "transcript": "",
                    "brain_text": "",
                    "language_context": result.language_context,
                    "audio_base64": None,
                    "content_type": None,
                    "metrics": {"sttMs": result.stt_ms, "brainMs": result.brain_ms, "ttsMs": result.tts_ms, "e2eMs": result.e2e_ms},
                    "request_ids": result.request_ids,
                    "error": "empty_transcript",
                }
            )

        audio_b64 = base64.b64encode(result.audio_bytes).decode() if result.audio_bytes else None
        return {
            "transcript": result.transcript,
            "brain_text": result.brain_text,
            "language_context": result.language_context,
            "audio_base64": audio_b64,
            "content_type": "audio/wav" if audio_b64 else None,
            "metrics": {"sttMs": result.stt_ms, "brainMs": result.brain_ms, "ttsMs": result.tts_ms, "e2eMs": result.e2e_ms},
            "request_ids": result.request_ids,
            "usage": result.usage,
        }
    except AppError as e:
        log_error("Voice turn error", code=e.code.value, status=e.status_code)
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e
    except Exception as e:
        log_error("Voice turn unexpected", err=str(e)[:500])
        raise HTTPException(status_code=500, detail={"error": {"code": "provider_error", "message": "Voice turn failed"}}) from e


@router.post("/api/voice/stt-brain")
async def voice_stt_brain_only(
    file: UploadFile = File(...),
    language_code: str = Form("te-IN"),
    mode: str = Form("transcribe"),
    sessionId: str = Form("default"),
    userInstructions: str = Form(""),
    businessInstructions: str = Form(""),
):
    """Text-only turn (no TTS) — useful for low-latency testing / Phase 2 compatibility."""
    controller = VoiceSessionController()
    rt = _runtime(sessionId)
    try:
        data = await file.read()
        validate_audio_size(data, constants.MAX_AUDIO_BYTES)
        eff_behaviour2 = userInstructions if userInstructions else instruction_store.get_behaviour(sessionId)
        eff_business2 = instruction_store.get_business(sessionId)
        result = await controller.run_turn(
            audio_bytes=data,
            filename=file.filename or "audio.wav",
            content_type=file.content_type or "audio/wav",
            language_code=language_code,
            stt_mode=mode if mode != "transcribe" else rt.get("sttMode", "transcribe"),
            stt_model=rt.get("sttModel"),
            session_id=sessionId,
            user_instructions=eff_behaviour2,
            business_instructions=eff_business2,
            openai_model=rt.get("openaiModel"),
            openai_temperature=rt.get("openaiTemperature"),
            openai_max_tokens=rt.get("openaiMaxTokens"),
            synthesize_audio=False,
        )
        return {
            "transcript": result.transcript,
            "brain_text": result.brain_text,
            "language_context": result.language_context,
            "metrics": {"sttMs": result.stt_ms, "brainMs": result.brain_ms, "e2eMs": result.e2e_ms},
            "request_ids": result.request_ids,
            "usage": result.usage,
        }
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e
