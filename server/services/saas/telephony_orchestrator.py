"""Subscriber PSTN — server-owned stack (PRD-05)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select

from server.auth.session import SessionData
from server.db.connection import get_session_factory
from server.db.models.entities import Call
from server.db.models.phase5_models import PhoneNumber
from server.config.env import get_settings
from server.services.saas.platform_admins import is_dev_tester_email
from server.services.saas.pstn_saas_stack import saas_stack_override_for_agent
from server.services.saas.tenant_guard import SubscriberPrincipal, subscriber_workspace_tenant_id


def dev_sandbox_e164() -> str | None:
    v = (get_settings().telnyx_phone_number or "").strip()
    return v or None


def is_dev_sandbox_line(e164: str | None, user_email: str | None) -> bool:
    sandbox = dev_sandbox_e164()
    if not sandbox or not e164:
        return False
    return is_dev_tester_email(user_email) and e164.strip() == sandbox


async def resolve_outbound_from_e164(
    tenant_id: uuid.UUID,
    agent_id: str,
    from_e164: str | None,
    *,
    user_email: str | None = None,
) -> str:
    """Pick caller ID: explicit fromE164, else agent-assigned DID, else any outbound-enabled tenant number."""
    if from_e164 and from_e164.strip():
        explicit = from_e164.strip()
        if not is_dev_sandbox_line(explicit, user_email):
            await assert_from_number(tenant_id, explicit)
        return explicit
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
    from server.config.env import get_settings

    settings = get_settings()
    platform_cap = max(1, min(20, int(settings.saas_max_concurrent_pstn or 20)))
    max_pstn = max(1, min(platform_cap, int(limits.get("max_concurrent_pstn") or platform_cap)))
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
                detail={"error": {"code": "concurrency_limit", "message": "Too many active calls", "retry_after": 15}},
                headers={"Retry-After": "15"},
            )


async def subscriber_outbound(
    principal: SubscriberPrincipal,
    *,
    agent_id: str,
    from_e164: str | None,
    to_e164: str,
    dial_request_id: str | None = None,
    contact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import uuid

    if not (dial_request_id or "").strip():
        dial_request_id = str(uuid.uuid4())
    from server.routes.dev_telephony import OutboundTestBody, _outbound_telnyx
    from server.services.saas.call_callback_service import resolve_workspace_agent
    from server.services.telephony import active_telephony_provider, telephony_guard_error

    workspace_tid = subscriber_workspace_tenant_id(principal)
    # Placing a real PSTN call is a compliance-gated action: it uses a customer
    # number and can reach anyone. Browser practice calls stay ungated.
    from server.services.saas.kyc_gate import assert_kyc_approved

    await assert_kyc_approved(principal, action="place a phone call")
    # An unknown or foreign agent must be a clean 404, never a leaked 500.
    agent = await resolve_workspace_agent(agent_id, str(workspace_tid))
    status = str(agent.get("status") or "").strip().lower()
    if status in {"paused", "inactive", "disabled"}:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "agent_paused",
                    "message": "This agent is paused. Switch it to Live before placing a call.",
                }
            },
        )
    if not agent.get("active_compiled_brain_version"):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "brain_not_published", "message": "Publish agent brain before calling"}},
        )
    from server.services.saas.billing_wallet_service import assert_wallet_allows_pstn

    await assert_wallet_allows_pstn(principal.tenant_id)
    resolved_from = await resolve_outbound_from_e164(
        workspace_tid,
        agent_id,
        from_e164,
        user_email=principal.email,
    )
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

    stack = await saas_stack_override_for_agent(agent)
    lang = str(stack.get("language") or (agent.get("languages") or ["te-IN"])[0])
    body = OutboundTestBody(
        agentId=agent_id,
        fromE164=resolved_from,
        toE164=to_e164.strip(),
        tier="medium",
        language=lang,
        stackOverride=stack,
        inheritTestStudioConfig=False,
        contact=contact,
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
            from server.services.outbound_dial_attempt import execute_dial_attempt
            return await execute_dial_attempt(
                request_id=dial_request_id,
                scope=f"app:{principal.tenant_id}:{principal.user_id}:{provider}",
                payload={"agent": agent_id, "from": resolved_from, "to": to_number, "stack": stack},
                operation=lambda: _outbound_telnyx(body, session_stub),
            )
        return {"ok": False, "error": f"Provider {provider} not supported for subscriber PSTN yet"}
    finally:
        release_outbound_slot(provider, to_number)
