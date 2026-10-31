"""Persist every ringing event — outbound dials and carrier hangups — as an attempt.

Before this module only Telnyx *inbound* calls wrote ``call_attempts`` rows.
Vobiz (the India carrier) never wrote any, and no outbound dial ever did, so a
call the callee did not answer, rejected, or that failed to connect left no
trace in the call history: a ``calls`` row is only created once media streams.

Every function here is failure-tolerant: carrier webhooks and dial responses
must never be delayed or failed by history bookkeeping.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from server.call.call_store import call_attempt_store
from server.call.hangup_causes import REASON_DIAL_FAILED, classify_hangup

logger = logging.getLogger(__name__)

#: Dial-result codes that mean the carrier itself refused the call. Policy
#: refusals (DND, wallet, KYC, concurrency) never rang anyone and are not attempts.
CARRIER_FAILURE_CODES = frozenset({"dial_failed", "carrier_error", "voice_service_unavailable"})


def dial_origin(contact: dict[str, Any] | None, dial_request_id: str | None = None) -> str:
    """Why this dial happened. Auto-recall only re-dials plain one-off calls
    (``outbound_dial``): campaigns keep their own retry rules and follow-up dials
    are retried by the follow-up worker."""
    contact = contact or {}
    request = str(dial_request_id or "")
    if contact.get("campaign_id") or contact.get("campaignId") or request.startswith("camp:"):
        return "campaign_dial"
    if contact.get("followup_job_id") or request.startswith("fu:"):
        return "followup_dial"
    return "outbound_dial"


def _control_from_result(result: dict[str, Any]) -> str:
    return str(result.get("call_control_id") or result.get("callControlId") or "").strip()


async def record_outbound_dial(
    *,
    provider: str,
    tenant_id: str,
    agent_id: str | None,
    from_e164: str | None,
    to_e164: str,
    result: Any,
    dial_request_id: str | None = None,
    contact: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Write the outbound attempt right after the carrier accepted (or refused) the dial."""
    if not isinstance(result, dict) or not tenant_id:
        return None
    try:
        fields = dict(
            tenant_id=str(tenant_id),
            agent_id=str(agent_id) if agent_id else None,
            provider=provider,
            direction="outbound",
            from_number=from_e164 or None,
            to_number=to_e164 or None,
            status="in_progress",
            policy_reason=dial_origin(contact, dial_request_id),
        )
        if result.get("ok"):
            control = _control_from_result(result)
            if not control:
                return None
            return await call_attempt_store.ensure_attempt(control, **fields)
        if str(result.get("code") or "") not in CARRIER_FAILURE_CODES or not dial_request_id:
            return None
        control = f"dialfail:{dial_request_id}"[:255]
        await call_attempt_store.ensure_attempt(control, **fields)
        return await call_attempt_store.finalize_by_control(control, status="failed", end_reason=REASON_DIAL_FAILED)
    except Exception as exc:  # noqa: BLE001 - history must never fail a dial.
        logger.warning("call_attempt.outbound_record_failed kind=%s", type(exc).__name__)
        return None


async def finalize_carrier_attempt(
    *,
    provider: str,
    control_ids: Iterable[str | None],
    cause: Any,
    answered: bool,
    linked_call_id: str | None,
    sip_code: Any = None,
    create_with: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Close the attempt for a carrier hangup, creating it first when needed.

    ``control_ids`` are tried in order (CallUUID, RequestUUID, tracking id); the first
    one with a row wins. ``create_with`` supplies tenant/agent/numbers for calls whose
    ringing was never recorded (e.g. a Vobiz inbound call declined at answer time).
    """
    candidates = [str(c).strip() for c in control_ids if c and str(c).strip()]
    if not candidates:
        return None
    try:
        existing = None
        control = candidates[0]
        for candidate in candidates:
            row = await _lookup(candidate)
            if row:
                existing, control = row, candidate
                break
        if existing is None:
            if not create_with or not create_with.get("tenant_id"):
                return None
            await call_attempt_store.ensure_attempt(control, provider=provider, **create_with)
            direction = str(create_with.get("direction") or "inbound")
        else:
            direction = str(existing.get("direction") or "inbound")
        if linked_call_id:
            await call_attempt_store.link_to_call(control, str(linked_call_id))
            return {"control_id": control, "status": "linked"}
        outcome = classify_hangup(cause, direction=direction, answered=answered, connected=False, sip_code=sip_code)
        await call_attempt_store.finalize_by_control(
            control, status=outcome.status, end_reason=outcome.end_reason, answered=False,
        )
        return {"control_id": control, "status": outcome.status, "end_reason": outcome.end_reason}
    except Exception as exc:  # noqa: BLE001
        logger.warning("call_attempt.finalize_failed provider=%s kind=%s", provider, type(exc).__name__)
        return None


async def _lookup(control_id: str) -> dict[str, Any] | None:
    """One attempt row by carrier control id (memory or database)."""
    from sqlalchemy import select

    from server.call import call_store as store
    from server.db.models.entities import CallAttempt

    factory = store.get_session_factory()
    if factory is None:
        rec = store._ATTEMPT_MEM.get(control_id)
        return dict(rec) if rec else None
    async with factory() as session:
        row = (
            await session.execute(select(CallAttempt).where(CallAttempt.provider_call_control_id == control_id))
        ).scalar_one_or_none()
        return store._attempt_row_to_dict(row) if row is not None else None
