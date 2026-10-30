"""Call lifecycle HTTP routes — delegates to call_lifecycle_service."""
from __future__ import annotations

import asyncio
import re
from typing import Any, Literal, Optional

import csv
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

_CALL_ID_SAFE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")


def _validate_call_id(call_id: str) -> str:
    cid = (call_id or "").strip()
    if not cid or not _CALL_ID_SAFE.match(cid) or ".." in cid:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "validation_error", "message": "Invalid call_id format"}},
        )
    return cid

from server.call.audio_archive import audio_archive
from server.call.paths import call_dir
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
from server.auth.call_sessions import CallPrincipal, resolve_call_tenant, tenant_session_id
from server.auth.subscriber_dependencies import (
    SubscriberPrincipal,
)
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.integration_models import TenantIntegration
from server.services.nango_service import nango_service
from server.utils.errors import AppError
from server.utils.logger import logger

router = APIRouter()


def _safe_tenant_uuid(raw_id: str | None) -> uuid.UUID:
    """Safely convert any raw tenant identifier into a deterministic UUID."""
    if not raw_id:
        return uuid.NAMESPACE_DNS
    try:
        return uuid.UUID(str(raw_id))
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, f"tenant:{raw_id}")


class CallStartBody(BaseModel):
    agent_id: Optional[str] = Field(None, alias="agentId")
    session_id: Optional[str] = Field(None, alias="sessionId")
    channel: Literal["browser", "pstn"] = "browser"
    direction: Literal["inbound", "outbound"] = "inbound"
    campaign_id: Optional[str] = Field(None, alias="campaignId")
    environment: Optional[Literal["development", "staging", "production"]] = None
    tier: Optional[str] = Field(None, pattern=r"^[a-z0-9_]{1,20}$")
    stack_override: Optional[dict] = Field(None, alias="stackOverride")
    caller_id: Optional[str] = Field(None, alias="callerId")
    language: Optional[str] = None

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


class CrmSyncBody(BaseModel):
    destination: Optional[str] = None
    notes: Optional[str] = None
    override_contact: Optional[dict[str, str]] = None

    model_config = ConfigDict(populate_by_name=True)


def _raise(e: AppError) -> None:
    raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e


@router.post("/api/call/start")
async def call_start(
    body: CallStartBody,
    request: Request,
    _auth: CallPrincipal = None,
):
    try:
        if isinstance(body.stack_override, dict) and "_voice_stack_snapshot" in body.stack_override:
            raise HTTPException(status_code=400, detail="Voice profile snapshots are managed by the server.")
        if body.language:
            from server.config.constants import normalize_supported_language

            # Retired codes ("en-GB") must resolve before the stack resolver sees them.
            body.language = normalize_supported_language(body.language)
        # The browser call endpoint is tenant-facing. Resolve the workspace from
        # the verified bearer/session context; never accept it from the request body.
        tenant_id = resolve_call_tenant(request, _auth) if get_settings().saas_auth_enabled else None
        if tenant_id is not None:
            from server.services.saas.pstn_saas_stack import saas_stack_override_for_agent
            from server.services.saas.voice_stack_profiles import VoiceProfileError, canonical_voice_tier
            from server.services.dev_runtime import effective_app_environment

            if body.stack_override:
                raise HTTPException(status_code=403, detail="Voice profiles are managed by the server.")
            agent = await call_lifecycle_service._resolve_agent(body.agent_id, tenant_id=tenant_id)
            try:
                saved_tier = canonical_voice_tier(agent.get("default_tier") or agent.get("defaultTier") or "medium")
            except VoiceProfileError as exc:
                raise HTTPException(status_code=409, detail="The saved agent tier is unavailable.") from exc
            saved_environment = agent.get("environment") or effective_app_environment()
            if body.tier and canonical_voice_tier(body.tier) != saved_tier:
                raise HTTPException(status_code=409, detail="The requested tier does not match the saved agent.")
            if body.environment and body.environment != saved_environment:
                raise HTTPException(status_code=409, detail="The requested environment does not match the saved agent.")
            if body.language:
                requested_language = body.language
                languages = agent.get("languages") or [agent.get("language") or "te-IN"]
                if requested_language not in languages:
                    raise HTTPException(status_code=409, detail="Choose a language configured for this agent.")
                agent = {**agent, "languages": [
                    requested_language, *[code for code in languages if code != requested_language],
                ]}
            try:
                body.stack_override = await saas_stack_override_for_agent(agent)
            except VoiceProfileError as exc:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
            body.session_id = tenant_session_id(tenant_id, body.session_id)
            body.tier = saved_tier
            body.environment = saved_environment
        result = await call_lifecycle_service.start(
            agent_id=body.agent_id,
            tenant_id=tenant_id,
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
async def call_end(
    body: CallEndBody,
    request: Request,
    _auth: CallPrincipal = None,
):
    if not body.call_id:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "validation_error", "message": "call_id is required"}},
        )
    _validate_call_id(body.call_id)
    await _require_call_scope(body.call_id, request, _auth)
    try:
        result = await call_lifecycle_service.end(body.call_id, reason=body.reason)
        return JSONResponse(status_code=202, content=result)
    except AppError as e:
        _raise(e)


