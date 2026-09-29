"""Call back a missed caller — reuses the existing subscriber outbound path.

No new dialling logic lives here: the request is handed to ``subscriber_outbound``,
so every existing guard still applies (published brain, wallet balance, caller-id
resolution, concurrency cap, in-flight dedupe, idempotent ``dial_request_id``).

This module owns only the parts a console needs on top of that: resolving the
target number from a call or an attempt, authorising the agent, and recording the
callback so retries and AI redial have an audit trail.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select

from server.db.connection import get_session_factory
from server.db.models.entities import Call, CallAttempt, CallCallback
from server.services.saas.tenant_guard import SubscriberPrincipal, subscriber_workspace_tenant_id

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

CALLBACK_MODES = ("manual", "ai_redial", "scheduled")


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


def normalize_e164(value: Any) -> str | None:
    """Accept the loose shapes humans paste; return strict E.164 or ``None``."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("00"):
        raw = f"+{raw[2:]}"
    if raw.startswith("+"):
        # "+1 415 555 2671" → "+14155552671"
        candidate = "+" + re.sub(r"\D", "", raw[1:])
    else:
        digits = re.sub(r"\D", "", raw)
        # Assume India for a bare 10-digit local number, matching the rest of the product.
        candidate = f"+91{digits}" if len(digits) == 10 else f"+{digits}"
    return candidate if E164_RE.match(candidate) else None


async def _resolve_target(
    principal: SubscriberPrincipal,
    *,
    call_id: str,
    to_e164: str | None,
) -> tuple[str, str | None, str | None]:
    """Return ``(to_e164, agent_id, source)`` for the callback.

    A number supplied by the client wins; otherwise it is read from the call's
    ledger, its outcome facts, or its stored attempt.
    """
    explicit = normalize_e164(to_e164)
    if explicit:
        return explicit, None, "client"

    try:
        cid = uuid.UUID(str(call_id))
    except (ValueError, TypeError):
        raise _err(400, "invalid_call_id", "Invalid call id")

    factory = get_session_factory()
    if factory is None:
        raise _err(503, "db_unavailable", "Database required")

    from server.call.call_ledger import call_ledger
    from server.call.post_call_pipeline import read_outcome

    stored: Call | None = None
    attempt: CallAttempt | None = None
    async with factory() as session:
        stored = await session.get(Call, cid)
        if stored is None:
            attempt = (
                await session.execute(
                    select(CallAttempt).where(CallAttempt.attempt_id == cid)
                )
            ).scalar_one_or_none()

    workspace_tid = subscriber_workspace_tenant_id(principal)

    if stored is not None:
        if str(stored.tenant_id) not in (str(principal.tenant_id), str(workspace_tid)):
            raise _err(404, "not_found", "Call not found")
        # An inbound call is called back at the caller; an outbound one at the callee.
        if stored.direction == "outbound":
            target = _from_ledger(call_ledger, str(stored.call_id), "callee_e164")
        else:
            target = _from_ledger(call_ledger, str(stored.call_id), "caller_id")
        if not target:
            target = _from_outcome(read_outcome, str(stored.call_id))
        if not target:
            raise _err(
                400,
                "callback_target_unknown",
                "No caller number is recorded for this call. Enter the number to call back.",
            )
        return target, str(stored.agent_id), "call"

    if attempt is not None:
        if str(attempt.tenant_id) not in (str(principal.tenant_id), str(workspace_tid)):
            raise _err(404, "not_found", "Call not found")
        target = normalize_e164(attempt.from_number if attempt.direction != "outbound" else attempt.to_number)
        if not target:
            raise _err(
                400,
                "callback_target_unknown",
                "No caller number is recorded for this call. Enter the number to call back.",
            )
        return target, str(attempt.agent_id) if attempt.agent_id else None, "attempt"

    raise _err(404, "not_found", "Call not found")


def _from_ledger(call_ledger: Any, call_id: str, field: str) -> str | None:
    try:
        review = call_ledger.review_fields(call_id) or {}
    except Exception:
        return None
    return normalize_e164(review.get(field))


def _from_outcome(read_outcome: Any, call_id: str) -> str | None:
    try:
        outcome = read_outcome(call_id) or {}
    except Exception:
        return None
    facts = outcome.get("facts") or outcome.get("extracted_fields") or {}
    for key in ("phone", "callback_phone", "caller_phone", "callee_e164"):
        value = normalize_e164(facts.get(key))
        if value:
            return value
    return None


async def resolve_workspace_agent(agent_id: str, tenant_id: str) -> dict[str, Any]:
    """Load an agent the caller owns, or raise a clean 404.

    ``agent_service.get_agent`` signals "not found" with a ``KeyError``, which would
    surface as an unhandled 500 if it escaped. Callers on a live dialling path must
    never leak a stack trace or a 500 to a browser.
    """
    from server.brain.agent_service import agent_service

    try:
        return await agent_service.get_agent(agent_id, tenant_id=tenant_id)
    except (KeyError, ValueError):
        raise _err(404, "not_found", "Agent not found")


