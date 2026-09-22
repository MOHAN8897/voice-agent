"""Subscriber PSTN — server-owned stack (PRD-05)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select

from server.auth.session import SessionData
from server.brain.agent_service import agent_service
from server.db.connection import get_session_factory
from server.db.models.entities import Call
from server.db.models.phase5_models import PhoneNumber
from server.services.saas.tenant_guard import SubscriberPrincipal


def saas_stack_override(language: str) -> dict[str, Any]:
    return {"pipeline": "realtime_voice", "language": language}


async def resolve_outbound_from_e164(
    tenant_id: uuid.UUID,
    agent_id: str,
    from_e164: str | None,
) -> str:
    """Pick caller ID: explicit fromE164, else agent-assigned DID, else any outbound-enabled tenant number."""
    if from_e164 and from_e164.strip():
        await assert_from_number(tenant_id, from_e164.strip())
        return from_e164.strip()
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "db_unavailable", "message": "Database required"}},
        )
    try:
        agent_uuid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_agent", "message": "Invalid agent"}})
    async with factory() as session:
        result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == tenant_id,
                PhoneNumber.agent_id == agent_uuid,
                PhoneNumber.released_at.is_(None),
                PhoneNumber.outbound_enabled.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return row.e164
        result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == tenant_id,
                PhoneNumber.released_at.is_(None),
                PhoneNumber.outbound_enabled.is_(True),
            )
        )
        any_row = result.scalars().first()
        if any_row:
            return any_row.e164
    raise HTTPException(
        status_code=400,
        detail={
            "error": {
                "code": "no_from_number",
                "message": "Buy a phone number and assign it to this agent (or pass fromE164).",
            }
        },
    )


async def assert_from_number(tenant_id: uuid.UUID, from_e164: str) -> PhoneNumber:
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": {"code": "db_unavailable", "message": "Database required"}})
    async with factory() as session:
        result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == tenant_id,
                PhoneNumber.e164 == from_e164,
                PhoneNumber.released_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        if row is None or row.status not in ("active", "pending") or not row.outbound_enabled:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "invalid_from_number", "message": "From number not available"}},
            )
        return row


async def assert_concurrent_limit(tenant_id: uuid.UUID, limits: dict) -> None:
    max_pstn = int(limits.get("max_concurrent_pstn") or 3)
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        active = await session.execute(
            select(func.count())
            .select_from(Call)
            .where(
                Call.tenant_id == tenant_id,
                Call.channel == "pstn",
                Call.ended_at.is_(None),
            )
        )
        count = int(active.scalar_one() or 0)
        if count >= max_pstn:
            raise HTTPException(
                status_code=429,
                detail={"error": {"code": "concurrency_limit", "message": "Too many active calls"}},
            )


async def subscriber_outbound(
    principal: SubscriberPrincipal,
    *,
    agent_id: str,
    from_e164: str | None,
    to_e164: str,
) -> dict[str, Any]:
    from server.routes.dev_telephony import OutboundTestBody, _outbound_telnyx
    from server.services.telephony import active_telephony_provider, telephony_guard_error

    agent = await agent_service.get_agent(agent_id, tenant_id=str(principal.tenant_id))
    if not agent.get("active_compiled_brain_version"):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "brain_not_published", "message": "Publish agent brain before calling"}},
        )
    from server.services.saas.billing_wallet_service import assert_wallet_allows_pstn

    await assert_wallet_allows_pstn(principal.tenant_id)
    resolved_from = await resolve_outbound_from_e164(principal.tenant_id, agent_id, from_e164)
    from server.db.models.entities import Tenant

    factory = get_session_factory()
    limits: dict = {}
    if factory:
        async with factory() as session:
            tenant = await session.get(Tenant, principal.tenant_id)
            limits = (tenant.limits or {}) if tenant else {}
    await assert_concurrent_limit(principal.tenant_id, limits)

    provider = active_telephony_provider()
    guard = telephony_guard_error(provider)
    if guard:
        return {"ok": False, "error": guard, "provider": provider}

    lang = (agent.get("languages") or ["te-IN"])[0]
    body = OutboundTestBody(
        agentId=agent_id,
        fromE164=resolved_from,
        toE164=to_e164.strip(),
        tier="medium",
        language=lang,
        stackOverride=saas_stack_override(lang),
        inheritTestStudioConfig=False,
    )
    session_stub = SessionData(
        kind="app",
        subject=str(principal.user_id),
        tenant_id=str(principal.tenant_id),
        role=principal.role,
        issued_at=0,
    )
    from server.services.outbound_dial_guard import acquire_outbound_slot, release_outbound_slot

    to_number = body.to_e164.strip()
    if not await acquire_outbound_slot(provider, to_number):
        return {
            "ok": False,
            "error": "An outbound call to this number is already in progress.",
            "code": "dial_in_progress",
        }
    try:
        if provider == "telnyx":
            return await _outbound_telnyx(body, session_stub)
        return {"ok": False, "error": f"Provider {provider} not supported for subscriber PSTN yet"}
    finally:
        release_outbound_slot(provider, to_number)