@router.get("/api/call/{call_id}/finalization")
async def call_finalization(call_id: str, request: Request,
    _auth: CallPrincipal = None):
    _validate_call_id(call_id)
    await _require_call_scope(call_id, request, _auth)
    try:
        return await call_lifecycle_service.finalization(call_id)
    except AppError as e:
        _raise(e)


async def _require_call_scope(call_id: str, request: Request, principal: SubscriberPrincipal | None) -> None:
    if not get_settings().saas_auth_enabled:
        return
    tenant_id = resolve_call_tenant(request, principal)
    if tenant_id is None:
        return
    from server.call import call_context

    ctx = call_context.get(call_id)
    owner = str(ctx.tenant_id) if ctx else str((await call_store.get(call_id) or {}).get("tenant_id") or "")
    if owner != tenant_id:
        raise HTTPException(status_code=404, detail="Call not found")


@router.get("/api/call/{call_id}/prompt-preview")
async def call_prompt_preview(
    call_id: str,
    redacted: bool = Query(False),
    scoped_tenant: str | None = Depends(resolve_prompt_preview_tenant_id),
):
    """Actual model instructions for this call (locked brain + live session rules)."""
    _validate_call_id(call_id)
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
    tags: Optional[str] = Query(
        None, description="Comma-separated tag filter, e.g. intent:pricing,followup:callback"
    ),
    tag_match: Literal["any", "all"] = Query("any", description="Match any or all requested tags"),
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
        tags=[tag for tag in (tags or "").split(",") if tag.strip()],
        tag_match=tag_match,
    )
    # Ledger/outcome enrichment reads local files; keep it off the event loop.
    enriched = await asyncio.to_thread(lambda: [_enrich_timeline_item(item) for item in items])
    await _attach_tenant_wallet_charges(enriched, scoped_tenant)
    return {
        "calls": enriched,
        "total": total,
        "limit": limit,
        "offset": offset,
        "statuses": list(CALL_STATUSES),
    }


async def _attach_tenant_wallet_charges(items: list[dict[str, Any]], tenant_id: str) -> None:
    """Attach the tenant's actual wallet debits, scoped to the authenticated tenant."""
    call_ids = [
        str(item.get("call_id"))
        for item in items
        if item.get("connected") and item.get("call_id")
    ]
    if not call_ids:
        return
    try:
        tenant_uuid = uuid.UUID(str(tenant_id))
    except (ValueError, TypeError, AttributeError):
        return
    factory = get_session_factory()
    if factory is None:
        return
    from server.db.models.saas_models import BillingWallet, BillingWalletTransaction
    from server.services.saas.billing_wallet_service import wallet_debit_display

    try:
        fx_by_call: dict[str, float] = {}
        async with factory() as session:
            result = await session.execute(
                select(BillingWalletTransaction).where(
                    BillingWalletTransaction.tenant_id == tenant_uuid,
                    BillingWalletTransaction.reference_id.in_([f"call:{cid}" for cid in call_ids]),
                )
            )
            transactions = result.scalars().all()
            wallet = await session.get(BillingWallet, tenant_uuid)
            mixed_call_ids = {
                str(tx.reference_id)[len("call:"):]
                for tx in transactions
                if str(tx.reference_id or "").startswith("call:")
                and int(tx.amount_cents or 0) != 0
                and int(tx.amount_inr_paise or 0) != 0
            }
            call_uuids = []
            for call_id in mixed_call_ids:
                try:
                    call_uuids.append(uuid.UUID(call_id))
                except (ValueError, TypeError, AttributeError):
                    continue
            if call_uuids:
                from server.db.models.entities import Call

                calls_result = await session.execute(
                    select(Call).where(
                        Call.tenant_id == tenant_uuid,
                        Call.call_id.in_(call_uuids),
                    )
                )
                fx_by_call = {
                    str(call.call_id): float(call.applied_fx_rate_inr)
                    for call in calls_result.scalars().all()
                    if call.applied_fx_rate_inr is not None
                    and float(call.applied_fx_rate_inr) > 0
                }
    except Exception as exc:
        logger.warning("[CALLS] Could not load tenant call charges (%s)", type(exc).__name__)
        return

    by_call = {
        str(tx.reference_id)[len("call:"):]: tx
        for tx in transactions
        if str(tx.reference_id or "").startswith("call:")
    }
    for item in items:
        tx = by_call.get(str(item.get("call_id") or ""))
        if tx is None:
            item["tenant_charge"] = None
            continue
        item["tenant_charge"] = wallet_debit_display(
            amount_cents=tx.amount_cents,
            amount_inr_paise=tx.amount_inr_paise,
            wallet_currency=getattr(wallet, "currency", "usd"),
            fx_rate_inr=fx_by_call.get(str(item.get("call_id"))) or get_settings().fx_rate_inr,
        )


