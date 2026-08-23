"""
Brain route — server/routes/brain.py
POST /api/brain         {transcript, language_code, sessionId, userInstructions?, businessInstructions?}
POST /api/brain/stream  SSE variant
POST /api/brain/test    ephemeral test of dual-channel prompting without saving
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from server.agent.conversation_manager import conversation_manager
from server.agent.instruction_store import instruction_store
from server.services.openai_brain_service import generate_response, generate_response_stream
from server.services.runtime_settings import runtime_settings
from server.utils.errors import AppError
from server.utils.logger import log_error

router = APIRouter()


class BrainRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=5000, description="STT transcript")
    language_code: str = Field("te-IN")
    sessionId: str = Field("default", max_length=100)
    userInstructions: str | None = Field(None, max_length=10000, description="BEHAVIOUR: how to respond")
    businessInstructions: str | None = Field(None, max_length=10000, description="BUSINESS: client domain knowledge")
    responseStyle: str | None = Field(None, max_length=100)


class BrainTestRequest(BaseModel):
    userInstructions: str = Field("", max_length=10000)
    businessInstructions: str = Field("", max_length=10000)
    testInput: str = Field(..., min_length=1, max_length=2000)
    responseStyle: Optional[str] = Field(None, max_length=100)


async def _effective_prompting(session_id: str, user_instructions: str | None,
                               business_instructions: str | None, style: str | None):
    """Request value wins; else stored per-session values."""
    if user_instructions is None:
        user_instructions = instruction_store.get_behaviour(session_id)
    if business_instructions is None:
        business_instructions = instruction_store.get_business(session_id)
    if style is None:
        style = instruction_store.get_style(session_id)
    rt = {}
    try:
        rt = runtime_settings.get(session_id)
    except Exception:
        rt = {}
    return user_instructions or "", business_instructions or "", style, rt


@router.post("/api/brain")
async def brain_route(body: BrainRequest):
    transcript = body.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail={"error": {"code": "validation_error", "message": "transcript is required"}})

    eff_user, eff_business, eff_style, rt = await _effective_prompting(
        body.sessionId, body.userInstructions, body.businessInstructions, body.responseStyle)
    try:
        result = await generate_response(
            transcript=transcript,
            language_code=body.language_code,
            session_id=body.sessionId,
            user_instructions=eff_user,
            business_instructions=eff_business,
            response_style=eff_style,
            openai_model=rt.get("openaiModel"),
            temperature=rt.get("openaiTemperature"),
            max_output_tokens=rt.get("openaiMaxTokens"),
        )
        return result
    except AppError as e:
        log_error("Brain route error", code=e.code.value, status=e.status_code)
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e
    except Exception as e:
        log_error("Brain unexpected", err=str(e)[:500])
        raise HTTPException(status_code=500, detail={"error": {"code": "provider_error", "message": "Brain service failed"}}) from e


@router.post("/api/brain/test")
async def brain_test_route(body: BrainTestRequest):
    """Test dual-channel prompting without saving — ephemeral session."""
    try:
        result = await generate_response(
            transcript=body.testInput.strip(),
            language_code="te-IN",
            session_id=f"test-{id(body)}",
            user_instructions=body.userInstructions,
            business_instructions=body.businessInstructions,
            response_style=body.responseStyle,
        )
        return result
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e


@router.post("/api/brain/stream")
async def brain_stream_route(body: BrainRequest):
    """Streaming SSE — deltas forwarded by the client into the TTS socket for first-sentence audio."""
    transcript = body.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail={"error": {"code": "validation_error", "message": "transcript is required"}})

    eff_user, eff_business, eff_style, rt = await _effective_prompting(
        body.sessionId, body.userInstructions, body.businessInstructions, body.responseStyle)

    async def sse_gen():
        try:
            async for chunk in generate_response_stream(
                transcript=transcript,
                language_code=body.language_code,
                session_id=body.sessionId,
                user_instructions=eff_user,
                business_instructions=eff_business,
                response_style=eff_style,
                openai_model=rt.get("openaiModel"),
                temperature=rt.get("openaiTemperature"),
                max_output_tokens=rt.get("openaiMaxTokens"),
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except AppError as e:
            yield f"data: {json.dumps({'error': e.to_dict()}, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/session/clear")
async def clear_session(body: dict):
    session_id = body.get("sessionId", "default")
    conversation_manager.clear(session_id)
    return {"ok": True, "sessionId": session_id}
