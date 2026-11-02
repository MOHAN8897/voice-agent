"""
Voice Turn route — server/routes/voice.py
POST /api/voice/turn  → end-to-end: file (audio) → STT → Brain → TTS
Returns JSON with transcript, brain_text, audio (base64) + PERF metrics.
Streaming variant POST /api/voice/turn/stream would yield audio chunks (Phase 5).
"""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from server.auth.call_sessions import resolve_call_tenant, tenant_session_id
from server.auth.subscriber_dependencies import (
    SubscriberPrincipal,
    require_subscriber_jwt_if_enabled,
)
from server.config.constants import coerce_supported_language, constants
from server.config.env import get_settings
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


def _scope_voice_session(
    request: Request, principal: SubscriberPrincipal | None, session_id: str, overrides: tuple[str, ...]
) -> str:
    """A tenant's turn runs in its own session namespace, on its saved instructions."""
    if not get_settings().saas_auth_enabled:
        return session_id
    tenant_id = resolve_call_tenant(request, principal)
    if tenant_id is None:
        return session_id
    if any(str(value or "").strip() for value in overrides):
        raise HTTPException(status_code=403, detail="Call instructions are locked to the saved agent configuration")
    return tenant_session_id(tenant_id, session_id)


@router.post("/api/voice/turn")
async def voice_turn(
    request: Request,
    file: UploadFile = File(..., description="Audio WAV/MP3/WEBM ≤10MB"),
    language_code: str = Form("te-IN"),
    mode: str = Form("transcribe"),
    sessionId: str = Form("default", max_length=100),
    brainPrompt: str = Form(""),
    userInstructions: str = Form(""),
    businessInstructions: str = Form(""),
    ttsSpeaker: str = Form(""),
    _auth: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    sessionId = _scope_voice_session(request, _auth, sessionId, (brainPrompt, userInstructions, businessInstructions))
    controller = VoiceSessionController()
    rt = _runtime(sessionId)
    try:
        # Read one byte past the cap so an oversized upload is refused without buffering it all.
        data = await file.read(constants.MAX_AUDIO_BYTES + 1)
        validate_audio_size(data, constants.MAX_AUDIO_BYTES)
        language_code = coerce_supported_language(language_code)
        if mode not in ("transcribe", "translate", "verbatim", "translit", "codemix"):
            mode = "transcribe"

        # Prefer explicit param → runtime override (Fine-tune console) → env default
        stt_model_rt = rt.get("sttModel")
        stt_mode_eff = mode if mode != "transcribe" else rt.get("sttMode", "transcribe")
        # Dual-channel prompting: explicit form fields override; else use stored brain prompt
        brain_instr = brainPrompt.strip() if brainPrompt and brainPrompt.strip() else None
        user_instr = userInstructions if userInstructions else None
        biz_instr = businessInstructions if businessInstructions else None
        result = await controller.run_turn(
            audio_bytes=data,
            filename=file.filename or "audio.wav",
            content_type=file.content_type or "audio/wav",
            language_code=language_code,
            stt_mode=stt_mode_eff,
            stt_model=stt_model_rt,
            session_id=sessionId,
            brain_prompt=brain_instr,
            user_instructions=user_instr,
            business_instructions=biz_instr,
            tts_speaker=ttsSpeaker or rt.get("ttsSpeaker"),
            tts_model=rt.get("ttsModel"),
            tts_temperature=rt.get("ttsTemperature"),
            openai_model=rt.get("openaiModel"),
            openai_temperature=rt.get("openaiTemperature"),
            openai_reasoning_effort=rt.get("openaiReasoningEffort"),
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