@router.get("/api/calls/tags")
async def calls_tags(
    agent_id: Optional[str] = Query(None, alias="agentId"),
    scoped_tenant: str = Depends(resolve_calls_tenant_id),
):
    """Tags present in this tenant's history, with counts, for the filter menu."""
    return {"tags": await call_store.list_tags(tenant_id=scoped_tenant, agent_id=agent_id)}


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
        include_attempts=include_attempts,
    )


_ENRICH_CALL_CACHE: dict[str, dict] = {}
_CACHE_MAX_ENTRIES = 2000
#: Ledger contact fields keyed by call, invalidated by the meta file's mtime, so the
#: list poll stats the file instead of re-parsing its JSON for every row.
_CONTACT_CACHE: dict[str, tuple[int, tuple[str, Any, Any]]] = {}
#: Call-folder mtime seen when a finished call had no recording. Carrier recordings
#: arrive after finalization and land in that folder, so "none" is re-probed only
#: when the folder changed (one stat instead of six file probes per row).
_RECORDING_CHECKED_AT: dict[str, int] = {}


def _call_dir_mtime(call_id: str) -> int:
    try:
        return call_dir(call_id).stat().st_mtime_ns
    except OSError:
        return 0


def _ledger_contact(cid: str) -> tuple[str, Any, Any]:
    """(ledger tenant, caller, callee) for a call; re-read only when its meta changes."""
    try:
        mtime = call_ledger.meta_path(cid).stat().st_mtime_ns
    except (OSError, ValueError):
        mtime = None
    cached = _CONTACT_CACHE.get(cid)
    if mtime is not None and cached is not None and cached[0] == mtime:
        return cached[1]
    meta = call_ledger.read_meta(cid) or {}
    contact = (
        str(meta.get("tenant_id") or ""),
        meta.get("caller_id") or meta.get("from_number"),
        meta.get("callee_e164") or meta.get("to_number"),
    )
    if mtime is not None:
        if len(_CONTACT_CACHE) >= _CACHE_MAX_ENTRIES:
            for k in list(_CONTACT_CACHE.keys())[:200]:
                _CONTACT_CACHE.pop(k, None)
        _CONTACT_CACHE[cid] = (mtime, contact)
    return contact


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
    ledger_tenant, caller, callee = _ledger_contact(str(item.get("call_id") or ""))
    # Only copy contact fields from a ledger belonging to the indexed tenant.
    # Attempts already carry their numbers; connected rows previously lost both.
    if ledger_tenant == str(item.get("tenant_id") or "") and item.get("tenant_id"):
        out["caller_phone"] = caller or out.get("caller_phone")
        out["called_phone"] = callee or out.get("called_phone")
    for key in ("summary", "customer", "pipeline", "has_recording"):
        if key in enriched:
            out[key] = enriched[key]
    # Wholesale supplier and model costs stay in the admin reporting surfaces.
    # A tenant call row only receives its exact wallet charge from the ledger.
    for key in (
        "usage", "cost_usd", "cost_inr", "cost_usd_per_min", "cost_inr_per_min",
        "model_cost_usd", "model_cost_inr", "model_cost_inr_per_min",
        "telnyx_usd", "telnyx_inr", "telnyx_inr_per_min", "telnyx_cost_source",
        "vobiz_usd", "vobiz_inr", "vobiz_inr_per_min", "vobiz_voice_inr",
        "vobiz_recording_inr", "vobiz_transcription_inr", "vobiz_rate_inr_per_min",
        "telephony_provider", "telephony_usd", "telephony_inr", "telephony_usd_per_min",
        "telephony_inr_per_min", "gemini_38_live_cost_usd", "gemini_38_live_cost_inr",
        "recording_source", "has_telnyx_recording",
    ):
        out.pop(key, None)
    if out.get("summary"):
        out["has_transcript"] = True
    return out


