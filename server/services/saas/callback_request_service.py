"""Tenant-managed future callback requests, using the existing callback table."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
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


def resolve_requested_window(texts: list[str], at: datetime, config: dict | None = None,
                             spread_key: str = "") -> dict[str, Any] | None:
    """The concrete window for a vague callback time, in the agent's follow-up timezone."""
    from server.services.saas.followup_policy import FollowUpConfig
    from server.services.saas.followup_service import resolve_vague_time
    try:
        cfg = FollowUpConfig.model_validate(config or {})
    except Exception:  # noqa: BLE001 - a stale/invalid saved policy falls back to defaults.
        cfg = FollowUpConfig()
    return resolve_vague_time(cfg, at, *texts, spread_key=spread_key)


def _public(row: CallCallback) -> dict[str, Any]:
    meta = call_ledger.read_meta(str(row.original_call_id)) if row.original_call_id else {}
    details = meta.get("callback_request") or {}
    resolved = details.get("resolvedWindow")
    if resolved is None and row.created_at and (details.get("requestedWhen") or details.get("requestText")):
        # Requests saved before windows were resolved: anchor on when the caller asked.
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        resolved = resolve_requested_window(
            [details.get("requestedWhen") or "", details.get("requestText") or ""], created,
            spread_key=str(row.callback_id))
    return {
        "id": str(row.callback_id), "callId": str(row.original_call_id),
        "agentId": row.agent_id, "phone": row.to_e164, "status": row.status,
        "requestedWhen": details.get("requestedWhen") or "Requested during the call",
        "requestText": details.get("requestText") or "",
        "resolvedWindow": resolved,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
    }


async def recover_interrupted_callback(ctx: Any) -> dict[str, Any] | None:
    """Keep an unfinished explicit request for human review after a disconnect."""
    if ctx is not None and getattr(ctx, "callback_withdrawal_pending", False):
        await withdraw_callback_request(ctx)
        return None
    if (ctx is None or getattr(ctx, "contact_preference", "") == "do_not_call"
            or getattr(ctx, "callback_close_phase", "idle") == "idle"):
        return None
    request = str(getattr(ctx, "callback_request_text", "") or "").strip()
    if not request:
        return None
    return await asyncio.wait_for(record_callback_request(ctx, request, review_only=True), timeout=3.0)


async def record_callback_request(ctx: Any, request_text: str, *, review_only: bool = False) -> dict[str, Any] | None:
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
    generation = int(getattr(ctx, "callback_generation", 0) or meta.get("callback_generation") or 0)
    key = f"requested:{call_id}" + (f":{generation}" if generation else "")
    policy_config: dict | None = None
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
                                              requested_when=requested_when, recent_turns=recent_turns,
                                              review_only=review_only)
                        await session.flush()
                except Exception as exc:
                    logger.warning("callback.scheduling_unavailable kind=%s", type(exc).__name__)
                try:
                    from server.db.models.followup_models import AgentFollowUpPolicy
                    async with session.begin_nested():
                        policy = await session.scalar(select(AgentFollowUpPolicy).where(
                            AgentFollowUpPolicy.tenant_id == tenant_id,
                            AgentFollowUpPolicy.agent_id == uuid.UUID(str(ctx.agent_id))))
                        policy_config = dict(policy.config or {}) if policy is not None else None
                except Exception as exc:
                    logger.warning("callback.policy_unavailable kind=%s", type(exc).__name__)
                await session.commit()
            except IntegrityError:
                await session.rollback()
                row = (await session.execute(query)).scalar_one_or_none()
                if row is None:
                    raise
        callback_id, status = str(row.callback_id), row.status
    # Re-read after the database await so concurrent transcript/media metadata survives.
    requested_when_text = str(getattr(ctx, "callback_when", "") or request_text)[:400]
    resolved = resolve_requested_window([requested_when_text, request_text], datetime.now(timezone.utc),
                                        policy_config, spread_key=callback_id)
    meta = call_ledger.read_meta(str(call_id))
    meta["callback_request"] = {
        "id": callback_id, "status": status,
        "requestedWhen": requested_when_text,
        "requestText": request_text[:800],
        **({"resolvedWindow": resolved} if resolved else {}),
    }
    meta.update(callback_cancelled=False, callback_withdrawal_pending=False)
    call_ledger.write_meta(str(call_id), meta)
    return {"id": callback_id, "status": status}


