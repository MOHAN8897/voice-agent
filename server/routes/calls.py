"""Call lifecycle HTTP routes — delegates to call_lifecycle_service."""
from __future__ import annotations

import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from server.call.audio_archive import audio_archive
from server.call.call_ledger import call_ledger
from server.call.call_lifecycle_service import call_lifecycle_service
from server.call.call_status import CALL_STATUSES
from server.call.call_store import call_store
from server.call.call_timeline import list_timeline, timeline_stats
from server.auth.calls_tenant import (
    resolve_calls_scope,
    resolve_calls_tenant_id,
    resolve_prompt_preview_tenant_id,
)
from server.services.saas.call_redaction import redact_call_detail_for_tenant
from server.auth.tenant_context import tenant_id_from_request
from server.config.env import get_settings
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


@router.get("/api/call/{call_id}/prompt-preview")
async def call_prompt_preview(
    call_id: str,
    redacted: bool = Query(False),
    scoped_tenant: str | None = Depends(resolve_prompt_preview_tenant_id),
):
    """Actual model instructions for this call (locked brain + live session rules)."""
    from server.call.call_prompt_preview import get_call_prompt_preview

    settings = get_settings()
    if settings.saas_auth_enabled and scoped_tenant is not None:
        stored = await call_store.get(call_id)
        tenant = str((stored or {}).get("tenant_id") or "")
        if not tenant or tenant != scoped_tenant:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": "Call not found"}},
            )
    try:
        preview = await get_call_prompt_preview(call_id, redacted=redacted)
    except AppError as e:
        _raise(e)
    return JSONResponse(preview, headers={"Cache-Control": "private, no-store", "Vary": "Cookie, Authorization"})


@router.get("/api/call/{call_id}")
async def get_call(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    scoped_tenant, internal_viewer = scope
    try:
        result = await call_lifecycle_service.get_call(call_id)
    except AppError as e:
        _raise(e)
    settings = get_settings()
    if settings.saas_auth_enabled:
        if str(result.get("tenant_id") or "") != scoped_tenant:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": "Call not found"}},
            )
    if internal_viewer:
        return result
    # Wholesale carrier cost, upstream model list rates, the resolved provider stack
    # and PSTN forensics stay on the platform side. Redacted on the response, not in
    # the UI — a field hidden in React is still on the wire.
    return redact_call_detail_for_tenant(result)


@router.get("/api/calls")
async def list_calls(
    agent_id: Optional[str] = Query(None, alias="agentId"),
    disposition: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = Query(None, description="Canonical status filter; comma-separated for several"),
    direction: Optional[str] = Query(None, description="inbound | outbound"),
    include_attempts: bool = Query(True, description="Include never-answered ringing attempts"),
    include_tests: bool = Query(
        False, description="Include browser practice sessions (not real calls)"
    ),
    scoped_tenant: str = Depends(resolve_calls_tenant_id),
):
    """One ordered call history, including calls that never connected.

    ``status`` uses the canonical vocabulary in ``server/call/call_status.py``.
    Connected calls are enriched exactly as before; ringing attempts carry the same
    envelope so the console renders both from a single list.
    """
    from server.call.call_status import normalize_call_statuses

    items, total = await list_timeline(
        tenant_id=scoped_tenant,
        agent_id=agent_id,
        statuses=normalize_call_statuses(status),
        direction=direction,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
        include_attempts=include_attempts,
        include_tests=include_tests,
    )
    enriched = [_enrich_timeline_item(item) for item in items]
    return {
        "calls": enriched,
        "total": total,
        "limit": limit,
        "offset": offset,
        "statuses": list(CALL_STATUSES),
    }


@router.get("/api/calls/stats")
async def calls_stats(
    agent_id: Optional[str] = Query(None, alias="agentId"),
    since: Optional[str] = None,
    until: Optional[str] = None,
    include_attempts: bool = Query(True),
    scoped_tenant: str = Depends(resolve_calls_tenant_id),
):
    """Counts and totals for the call history header."""
    return await timeline_stats(
        tenant_id=scoped_tenant,
        agent_id=agent_id,
        since=since,
        until=until,
    )


_ENRICH_CALL_CACHE: dict[str, dict] = {}
_CACHE_MAX_ENTRIES = 2000


def _enrich_timeline_item(item: dict) -> dict:
    """Attach summary, cost and recording flags to a timeline row."""
    if not item.get("connected"):
        # A ringing attempt has no ledger, no outcome and no recording.
        return item
    enriched = _enrich_call_list_item(
        {
            "call_id": item.get("call_id"),
            "direction": item.get("direction"),
            "disposition": item.get("disposition"),
            "duration_sec": item.get("duration_sec"),
            "summary": item.get("summary"),
            "has_recording": item.get("has_recording"),
            "in_progress": item.get("in_progress"),
        }
    )
    out = dict(item)
    for key in ("summary", "customer", "usage", "cost_usd", "cost_inr", "cost_inr_per_min", "pipeline", "has_recording", "recording_source", "has_telnyx_recording"):
        if key in enriched:
            out[key] = enriched[key]
    if out.get("summary"):
        out["has_transcript"] = True
    return out