def _integration_fields(cid: str) -> dict[str, Any]:
    """Integrations attached at launch (single call) or the owning campaign id."""
    try:
        meta = call_ledger.read_meta(cid) or {}
    except (OSError, ValueError):
        return {}
    contact = meta.get("contact") if isinstance(meta.get("contact"), dict) else {}
    campaign_id = contact.get("campaign_id") or meta.get("campaign_id")
    fields: dict[str, Any] = {}
    if campaign_id:
        # Campaign calls inherit the campaign's set; the console reads it there.
        fields["campaign_id"] = str(campaign_id)
    else:
        selection = contact.get("integration_selection")
        if isinstance(selection, list):
            fields["integration_selection"] = [
                {"app": str(i.get("app")), "mode": str(i.get("mode"))} for i in selection if isinstance(i, dict)
            ][:12]
    return fields


def _enrich_call_list_item(item: dict) -> dict:
    """Attach outcome summary, customer label, pipeline, and session cost with memory caching."""
    cid = str(item.get("call_id") or "")
    if not cid:
        return dict(item)

    is_in_progress = bool(item.get("in_progress"))
    if not is_in_progress and cid in _ENRICH_CALL_CACHE:
        cached = dict(_ENRICH_CALL_CACHE[cid])
        cached.update({k: v for k, v in item.items() if v is not None})
        # Carrier recordings arrive after finalization. Cached call summaries
        # must not hide a recording that became available in the meantime, but a
        # found recording does not disappear, so only "none" is re-probed.
        if _ENRICH_CALL_CACHE[cid].get("recording_source", "none") == "none" and (
            (mtime := _call_dir_mtime(cid)) != _RECORDING_CHECKED_AT.get(cid)
        ):
            source = audio_archive.recording_source(cid)
            _RECORDING_CHECKED_AT[cid] = mtime
            _ENRICH_CALL_CACHE[cid].update(
                has_recording=source != "none", recording_source=source,
                has_telnyx_recording=source == "telnyx",
            )
        entry = _ENRICH_CALL_CACHE[cid]
        cached.update(has_recording=entry.get("has_recording", False),
                      recording_source=entry.get("recording_source", "none"),
                      has_telnyx_recording=entry.get("has_telnyx_recording", False))
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
    for key in (
        "cost_usd",
        "cost_inr",
        "cost_usd_per_min",
        "cost_inr_per_min",
        "model_cost_usd",
        "model_cost_inr",
        "model_cost_inr_per_min",
        "telnyx_usd",
        "telnyx_inr",
        "telnyx_inr_per_min",
        "telnyx_cost_source",
        "vobiz_usd",
        "vobiz_inr",
        "vobiz_inr_per_min",
        "vobiz_voice_inr",
        "vobiz_recording_inr",
        "vobiz_transcription_inr",
        "vobiz_rate_inr_per_min",
        "telephony_provider",
        "telephony_usd",
        "telephony_inr",
        "telephony_usd_per_min",
        "telephony_inr_per_min",
        "gemini_38_live_cost_usd",
        "gemini_38_live_cost_inr",
        "pipeline",
    ):
        if review.get(key) is not None:
            out[key] = review[key]
    source = audio_archive.recording_source(cid)
    out["has_recording"] = source != "none"
    out["recording_source"] = source
    out["has_telnyx_recording"] = source == "telnyx"
    out.update(_integration_fields(cid))

    if not is_in_progress:
        if len(_ENRICH_CALL_CACHE) >= _CACHE_MAX_ENTRIES:
            keys_to_remove = list(_ENRICH_CALL_CACHE.keys())[:200]
            for k in keys_to_remove:
                _ENRICH_CALL_CACHE.pop(k, None)
                _RECORDING_CHECKED_AT.pop(k, None)
        _ENRICH_CALL_CACHE[cid] = out
        _RECORDING_CHECKED_AT[cid] = _call_dir_mtime(cid)

    return out


async def _assert_call_scoped(
    call_id: str, scope: tuple[str, bool], meta: dict | None = None
) -> dict:
    """``meta``: the ledger meta when the caller already read it, so it is read once."""
    _validate_call_id(call_id)
    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.meta_path(call_id).exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    settings = get_settings()
    if settings.saas_auth_enabled:
        scoped_tenant, _ = scope
        tenant = str((stored or {}).get("tenant_id") or "")
        if not tenant:
            if meta is None:
                meta = call_ledger.read_meta(call_id) or {}
            tenant = str(meta.get("tenant_id") or "")
        if not tenant or tenant != scoped_tenant:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "not_found", "message": "Call not found"}},
            )
    return stored or {}