async def withdraw_callback_request(ctx: Any) -> bool:
    try:
        async with asyncio.timeout(2.5):
            return await _withdraw_callback_request(ctx)
    except Exception as exc:
        ctx.callback_withdrawal_pending = True
        logger.warning("callback.withdrawal_pending kind=%s", type(exc).__name__)
        return False


async def _withdraw_callback_request(ctx: Any) -> bool:
    """Withdraw only this call's requests; preserve other tenants/calls and DND."""
    factory = get_session_factory()
    try:
        tenant_id, call_id, agent_id = (uuid.UUID(str(getattr(ctx, key))) for key in ("tenant_id", "call_id", "agent_id"))
    except (ValueError, TypeError, AttributeError):
        return False
    if not getattr(ctx, "callback_withdrawal_pending", False):
        meta = await asyncio.to_thread(call_ledger.read_meta, str(call_id))
        if ((meta.get("tenant_id") and meta["tenant_id"] != str(tenant_id))
                or (meta.get("agent_id") and meta["agent_id"] != str(agent_id))):
            return False
        ctx.callback_generation = int(meta.get("callback_generation") or 0) + 1
        meta.update(callback_cancelled=True, callback_withdrawal_pending=True,
                    callback_generation=ctx.callback_generation)
        await asyncio.to_thread(call_ledger.write_meta, str(call_id), meta)
    ctx.callback_withdrawal_pending = True
    if factory is None:
        return False
    try:
        async with asyncio.timeout(1.5), factory() as session:
            async with session.begin():
                owner = await session.scalar(select(Call).where(Call.call_id == call_id,
                    Call.tenant_id == tenant_id, Call.agent_id == agent_id))
                if owner is None:
                    return False
                rows = (await session.scalars(select(CallCallback).where(
                    CallCallback.tenant_id == tenant_id, CallCallback.agent_id == str(agent_id),
                    CallCallback.original_call_id == call_id, CallCallback.mode == REQUEST_MODE,
                    CallCallback.status == "requested").with_for_update())).all()
                moment = datetime.now(timezone.utc)
                for row in rows:
                    row.status, row.updated_at = "dismissed", moment
                # Optional queue tables may not exist before migration 047.
                try:
                    from server.db.models.followup_models import FollowUpJob
                    async with session.begin_nested():
                        await session.execute(update(FollowUpJob).where(
                            FollowUpJob.tenant_id == tenant_id, FollowUpJob.agent_id == agent_id,
                            FollowUpJob.source_id == str(call_id), FollowUpJob.kind == "callback",
                            FollowUpJob.status.in_(("planning", "resolving", "needs_review", "scheduled", "dispatching")),
                        ).values(status="cancelled", reason="caller_withdrew_callback", lease_token=None,
                                 lease_until=None, updated_at=moment))
                except Exception as exc:
                    logger.warning("callback.withdraw_queue_unavailable kind=%s", type(exc).__name__)
        ctx.callback_withdrawal_pending = False
        meta = await asyncio.to_thread(call_ledger.read_meta, str(call_id))
        meta["callback_withdrawal_pending"] = False
        await asyncio.to_thread(call_ledger.write_meta, str(call_id), meta)
        return True
    except Exception as exc:
        logger.warning("callback.withdrawal_unconfirmed kind=%s", type(exc).__name__)
        return False


async def list_callback_requests(principal: Any, *, agent_id: str | None = None, status: str = "requested") -> list[dict[str, Any]]:
    if status not in {"requested", "completed", "converted", "dismissed"}:
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
        if status == "converted":
            # Tenant confirmation must agree with the CRM's conversion metric.
            # Scope by the original agent as well as workspace and phone.
            from server.db.models.saas_models import Lead
            leads = (await session.scalars(select(Lead).where(Lead.tenant_id == row.tenant_id,
                Lead.agent_id == row.agent_id, Lead.phone.is_not(None)))).all()
            for lead in leads:
                if normalize_e164(lead.phone) == normalize_e164(row.to_e164):
                    lead.stage, lead.updated_at = "converted", datetime.now(timezone.utc)
        await session.commit()
        result = {"id": str(row.callback_id), "status": row.status}
    try:
        from server.services.saas.followup_service import suppress_jobs
        await suppress_jobs(subscriber_workspace_tenant_id(principal), callback_id=str(callback_id), reason="request_closed")
        if status == "converted":
            from server.services.saas.lead_scoring import retire_converted_followups
            await retire_converted_followups(subscriber_workspace_tenant_id(principal), row.to_e164)
    except Exception as exc:
        # Dispatch also rechecks the committed request status before dialing.
        logger.warning("callback.cancel_queue_failed kind=%s", type(exc).__name__)
    return result
