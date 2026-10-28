"""Tenant-managed future callback requests, using the existing callback table."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.call.call_ledger import call_ledger
from server.db.connection import get_session_factory
from server.db.models.entities import Call, CallCallback
from server.services.saas.call_callback_service import normalize_e164
from server.services.saas.tenant_guard import subscriber_workspace_tenant_id

REQUEST_MODE = "requested"
logger = logging.getLogger(__name__)


def _timing_context(call_id: str, request_text: str, requested_when: str) -> list[dict[str, str]]:
    """Small, timestamped transcript context for short answers to a timing question."""
    rows = [r for r in call_ledger.read_lines(call_id)
            if r.get("role") in ("user", "assistant") and not r.get("partial") and str(r.get("text") or "").strip()]
    selected = set(range(max(0, len(rows) - 8), len(rows)))
    for phrase in (request_text, requested_when):
        if not phrase.strip():
            continue
        match = next((i for i in range(len(rows) - 1, -1, -1)
                      if rows[i]["role"] == "user" and phrase.casefold() in str(rows[i]["text"]).casefold()), None)
        if match is not None:
            selected.add(match)
    return [{"role": rows[i]["role"], "text": str(rows[i]["text"])[:500], "at": str(rows[i].get("ts") or "")}
            for i in sorted(selected)]


async def prepare_callback_close(ctx: Any, decision: dict[str, Any], language: str, user_text: str) -> dict[str, Any]:
    """A spoken callback assurance requires a durable record, across voice stacks."""
    if not decision.get("should_end") or decision.get("contact_preference") != "callback":
        return decision
    from server.call.call_end_policy import callback_save_failed_for, server_farewell_for
    from server.utils.logger import log_pstn

    try:
        saved = await asyncio.wait_for(record_callback_request(
            ctx, str(getattr(ctx, "callback_request_text", "") or user_text),
        ), timeout=3.0)
    except Exception as exc:  # noqa: BLE001 -- closing must report storage failures honestly.
        saved = None
        log_pstn("callback.request_failed", call_id=getattr(ctx, "call_id", None), error_type=type(exc).__name__)
    result = dict(decision)
    if saved:
        result["farewell"] = server_farewell_for(language, policy=getattr(ctx, "call_end_policy", None), contact_preference="callback")
        log_pstn("callback.request_saved", call_id=getattr(ctx, "call_id", None))
    else:
        result["farewell"] = callback_save_failed_for(language) + " " + server_farewell_for(language, policy=getattr(ctx, "call_end_policy", None))
        log_pstn("callback.request_not_saved", call_id=getattr(ctx, "call_id", None))
    return result


def _public(row: CallCallback) -> dict[str, Any]:
    meta = call_ledger.read_meta(str(row.original_call_id)) if row.original_call_id else {}
    details = meta.get("callback_request") or {}
    return {
        "id": str(row.callback_id), "callId": str(row.original_call_id),
        "agentId": row.agent_id, "phone": row.to_e164, "status": row.status,
        "requestedWhen": details.get("requestedWhen") or "Requested during the call",
        "requestText": details.get("requestText") or "",
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


async def record_callback_request(ctx: Any, request_text: str) -> dict[str, Any] | None:
    """Commit before the voice agent claims the request was noted. Never dials."""
    factory = get_session_factory()
    if factory is None or ctx is None:
        return None
    try:
        tenant_id, call_id = uuid.UUID(str(ctx.tenant_id)), uuid.UUID(str(ctx.call_id))
    except (ValueError, TypeError, AttributeError):
        return None
    meta = call_ledger.read_meta(str(call_id))
    target = normalize_e164(
        getattr(ctx, "callback_phone", None)
        or (meta.get("callee_e164") if meta.get("direction") == "outbound" else meta.get("caller_id"))
    )
    if not target:
        return None
    key = f"requested:{call_id}"
    async with factory() as session:
        call = (await session.execute(select(Call).where(
            Call.call_id == call_id, Call.tenant_id == tenant_id,
        ))).scalar_one_or_none()
        if call is None or str(call.agent_id) != str(ctx.agent_id):
            return None
        query = select(CallCallback).where(
            CallCallback.tenant_id == tenant_id, CallCallback.dial_request_id == key,
            CallCallback.mode == REQUEST_MODE,
        )
        row = (await session.execute(query)).scalar_one_or_none()
        if row is None:
            row = CallCallback(
                callback_id=uuid.uuid4(), tenant_id=tenant_id, original_call_id=call_id,
                agent_id=str(ctx.agent_id), to_e164=target, dial_request_id=key,
                mode=REQUEST_MODE, status="requested", created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            try:
                await session.flush()
                # Optional new storage stays in a savepoint so older installations
                # retain the durable manual request until their migration is applied.
                try:
                    from server.services.saas.followup_service import capture_request
                    from server.services.saas.followup_policy import timing_model_snapshot
                    selected = getattr(getattr(ctx, "resolved_stack", None), "llm", None)
                    llm = timing_model_snapshot(selected)
                    requested_when = str(getattr(ctx, "callback_when", "") or "")[:400]
                    recent_turns = await asyncio.to_thread(_timing_context, str(call_id), request_text, requested_when)
                    async with session.begin_nested():
                        await capture_request(session, row, request_text=request_text, llm=llm,
                                              requested_when=requested_when, recent_turns=recent_turns)
                        await session.flush()
                except Exception as exc:
                    logger.warning("callback.scheduling_unavailable kind=%s", type(exc).__name__)
                await session.commit()
            except IntegrityError:
                await session.rollback()
                row = (await session.execute(query)).scalar_one_or_none()
                if row is None:
                    raise
        callback_id, status = str(row.callback_id), row.status
    # Re-read after the database await so concurrent transcript/media metadata survives.
    meta = call_ledger.read_meta(str(call_id))
    meta["callback_request"] = {
        "id": callback_id, "status": status,
        "requestedWhen": str(getattr(ctx, "callback_when", "") or request_text)[:400],
        "requestText": request_text[:800],
    }
    call_ledger.write_meta(str(call_id), meta)
    return {"id": callback_id, "status": status}


async def list_callback_requests(principal: Any, *, agent_id: str | None = None, status: str = "requested") -> list[dict[str, Any]]:
    if status not in {"requested", "converted", "dismissed"}:
        raise HTTPException(422, "Invalid callback status")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(503, "Callback requests are temporarily unavailable")
    async with factory() as session:
        query = select(CallCallback).where(
            CallCallback.tenant_id == subscriber_workspace_tenant_id(principal),
            CallCallback.mode == REQUEST_MODE, CallCallback.status == status,
        )
        if agent_id:
            query = query.where(CallCallback.agent_id == agent_id)
        rows = (await session.execute(query.order_by(CallCallback.created_at.desc()).limit(200))).scalars().all()
        return [_public(row) for row in rows]


async def update_callback_request(principal: Any, callback_id: uuid.UUID, status: str) -> dict[str, Any]:
    if status not in {"converted", "dismissed"}:
        raise HTTPException(422, "Choose converted or dismissed")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(503, "Callback requests are temporarily unavailable")
    async with factory() as session:
        row = (await session.execute(select(CallCallback).where(
            CallCallback.callback_id == callback_id,
            CallCallback.tenant_id == subscriber_workspace_tenant_id(principal),
            CallCallback.mode == REQUEST_MODE,
        ).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "Callback request not found")
        row.status = status
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
        result = {"id": str(row.callback_id), "status": row.status}
    try:
        from server.services.saas.followup_service import suppress_jobs
        await suppress_jobs(subscriber_workspace_tenant_id(principal), callback_id=str(callback_id), reason="request_closed")
    except Exception as exc:
        # Dispatch also rechecks the committed request status before dialing.
        logger.warning("callback.cancel_queue_failed kind=%s", type(exc).__name__)
    return result