@router.get("/api/call/{call_id}/transcript")
async def get_transcript(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    _validate_call_id(call_id)
    meta = call_ledger.read_meta(call_id) or {}
    await _assert_call_scoped(call_id, scope, meta=meta)
    from server.services.saas.call_redaction import tenant_live_transcription
    return {"call_id": call_id, "lines": call_ledger.read_lines(call_id),
            "transcription": tenant_live_transcription(meta)}


@router.get("/api/call/{call_id}/trace")
async def get_trace(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    await _assert_call_scoped(call_id, scope)
    return call_ledger.read_trace(call_id)


@router.get("/api/call/{call_id}/audio-status")
async def get_audio_status(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    await _assert_call_scoped(call_id, scope)
    meta = call_ledger.read_meta(call_id)
    if meta.get("vobiz_call_uuid") and meta.get("ended_at"):
        from server.services.vobiz_recordings import schedule_recording_retrieval
        schedule_recording_retrieval(call_id)
    await asyncio.to_thread(audio_archive.ensure_telnyx_review, call_id)
    path = audio_archive.file_for(call_id, "mix_clear")
    if path and path.suffix.lower() == ".wav":
        mp4_path = await asyncio.to_thread(audio_archive.ensure_conversation_mp4, call_id, path)
        if mp4_path:
            path = mp4_path
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
    scope: tuple[str, bool] = Depends(resolve_calls_scope),
):
    await _assert_call_scoped(call_id, scope)
    if kind in ("mix", "mix_clear"):
        await asyncio.to_thread(audio_archive.ensure_telnyx_review, call_id)
    if kind.endswith("_clear"):
        await asyncio.to_thread(audio_archive.refresh_clear_tracks, call_id)
    path = audio_archive.file_for(call_id, kind)
    if path is None:
        from server.services.r2_storage import r2_storage
        if r2_storage.is_configured():
            for ext in ("mp4", "mp3", "wav"):
                presigned = await r2_storage.presigned_url(f"calls/{call_id}/recording.{ext}")
                if presigned:
                    from fastapi.responses import RedirectResponse
                    return RedirectResponse(presigned, status_code=307)
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Audio not available"}},
        )
    serve_path = path
    suffix = path.suffix.lower()

    if download:
        # Downloads must always be MP3
        if suffix == ".mp3":
            serve_path = path
        else:
            mp3 = await asyncio.to_thread(audio_archive.ensure_conversation_mp3, call_id, path)
            if mp3 is not None and mp3.is_file():
                serve_path = mp3
                suffix = ".mp3"
        download_name = f"{call_id}-recording.mp3"
    else:
        # Playout / media playback: convert WAV to MP4 if needed
        if suffix == ".wav":
            mp4 = await asyncio.to_thread(audio_archive.ensure_conversation_mp4, call_id, path)
            if mp4 is not None and mp4.is_file():
                serve_path = mp4
                suffix = ".mp4"
        download_name = f"{call_id}-{kind}{suffix}"

    media = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".m4a": "audio/mp4",
    }.get(suffix, "application/octet-stream")
    source = "vobiz" if path.name.startswith("vobiz_recording") else "telnyx" if path.name.startswith("telnyx") else "local"
    headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
        "X-Recording-Source": source,
        "Access-Control-Expose-Headers": "X-Recording-Source",
        "X-Audio-Encoding": suffix.lstrip("."),
    }
    return FileResponse(
        serve_path,
        media_type=media,
        filename=download_name if download else None,
        headers=headers,
        content_disposition_type="attachment" if download else "inline",
    )