async def request_callback(
    principal: SubscriberPrincipal,
    *,
    call_id: str,
    to_e164: str | None = None,
    agent_id: str | None = None,
    from_e164: str | None = None,
    dial_request_id: str | None = None,
    mode: str = "manual",
) -> dict[str, Any]:
    """Dial a missed caller back through the normal subscriber outbound flow."""
    from server.services.saas.telephony_orchestrator import subscriber_outbound

    normalized_mode = str(mode or "manual").strip().lower()
    if normalized_mode not in CALLBACK_MODES:
        raise _err(400, "invalid_mode", f"mode must be one of {', '.join(CALLBACK_MODES)}")

    target, call_agent_id, source = await _resolve_target(
        principal, call_id=call_id, to_e164=to_e164
    )
    workspace_tid = subscriber_workspace_tenant_id(principal)
    effective_agent = str(agent_id or call_agent_id or "").strip()
    if not effective_agent:
        raise _err(400, "invalid_agent", "Choose an agent to place this callback")

    # Authorise the agent against the caller's own workspace tenant.
    await resolve_workspace_agent(effective_agent, str(workspace_tid))

    request_id = str(dial_request_id or uuid.uuid4())
    existing = await _existing_callback(request_id, principal.tenant_id)
    if existing is not None:
        return existing

    callback_row = await _create_callback_row(
        principal,
        call_id=call_id,
        request_id=request_id,
        agent_id=effective_agent,
        to_e164=target,
        from_e164=from_e164,
        mode=normalized_mode,
        original_call_id=call_id if source == "call" else None,
    )

    result = await subscriber_outbound(
        principal,
        agent_id=effective_agent,
        from_e164=normalize_e164(from_e164),
        to_e164=target,
        dial_request_id=request_id,
    )

    ok = bool(result.get("ok"))
    await _finish_callback_row(
        callback_row,
        status="dialed" if ok else "failed",
        provider=result.get("provider"),
        control_id=result.get("call_control_id"),
        error=None if ok else str(result.get("error") or "dial_failed")[:500],
    )
    return {
        "ok": ok,
        "callbackOf": call_id,
        "toE164": target,
        "agentId": effective_agent,
        "mode": normalized_mode,
        "dialRequestId": request_id,
        "provider": result.get("provider"),
        "callControlId": result.get("call_control_id"),
        "error": result.get("error"),
        "code": result.get("code"),
    }


async def _existing_callback(dial_request_id: str, tenant_id: uuid.UUID) -> dict[str, Any] | None:
    """Idempotency: a replayed request returns the first outcome unchanged."""
    factory = get_session_factory()
    if factory is None:
        return None
    async with factory() as session:
        row = (
            await session.execute(
                select(CallCallback).where(CallCallback.dial_request_id == dial_request_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if str(row.tenant_id) != str(tenant_id):
            raise _err(409, "dial_request_conflict", "This dial request id is already in use")
        return {
            "ok": row.status == "dialed",
            "callbackOf": str(row.original_call_id or ""),
            "toE164": row.to_e164,
            "agentId": row.agent_id,
            "mode": row.mode,
            "dialRequestId": row.dial_request_id,
            "provider": row.provider,
            "callControlId": row.provider_call_control_id,
            "error": row.error,
            "replayed": True,
        }


async def _create_callback_row(
    principal: SubscriberPrincipal,
    *,
    call_id: str,
    request_id: str,
    agent_id: str,
    to_e164: str,
    from_e164: str | None,
    mode: str,
    original_call_id: str | None,
) -> str:
    factory = get_session_factory()
    if factory is None:
        return request_id
    try:
        cb_uuid = uuid.UUID(str(call_id))
        attempt_uuid = None if original_call_id else cb_uuid
    except (ValueError, TypeError):
        cb_uuid = None
        attempt_uuid = None
    async with factory() as session:
        row = CallCallback(
            callback_id=uuid.uuid4(),
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            original_call_id=cb_uuid,
            original_attempt_id=attempt_uuid if attempt_uuid else None,
            agent_id=agent_id,
            to_e164=to_e164,
            from_e164=from_e164,
            dial_request_id=request_id,
            mode=mode,
            status="pending",
        )
        session.add(row)
        try:
            await session.commit()
        except Exception:
            await session.rollback()
        return request_id


async def _finish_callback_row(
    request_id: str,
    *,
    status: str,
    provider: str | None = None,
    control_id: str | None = None,
    error: str | None = None,
) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        row = (
            await session.execute(
                select(CallCallback).where(CallCallback.dial_request_id == request_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.status = status
        row.provider = provider
        row.provider_call_control_id = control_id
        row.error = error
        await session.commit()


async def list_callbacks(
    principal: SubscriberPrincipal,
    *,
    call_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    factory = get_session_factory()
    if factory is None:
        return []
    limit = max(1, min(limit, 200))
    async with factory() as session:
        stmt = select(CallCallback).where(CallCallback.tenant_id == principal.tenant_id)
        if call_id:
            # The id may be a connected call or a ringing attempt, and a callback
            # row records whichever it was. Match both, or the Missed tab would
            # never show the callbacks it just made.
            try:
                parsed = uuid.UUID(str(call_id))
            except (ValueError, TypeError):
                parsed = None
            if parsed is not None:
                stmt = stmt.where(
                    or_(
                        CallCallback.original_call_id == parsed,
                        CallCallback.original_attempt_id == parsed,
                    )
                )
        rows = (await session.execute(stmt.order_by(CallCallback.created_at.desc()).limit(limit))).scalars()
        return [
            {
                "callbackId": str(r.callback_id),
                "originalCallId": str(r.original_call_id) if r.original_call_id else None,
                "originalAttemptId": str(r.original_attempt_id) if r.original_attempt_id else None,
                "agentId": r.agent_id,
                "toE164": r.to_e164,
                "fromE164": r.from_e164,
                "mode": r.mode,
                "status": r.status,
                "provider": r.provider,
                "callControlId": r.provider_call_control_id,
                "error": r.error,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