def _enrich_call_list_item(item: dict) -> dict:
    """Attach outcome summary, customer label, pipeline, and session cost with memory caching."""
    cid = str(item.get("call_id") or "")
    if not cid:
        return dict(item)

    is_in_progress = bool(item.get("in_progress"))
    if not is_in_progress and cid in _ENRICH_CALL_CACHE:
        cached = dict(_ENRICH_CALL_CACHE[cid])
        cached.update({k: v for k, v in item.items() if v is not None})
        return cached

    out = dict(item)
    # chisel: if summary is already present, avoid outcome disk read
    if not out.get("summary"):
        from server.call.post_call_pipeline import read_outcome

        outcome = read_outcome(cid)
        if outcome:
            summary = (outcome.get("summary_en") or "").strip()
            if summary:
                out["summary"] = summary[:240]
            from server.call.outcome_schema import normalize_extracted_fields

            fields = normalize_extracted_fields(outcome.get("extracted_fields"))
            customer = (fields.get("name") or fields.get("phone") or "").strip()
            if customer:
                out["customer"] = customer

    review = call_ledger.review_fields(cid)
    if review.get("usage"):
        out["usage"] = review["usage"]
    for key in ("cost_usd", "cost_inr", "cost_inr_per_min", "pipeline"):
        if review.get(key) is not None:
            out[key] = review[key]
    source = audio_archive.recording_source(cid)
    out["has_recording"] = source != "none"
    out["recording_source"] = source
    out["has_telnyx_recording"] = source == "telnyx"

    if not is_in_progress:
        if len(_ENRICH_CALL_CACHE) >= _CACHE_MAX_ENTRIES:
            keys_to_remove = list(_ENRICH_CALL_CACHE.keys())[:200]
            for k in keys_to_remove:
                _ENRICH_CALL_CACHE.pop(k, None)
        _ENRICH_CALL_CACHE[cid] = out

    return out


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


@router.get("/api/call/{call_id}/audio-status")
async def get_audio_status(call_id: str):
    await asyncio.to_thread(audio_archive.ensure_telnyx_review, call_id)
    path = audio_archive.file_for(call_id, "mix_clear")
    source = audio_archive.recording_source(call_id)
    return {
        "call_id": call_id,
        "source": source,
        "ready": path is not None,
        "telnyx_ready": source == "telnyx",
        "file": path.name if path else None,
    }


@router.api_route("/api/call/{call_id}/audio/{kind}", methods=["GET", "HEAD"])
async def get_audio(
    call_id: str,
    kind: Literal["mix", "user", "agent", "mix_clear", "user_clear", "agent_clear"],
    download: bool = Query(False, alias="download"),
):
    if kind in ("mix", "mix_clear"):
        await asyncio.to_thread(audio_archive.ensure_telnyx_review, call_id)
    if kind.endswith("_clear"):
        await asyncio.to_thread(audio_archive.refresh_clear_tracks, call_id)
    path = audio_archive.file_for(call_id, kind)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Audio not available"}},
        )
    serve_path = path
    suffix = path.suffix.lower()
    if download and kind in ("mix", "mix_clear"):
        telnyx_mp3 = audio_archive.telnyx_mp3_path(call_id)
        if telnyx_mp3.is_file() and telnyx_mp3.stat().st_size > 0:
            serve_path = telnyx_mp3
            suffix = ".mp3"
        elif suffix == ".wav":
            mp3 = await asyncio.to_thread(audio_archive.ensure_conversation_mp3, call_id, path)
            if mp3 is not None:
                serve_path = mp3
                suffix = ".mp3"
    media = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
    }.get(suffix, "application/octet-stream")
    source = "telnyx" if path.name.startswith("telnyx") else "local"
    headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
        "X-Recording-Source": source,
        "Access-Control-Expose-Headers": "X-Recording-Source",
        "X-Audio-Encoding": suffix.lstrip("."),
    }
    stem = "conversation" if path.name.startswith("telnyx") else kind
    download_name = f"{call_id}-{stem}{suffix}"
    return FileResponse(
        serve_path,
        media_type=media,
        filename=download_name if download else None,
        headers=headers,
        content_disposition_type="attachment" if download else "inline",
    )


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
    await enqueue(call_id, force=True)
    return JSONResponse(
        status_code=202,
        content={
            "call_id": call_id,
            "status": "processing",
            "status_url": status_url(call_id),
        },
    )