@router.get("/api/call/{call_id}/audio")
async def get_audio_mix(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    return await get_audio(call_id, "mix", scope=scope)


@router.get("/api/call/{call_id}/memory")
async def get_memory(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    from server.call.memory_manager import memory_manager

    await _assert_call_scoped(call_id, scope)
    return {"call_id": call_id, "memory": memory_manager.get_snapshot(call_id)}


@router.get("/api/call/{call_id}/memory-events")
@router.get("/api/call/{call_id}/memory/events")
async def get_memory_events(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    from server.call.memory_manager import memory_manager

    await _assert_call_scoped(call_id, scope)
    return {"call_id": call_id, "events": memory_manager.list_events(call_id)}


@router.get("/api/call/{call_id}/memory/projection")
async def get_memory_projection(call_id: str, turn: int | None = Query(None), scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    from server.call.memory_manager import memory_manager
    from server.call.memory_projection import build as build_projection

    await _assert_call_scoped(call_id, scope)
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
async def post_memory_correction(call_id: str, body: MemoryCorrectionBody, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    from server.call.memory_manager import memory_manager

    await _assert_call_scoped(call_id, scope)
    result = memory_manager.manual_correction(
        call_id,
        body.operations,
        actor=body.actor,
        reason=body.reason,
        turn_seq=body.turn_seq,
    )
    return {"ok": True, "call_id": call_id, "event": result["event"], "memory": result["snapshot"]}


@router.get("/api/call/{call_id}/outcome")
async def get_outcome(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    from server.call.post_call_pipeline import read_outcome

    await _assert_call_scoped(call_id, scope)
    outcome = read_outcome(call_id)
    if outcome is None:
        return JSONResponse(
            status_code=202,
            content={"call_id": call_id, "status": "pending", "outcome": None},
        )
    return {"call_id": call_id, "outcome": outcome}


@router.post("/api/call/{call_id}/outcome/retry", status_code=202)
async def retry_outcome(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    from server.call.call_context import get as get_ctx
    from server.call.call_lifecycle_service import status_url
    from server.call.post_call_pipeline import enqueue

    await _assert_call_scoped(call_id, scope)
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


def _compute_call_analytics_payload(call_id: str, stored: dict) -> dict[str, Any]:
    from server.call.post_call_pipeline import read_outcome
    outcome = read_outcome(call_id) or {}
    lines = call_ledger.read_lines(call_id) or []
    meta = call_ledger.read_meta(call_id) or {}

    facts = dict(outcome.get("facts") or outcome.get("extracted_fields") or {})
    raw_name = str(
        facts.get("name")
        or facts.get("caller_name")
        or facts.get("customer_name")
        or facts.get("customer")
        or stored.get("customer")
        or ""
    ).strip()
    name_parts = raw_name.split(None, 1)
    first_name = name_parts[0] if name_parts else "Caller"
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    phone = str(
        facts.get("phone")
        or facts.get("mobile")
        or facts.get("callback_phone")
        or facts.get("contact")
        or stored.get("caller_id")
        or meta.get("caller_id")
        or ""
    ).strip()
    email = str(facts.get("email") or facts.get("mail") or "").strip()
    company = str(facts.get("company") or facts.get("organization") or facts.get("business") or "").strip()

    disposition = outcome.get("disposition") or stored.get("disposition") or "no_outcome"
    disposition_confidence = float(outcome.get("disposition_confidence") or 0.0)
    summary_en = str(outcome.get("summary_en") or stored.get("summary") or "").strip()
    summary_te = str(outcome.get("summary_te") or "").strip()
    next_action = outcome.get("next_action") or None
    objections = [str(o) for o in (outcome.get("objections") or [])]
    status_tags = [str(t) for t in (outcome.get("status_tags") or [])]

    # Turns & talk time
    user_turns = sum(1 for line in lines if line.get("role") == "user")
    agent_turns = sum(1 for line in lines if line.get("role") in ("assistant", "agent"))
    user_words = sum(len(str(line.get("text") or "").split()) for line in lines if line.get("role") == "user")
    agent_words = sum(len(str(line.get("text") or "").split()) for line in lines if line.get("role") in ("assistant", "agent"))
    total_words = user_words + agent_words
    user_ratio = round(user_words / total_words, 2) if total_words > 0 else 0.50

    # Sentiment analysis
    positive_dispositions = {"converted", "site_visit_planned", "qualified", "interested"}
    negative_dispositions = {"not_interested", "wrong_number"}
    if disposition in positive_dispositions:
        sentiment = "positive"
        sentiment_score = 0.88 if not objections else 0.72
        sentiment_label = "Positive (High Intent)"
    elif disposition in negative_dispositions:
        sentiment = "negative"
        sentiment_score = 0.20
        sentiment_label = "Challenging / Negative"
    elif objections:
        sentiment = "neutral"
        sentiment_score = 0.48
        sentiment_label = "Neutral (Objections Raised)"
    elif disposition == "callback_required":
        sentiment = "neutral"
        sentiment_score = 0.65
        sentiment_label = "Neutral / Callback Scheduled"
    else:
        sentiment = "neutral"
        sentiment_score = 0.50
        sentiment_label = "Neutral / General Inquiry"

    # Resolution status
    if disposition in ("converted", "site_visit_planned", "qualified"):
        resolution_status = "resolved"
    elif disposition == "callback_required" or next_action:
        resolution_status = "action_required"
    elif disposition == "not_interested":
        resolution_status = "closed_lost"
    elif disposition == "wrong_number":
        resolution_status = "invalid"
    else:
        resolution_status = "inconclusive"

    source = audio_archive.recording_source(call_id)
    duration_sec = int(stored.get("duration_sec") or meta.get("duration_sec") or 0)
    started_at = stored.get("started_at") or meta.get("started_at")

    contact = {
        "name": raw_name or "Caller",
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "email": email,
        "company": company,
        "disposition": disposition,
        "summary": summary_en,
        "next_action": next_action,
        "call_id": call_id,
        "duration_sec": duration_sec,
        "started_at": started_at,
    }

    return {
        "call_id": call_id,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "sentiment_label": sentiment_label,
        "resolution_status": resolution_status,
        "disposition": disposition,
        "disposition_confidence": disposition_confidence,
        "summary_en": summary_en,
        "summary_te": summary_te,
        "next_action": next_action,
        "objections": objections,
        "status_tags": status_tags,
        "facts": facts,
        "duration_sec": duration_sec,
        "started_at": started_at,
        "has_recording": source != "none",
        "recording_source": source,
        "talk_time": {
            "user_turns": user_turns,
            "agent_turns": agent_turns,
            "user_words": user_words,
            "agent_words": agent_words,
            "total_words": total_words,
            "user_ratio": user_ratio,
            "agent_ratio": round(1.0 - user_ratio, 2),
        },
        "contact": contact,
        "crm_sync_ready": bool(phone or email or raw_name),
    }


@router.get("/api/call/{call_id}/analytics")
async def get_call_analytics(call_id: str, scope: tuple[str, bool] = Depends(resolve_calls_scope)):
    """Retrieve comprehensive post-call analytics: sentiment, talk-time, resolution, and CRM contact facts."""
    stored = await _assert_call_scoped(call_id, scope)
    analytics = _compute_call_analytics_payload(call_id, stored)
    return {"call_id": call_id, "analytics": analytics}


@router.post("/api/call/{call_id}/crm-sync")
async def sync_call_to_crm(
    call_id: str,
    body: Optional[CrmSyncBody] = None,
    scope: tuple[str, bool] = Depends(resolve_calls_scope),
):
    """Synchronize caller contact info, conversation summary, and disposition to tenant's CRM."""
    stored = await _assert_call_scoped(call_id, scope)
    scoped_tenant, _ = scope
    analytics = _compute_call_analytics_payload(call_id, stored)
    contact = dict(analytics["contact"])
    if body and body.override_contact:
        contact.update({k: v for k, v in body.override_contact.items() if v})

    first_name = contact.get("first_name") or "Caller"
    last_name = contact.get("last_name") or ""
    phone = contact.get("phone") or ""
    email = contact.get("email") or ""
    company = contact.get("company") or ""
    summary = contact.get("summary") or "Voice call completed."
    disposition = contact.get("disposition") or "no_outcome"
    next_action = contact.get("next_action") or ""
    additional_notes = (body.notes or "").strip() if body else ""

    # Look up active CRM integrations for this tenant
    session_factory = get_session_factory()
    active_crms: list[TenantIntegration] = []
    if session_factory:
        try:
            async with session_factory() as session:
                stmt = select(TenantIntegration).where(
                    TenantIntegration.tenant_id == _safe_tenant_uuid(scoped_tenant),
                    TenantIntegration.status == "ACTIVE",
                )
                res = await session.execute(stmt)
                all_integrations = list(res.scalars().all())
                active_crms = [
                    i for i in all_integrations
                    if i.app_name.upper() in ("HUBSPOT", "SALESFORCE", "ZOHOCRM", "ZOHO_CRM", "PIPEDRIVE", "ZENDESK")
                ]
        except Exception as exc:
            logger.warning("[CRM_SYNC] Failed to query tenant integrations: %s", exc)

    if body and body.destination:
        dest_upper = body.destination.upper().replace("-", "_")
        active_crms = [i for i in active_crms if i.app_name.upper().replace("-", "_") == dest_upper]

    sync_results: list[dict[str, Any]] = []

    for crm in active_crms:
        app_name = crm.app_name.upper()
        if app_name == "HUBSPOT":
            contact_res = await nango_service.execute_in_call_tool(
                scoped_tenant,
                "HUBSPOT_CREATE_CONTACT",
                {
                    "firstname": first_name,
                    "lastname": last_name,
                    "email": email,
                    "phone": phone,
                    "company": company,
                },
            )
            note_content = (
                f"Automated Voice Call Activity\n"
                f"Call ID: {call_id}\n"
                f"Disposition: {disposition}\n"
                f"Next Action: {next_action or 'None'}\n"
                f"Summary: {summary}\n"
            )
            if additional_notes:
                note_content += f"\nOperator Notes: {additional_notes}"
            await nango_service.execute_in_call_tool(
                scoped_tenant,
                "HUBSPOT_CREATE_NOTE",
                {"body": note_content},
            )
            sync_results.append({
                "app": "HubSpot",
                "status": contact_res.get("status") or "success",
                "contact_id": contact_res.get("contact_id") or contact_res.get("id"),
                "details": contact_res.get("message") or contact_res.get("summary") or "Contact created/updated in HubSpot.",
            })

        elif app_name == "SALESFORCE":
            lead_res = await nango_service.execute_in_call_tool(
                scoped_tenant,
                "SALESFORCE_CREATE_LEAD",
                {
                    "FirstName": first_name,
                    "LastName": last_name or "Contact",
                    "Phone": phone,
                    "Email": email,
                    "Company": company or "Individual",
                    "Description": f"Call Summary ({call_id}): {summary}\nDisposition: {disposition}\nNext Action: {next_action}" + (f"\nNotes: {additional_notes}" if additional_notes else ""),
                },
            )
            sync_results.append({
                "app": "Salesforce",
                "status": lead_res.get("status") or "success",
                "lead_id": lead_res.get("lead_id") or lead_res.get("id"),
                "details": lead_res.get("message") or "Lead record pushed to Salesforce.",
            })

        elif app_name in ("ZOHOCRM", "ZOHO_CRM"):
            zoho_res = await nango_service.execute_in_call_tool(
                scoped_tenant,
                "ZOHO_CRM_CREATE_LEAD",
                {
                    "First_Name": first_name,
                    "Last_Name": last_name or "Lead",
                    "Phone": phone,
                    "Email": email,
                    "Company": company or "Individual",
                    "Description": f"Call Summary: {summary}",
                },
            )
            sync_results.append({
                "app": "Zoho CRM",
                "status": zoho_res.get("status") or "success",
                "details": zoho_res.get("message") or "Lead exported to Zoho CRM.",
            })

    if sync_results:
        return {
            "ok": True,
            "synced": True,
            "destinations": sync_results,
            "contact": contact,
            "message": f"Successfully synchronized contact to {len(sync_results)} CRM destination(s).",
        }

    return {
        "ok": True,
        "synced": False,
        "destinations": [],
        "contact": contact,
        "message": "No active CRM connection configured for this workspace. Connect your CRM under Integrations, or export directly as CSV, vCard, or JSON.",
    }


@router.get("/api/call/{call_id}/crm-export")
async def export_call_crm_contact(
    call_id: str,
    format: Literal["json", "csv", "vcf"] = Query("json"),
    scope: tuple[str, bool] = Depends(resolve_calls_scope),
):
    """Export caller contact card and post-call analytics in standard formats (vCard, CSV, JSON)."""
    stored = await _assert_call_scoped(call_id, scope)
    analytics = _compute_call_analytics_payload(call_id, stored)
    contact = analytics["contact"]

    if format == "vcf":
        vcf_lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN:{contact.get('name') or 'Voice Contact'}",
            f"N:{contact.get('last_name') or ''};{contact.get('first_name') or 'Caller'};;;",
        ]
        if contact.get("phone"):
            vcf_lines.append(f"TEL;TYPE=CELL,VOICE:{contact['phone']}")
        if contact.get("email"):
            vcf_lines.append(f"EMAIL;TYPE=PREF,INTERNET:{contact['email']}")
        if contact.get("company"):
            vcf_lines.append(f"ORG:{contact['company']}")
        note_str = (
            f"Voice Call Summary (ID: {call_id})\\n"
            f"Disposition: {contact.get('disposition')}\\n"
            f"Next Action: {contact.get('next_action') or 'None'}\\n"
            f"Summary: {contact.get('summary') or 'Completed'}"
        ).replace("\n", "\\n")
        vcf_lines.append(f"NOTE:{note_str}")
        vcf_lines.append(f"REV:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        vcf_lines.append("END:VCARD\n")
        return Response(
            content="\r\n".join(vcf_lines),
            media_type="text/vcard",
            headers={"Content-Disposition": f'attachment; filename="contact-{call_id}.vcf"'},
        )

    elif format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([
            "Call ID", "Full Name", "First Name", "Last Name",
            "Phone", "Email", "Company", "Disposition",
            "Sentiment", "Summary", "Next Action", "Duration (sec)", "Started At"
        ])
        writer.writerow([
            call_id,
            contact.get("name") or "",
            contact.get("first_name") or "",
            contact.get("last_name") or "",
            contact.get("phone") or "",
            contact.get("email") or "",
            contact.get("company") or "",
            contact.get("disposition") or "",
            analytics.get("sentiment_label") or "",
            contact.get("summary") or "",
            contact.get("next_action") or "",
            contact.get("duration_sec") or 0,
            contact.get("started_at") or "",
        ])
        return Response(
            content=out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="call-{call_id}-crm-contact.csv"'},
        )

    return JSONResponse(content={"ok": True, "call_id": call_id, "contact": contact, "analytics": analytics})

