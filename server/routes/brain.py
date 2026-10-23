"""
Brain route — server/routes/brain.py
POST /api/brain         {transcript, language_code, sessionId, userInstructions?, businessInstructions?}
POST /api/brain/stream  SSE variant
POST /api/brain/test    ephemeral test of dual-channel prompting without saving
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.agent.conversation_manager import conversation_manager
from server.agent.session_memory import session_memory
from server.auth.call_sessions import CallPrincipal, resolve_call_tenant, tenant_session_id
from server.auth.subscriber_dependencies import SubscriberPrincipal
from server.call import call_context
from server.call.live_turn_orchestrator import live_turn_orchestrator
from server.config.env import get_settings
from server.services.openai_brain_service import generate_response
from server.services.runtime_settings import runtime_settings
from server.utils.errors import AppError
from server.utils.logger import log_error

router = APIRouter()


class BrainRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=5000, description="STT transcript")
    language_code: str = Field("te-IN")
    sessionId: str = Field("default", max_length=100)
    brainPrompt: str | None = Field(None, max_length=20000, description="Single brain prompt override")
    userInstructions: str | None = Field(None, max_length=10000, description="Legacy: behaviour channel")
    businessInstructions: str | None = Field(None, max_length=10000, description="Legacy: business channel")
    responseStyle: str | None = Field(None, max_length=100)
    callId: str | None = Field(None, max_length=64)
    sttLatencyMs: int | None = Field(None, ge=0, le=120000)


class BrainTestRequest(BaseModel):
    userInstructions: str = Field("", max_length=10000)
    businessInstructions: str = Field("", max_length=10000)
    testInput: str = Field(..., min_length=1, max_length=2000)
    responseStyle: Optional[str] = Field(None, max_length=100)


async def _runtime_settings(session_id: str) -> dict:
    try:
        return runtime_settings.get(session_id)
    except Exception:
        return {}


def _scoped_session(session_id: str, tenant_id: str):
    ctx = call_context.get_active_for_session(tenant_session_id(tenant_id, session_id))
    if ctx is None:
        ctx = call_context.get_active_for_session(session_id)
    return ctx if ctx and str(ctx.tenant_id) == tenant_id else None


def _scope_turn(body: BrainRequest, request: Request, principal: SubscriberPrincipal | None) -> None:
    """A tenant's HTTP turn can only use its own active, admitted call."""
    if not get_settings().saas_auth_enabled:
        return
    tenant_id = resolve_call_tenant(request, principal)
    if tenant_id is None:
        return
    ctx = call_context.get(body.callId) if body.callId else _scoped_session(body.sessionId, tenant_id)
    if ctx is None or str(ctx.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Call not found")
    if ctx.status != "active":
        raise HTTPException(status_code=409, detail="This call is no longer active")
    if any((body.brainPrompt, body.userInstructions, body.businessInstructions, body.responseStyle)):
        raise HTTPException(status_code=403, detail="Call instructions are locked to the saved agent configuration")
    body.callId = ctx.call_id
    body.sessionId = ctx.session_id
    body.language_code = ctx.resolved_stack.language


@router.post("/api/brain")
async def brain_route(body: BrainRequest, request: Request, _auth: CallPrincipal = None):
    _scope_turn(body, request, _auth)
    transcript = body.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail={"error": {"code": "validation_error", "message": "transcript is required"}})

    rt = await _runtime_settings(body.sessionId)
    try:
        result = await live_turn_orchestrator.handle_user_turn(
            transcript=transcript,
            language_code=body.language_code,
            session_id=body.sessionId,
            call_id=body.callId,
            user_instructions=body.userInstructions,
            business_instructions=body.businessInstructions,
            response_style=body.responseStyle,
            brain_prompt=body.brainPrompt,
            openai_model=rt.get("openaiModel"),
            temperature=rt.get("openaiTemperature"),
            reasoning_effort=rt.get("openaiReasoningEffort"),
            max_output_tokens=rt.get("openaiMaxTokens"),
            stt_latency_ms=body.sttLatencyMs,
        )
        return result
    except AppError as e:
        log_error("Brain route error", code=e.code.value, status=e.status_code)
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e
    except Exception as e:
        log_error("Brain unexpected", error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail={"error": {"code": "provider_error", "message": "Brain service failed"}}) from e


@router.post("/api/brain/test")
async def brain_test_route(body: BrainTestRequest, request: Request, _auth: CallPrincipal = None):
    """Test dual-channel prompting without saving — ephemeral session."""
    from server.services.saas.call_redaction import is_internal_viewer

    if get_settings().saas_auth_enabled:
        tenant_id = resolve_call_tenant(request, _auth)
        if tenant_id is not None and (_auth is None or not is_internal_viewer(_auth.role)):
            raise HTTPException(status_code=403, detail="Use an agent test call for this workspace")
    session_id = f"test-{uuid.uuid4().hex}"
    try:
        result = await generate_response(
            transcript=body.testInput.strip(),
            language_code="te-IN",
            session_id=session_id,
            user_instructions=body.userInstructions,
            business_instructions=body.businessInstructions,
            response_style=body.responseStyle,
        )
        return result
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e
    finally:
        conversation_manager.clear(session_id)
        session_memory.clear(session_id)


@router.post("/api/brain/stream")
async def brain_stream_route(body: BrainRequest, request: Request, _auth: CallPrincipal = None):
    """Streaming SSE — deltas forwarded by the client into the TTS socket for first-sentence audio."""
    _scope_turn(body, request, _auth)
    transcript = body.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail={"error": {"code": "validation_error", "message": "transcript is required"}})

    rt = await _runtime_settings(body.sessionId)

    async def sse_gen():
        try:
            async for chunk in live_turn_orchestrator.handle_user_turn_stream(
                transcript=transcript,
                language_code=body.language_code,
                session_id=body.sessionId,
                call_id=body.callId,
                user_instructions=body.userInstructions,
                business_instructions=body.businessInstructions,
                response_style=body.responseStyle,
                brain_prompt=body.brainPrompt,
                openai_model=rt.get("openaiModel"),
                temperature=rt.get("openaiTemperature"),
                reasoning_effort=rt.get("openaiReasoningEffort"),
                max_output_tokens=rt.get("openaiMaxTokens"),
                stt_latency_ms=body.sttLatencyMs,
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except AppError as e:
            yield f"data: {json.dumps({'error': e.to_dict()}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            log_error("Brain stream failed", error_type=type(exc).__name__)
            yield f"data: {json.dumps({'error': {'code': 'provider_error', 'message': 'The selected service could not complete the reply.', 'retryable': False}})}\n\n"

    return StreamingResponse(sse_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/session/clear")
async def clear_session(body: dict, request: Request, _auth: CallPrincipal = None):
    session_id = body.get("sessionId", "default")
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid session")
    ctx = call_context.get_active_for_session(session_id)
    if get_settings().saas_auth_enabled:
        tenant_id = resolve_call_tenant(request, _auth)
        if tenant_id is not None:
            ctx = _scoped_session(session_id, tenant_id)
            if ctx is None:
                raise HTTPException(status_code=404, detail="Call not found")
            session_id = ctx.session_id
    from server.call.call_lifecycle_service import call_lifecycle_service

    if ctx:
        try:
            await call_lifecycle_service.end(ctx.call_id, reason="user_stop")
        except Exception as exc:
            log_error("Session stop failed", error_type=type(exc).__name__)
            raise HTTPException(status_code=503, detail="The call could not be stopped. Please try again.") from exc
    conversation_manager.clear(session_id)
    session_memory.clear(session_id)
    return {"ok": True, "sessionId": session_id}
