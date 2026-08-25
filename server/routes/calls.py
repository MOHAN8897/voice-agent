"""Call lifecycle HTTP routes — delegates to call_lifecycle_service."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from server.call.audio_archive import audio_archive
from server.call.call_ledger import call_ledger
from server.call.call_lifecycle_service import call_lifecycle_service
from server.call.call_store import call_store
from server.auth.tenant_context import tenant_id_from_request
from server.utils.errors import AppError

router = APIRouter()


class CallStartBody(BaseModel):
    agent_id: Optional[str] = Field(None, alias="agentId")
    session_id: Optional[str] = Field(None, alias="sessionId")
    channel: Literal["browser", "pstn"] = "browser"
    direction: Literal["inbound", "outbound"] = "inbound"
    campaign_id: Optional[str] = Field(None, alias="campaignId")
    environment: Optional[Literal["development", "staging", "production"]] = None
    tier: Optional[Literal["low", "medium", "premium"]] = None
    stack_override: Optional[dict] = Field(None, alias="stackOverride")
    caller_id: Optional[str] = Field(None, alias="callerId")
    language: str = "te-IN"

    model_config = ConfigDict(populate_by_name=True)


class CallEndBody(BaseModel):
    call_id: Optional[str] = Field(None, alias="callId")
    reason: str = "user_stop"

    model_config = ConfigDict(populate_by_name=True)


class MemoryCorrectionBody(BaseModel):
    operations: list[dict] = Field(..., min_length=1)
    reason: str = Field(..., min_length=3, max_length=200)
    actor: str = Field("operator", min_length=1, max_length=100)
    turn_seq: int = Field(0, ge=0)

    model_config = ConfigDict(populate_by_name=True)


def _raise(e: AppError) -> None:
    raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e


@router.post("/api/call/start")
async def call_start(body: CallStartBody):
    try:
        result = await call_lifecycle_service.start(
            agent_id=body.agent_id,
            session_id=body.session_id,
            channel=body.channel,
            direction=body.direction,
            campaign_id=body.campaign_id,
            environment=body.environment,
            tier=body.tier,
            stack_override=body.stack_override,
            caller_id=body.caller_id,
            language=body.language,
        )
        return result
    except AppError as e:
        _raise(e)


@router.post("/api/call/end", status_code=202)
async def call_end(body: CallEndBody):
    if not body.call_id:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "validation_error", "message": "call_id is required"}},
        )
    try:
        result = await call_lifecycle_service.end(body.call_id, reason=body.reason)
        return JSONResponse(status_code=202, content=result)
    except AppError as e:
        _raise(e)


@router.get("/api/call/{call_id}/finalization")
async def call_finalization(call_id: str):
    try:
        return await call_lifecycle_service.finalization(call_id)
    except AppError as e:
        _raise(e)


@router.get("/api/call/{call_id}")
async def get_call(call_id: str):
    try:
        return await call_lifecycle_service.get_call(call_id)
    except AppError as e:
        _raise(e)


@router.get("/api/calls")
async def list_calls(
    request: Request,
    agent_id: Optional[str] = Query(None, alias="agentId"),
    tenant_id: Optional[str] = Query(None, alias="tenantId"),
    disposition: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    scoped_tenant = tenant_id or tenant_id_from_request(request)
    items, total = await call_store.list_calls(
        tenant_id=scoped_tenant,
        agent_id=agent_id,
        disposition=disposition,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return {"calls": items, "total": total, "limit": limit, "offset": offset}


@router.get("/api/call/{call_id}/transcript")
async def get_transcript(call_id: str):
    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.meta_path(call_id).exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    return {"call_id": call_id, "lines": call_ledger.read_lines(call_id)}


@router.get("/api/call/{call_id}/trace")
async def get_trace(call_id: str):
    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.trace_path(call_id).exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    return call_ledger.read_trace(call_id)


@router.get("/api/call/{call_id}/audio/{kind}")
async def get_audio(call_id: str, kind: Literal["mix", "user", "agent"]):
    path = audio_archive.file_for(call_id, kind)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Audio not available"}},
        )
    media = {
        "mix": "audio/wav",
        "user": "application/octet-stream",
        "agent": "audio/mpeg" if path.suffix == ".mp3" else "application/octet-stream",
    }[kind]
    return FileResponse(path, media_type=media, filename=path.name)


@router.get("/api/call/{call_id}/audio")
async def get_audio_mix(call_id: str):
    return await get_audio(call_id, "mix")


@router.get("/api/call/{call_id}/memory")
async def get_memory(call_id: str):
    from server.call.memory_manager import memory_manager

    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.meta_path(call_id).exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    return {"call_id": call_id, "memory": memory_manager.get_snapshot(call_id)}


@router.get("/api/call/{call_id}/memory-events")
@router.get("/api/call/{call_id}/memory/events")
async def get_memory_events(call_id: str):
    from server.call.memory_manager import memory_manager

    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.meta_path(call_id).exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    return {"call_id": call_id, "events": memory_manager.list_events(call_id)}


@router.get("/api/call/{call_id}/memory/projection")
async def get_memory_projection(call_id: str, turn: int | None = Query(None)):
    from server.call.memory_manager import memory_manager
    from server.call.memory_projection import build as build_projection

    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.meta_path(call_id).exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    if turn is not None:
        recorded = memory_manager.projection_at_turn(call_id, turn)
        snap = memory_manager.snapshot_at_turn(call_id, turn)
        rolling = (snap.get("summary") or "").strip()
        rebuilt = build_projection(snap, include_summary=not rolling)
        return {
            "call_id": call_id,
            "turn": turn,
            "projection": recorded if recorded is not None else rebuilt,
            "memory": snap,
        }
    snap = memory_manager.get_snapshot(call_id)
    rolling = (snap.get("summary") or "").strip()
    return {
        "call_id": call_id,
        "projection": build_projection(snap, include_summary=not rolling),
        "memory": snap,
    }


@router.post("/api/call/{call_id}/memory/correction")
async def post_memory_correction(call_id: str, body: MemoryCorrectionBody):
    from server.call.memory_manager import memory_manager

    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.meta_path(call_id).exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    result = memory_manager.manual_correction(
        call_id,
        body.operations,
        actor=body.actor,
        reason=body.reason,
        turn_seq=body.turn_seq,
    )
    return {"ok": True, "call_id": call_id, "event": result["event"], "memory": result["snapshot"]}


@router.get("/api/call/{call_id}/outcome")
async def get_outcome(call_id: str):
    from server.call.post_call_pipeline import read_outcome

    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.meta_path(call_id).exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    outcome = read_outcome(call_id)
    if outcome is None:
        return JSONResponse(
            status_code=202,
            content={"call_id": call_id, "status": "pending", "outcome": None},
        )
    return {"call_id": call_id, "outcome": outcome}


@router.post("/api/call/{call_id}/outcome/retry", status_code=202)
async def retry_outcome(call_id: str):
    from server.call.call_context import get as get_ctx
    from server.call.call_lifecycle_service import status_url
    from server.call.post_call_pipeline import enqueue

    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.meta_path(call_id).exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    ctx = get_ctx(call_id)
    if ctx:
        ctx.components["outcome"] = "processing"
    await enqueue(call_id)
    return JSONResponse(
        status_code=202,
        content={
            "call_id": call_id,
            "status": "processing",
            "status_url": status_url(call_id),
        },
    )
