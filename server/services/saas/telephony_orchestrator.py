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
    settings = get_settings()
    from server.services.telephony import active_telephony_provider
    prov = active_telephony_provider()
    if prov == "vobiz":
        v = (getattr(settings, "vobiz_phone_number", None) or "+917965480745").strip()
        return v or None
    v = (settings.telnyx_phone_number or "").strip()
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
                # A suspended (unpaid rental) or releasing line must never be
                # picked — and silently re-enabled — as caller ID.
                PhoneNumber.status.in_(("active", "pending")),
            ).limit(1)
        )
        row = result.scalars().first()
        if row:
            if not row.outbound_enabled:
                row.outbound_enabled = True
                await session.commit()
            return row.e164
        result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == tenant_id,
                PhoneNumber.released_at.is_(None),
                PhoneNumber.status.in_(("active", "pending")),
            )
        )
        any_row = result.scalars().first()
        if any_row:
            if not any_row.outbound_enabled:
                any_row.outbound_enabled = True
                await session.commit()
            return any_row.e164
    if is_dev_tester_email(user_email):
        sandbox = dev_sandbox_e164()
        if sandbox:
            return sandbox
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
        if row is None or row.status not in ("active", "pending"):
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "invalid_from_number", "message": "From number not available"}},
            )
        if not row.outbound_enabled:
            row.outbound_enabled = True
            await session.commit()
        return row


async def assert_concurrent_limit(tenant_id: uuid.UUID, limits: dict) -> None:
    from server.config.env import get_settings

    settings = get_settings()
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        from server.db.models.entities import Tenant
        from server.services.saas import concurrency_service as channels

        tenant = await session.get(Tenant, tenant_id)
        if tenant is not None:
            max_pstn = (await channels.channel_cap(session, tenant, settings=settings))["cap"]
        else:
            max_pstn = channels.legacy_caps(settings, limits)[0]
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
        await channels.record_daily(factory, tenant_id, active=count, cap=max_pstn, rejected=1)
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "concurrency_limit", "message": "All concurrent call channels are in use", "retry_after": 15}},
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
    # Vobiz owns telecom KYC; retain the configured platform gate for other carriers.
    provider = active_telephony_provider()
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
    from server.services.saas.telephony_profile import get_profile

    telephony_profile = await get_profile(agent_id)
    if telephony_profile is not None and telephony_profile.get("outbound_enabled") is False:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "agent_outbound_disabled",
                    "message": "Outbound calls are disabled for this agent in Telephony Settings.",
                }
            },
        )
    if not agent.get("active_compiled_brain_version"):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "brain_not_published", "message": "Publish agent brain before calling"}},
        )
    from server.services.saas.billing_wallet_service import assert_wallet_allows_pstn

    if provider == "vobiz":
        from server.services.saas.platform_admins import is_dev_tester_email
        if not is_dev_tester_email(principal.email):
            from server.services.saas.voice_kyc_service import assert_voice_kyc_approved
            await assert_voice_kyc_approved(principal.tenant_id, action="place a phone call")
    else:
        from server.services.saas.kyc_gate import assert_kyc_approved
        await assert_kyc_approved(principal, action="place a phone call")
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
    if provider != "vobiz":
        await assert_concurrent_limit(principal.tenant_id, limits)

    guard = telephony_guard_error(provider)
    if guard:
        return {"ok": False, "error": "Phone service is temporarily unavailable. Please contact support.", "code": "phone_service_unavailable"}

    # Normalize destination number to clean E.164 (strip spaces, hyphens, parentheses)
    clean_to = (to_e164 or "").strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if clean_to.startswith("00"):
        clean_to = f"+{clean_to[2:]}"
    elif not clean_to.startswith("+"):
        digits = "".join(c for c in clean_to if c.isdigit())
        clean_to = f"+91{digits}" if len(digits) == 10 else (f"+{digits}" if digits else clean_to)

    try:
        stack = await saas_stack_override_for_agent(agent)
    except Exception as exc:
        from server.services.saas.voice_setup_errors import voice_setup_error

        setup_error = voice_setup_error(exc)
        if setup_error:
            raise HTTPException(status_code=409, detail={"error": setup_error}) from exc
        raise
    lang = str(stack.get("language") or (agent.get("languages") or ["te-IN"])[0])
    saved_voice_settings = agent.get("voice_settings") if isinstance(agent.get("voice_settings"), dict) else (agent.get("voiceSettings") if isinstance(agent.get("voiceSettings"), dict) else {})
    raw_tier = agent.get("default_tier") or agent.get("defaultTier") or "medium"
    tier = str(raw_tier) if saved_voice_settings.get("stackSelectionVersion") == 1 else "medium"
    snapshot = stack.get("_voice_stack_snapshot") if isinstance(stack, dict) else None
    if isinstance(snapshot, dict) and snapshot.get("tier"):
        tier = str(snapshot["tier"])
    body = OutboundTestBody(
        agentId=agent_id,
        fromE164=resolved_from,
        toE164=clean_to,
        tier=tier,
        language=lang,
        stackOverride=stack,
        inheritTestStudioConfig=False,
        contact=contact,
    )
    async def before_dial_check():
        from server.services.saas.predial_policy import assert_predial_policy
        await assert_predial_policy(principal, agent_id=agent_id, phone=clean_to,
                                    contact=contact, request_id=dial_request_id)
    body._before_dial_check = before_dial_check
    session_stub = SessionData(
        kind="app",
        subject=str(principal.user_id),
        tenant_id=str(principal.tenant_id),
        role=principal.role,
        issued_at=0,
    )
    from server.services.outbound_dial_guard import acquire_outbound_slot, release_outbound_slot

    to_number = body.to_e164.strip()
    if factory:
        from server.db.models.phase5_models import DncEntry
        from sqlalchemy import select

        async with factory() as session:
            dnc_hit = (
                await session.execute(
                    select(DncEntry.id)
                    .where(
                        DncEntry.tenant_id == workspace_tid,
                        DncEntry.phone_e164 == to_number,
                        DncEntry.active.is_(True),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not dnc_hit and not to_number.startswith("+"):
                alt = f"+{to_number}"
                dnc_hit = (
                    await session.execute(
                        select(DncEntry.id)
                        .where(
                            DncEntry.tenant_id == workspace_tid,
                            DncEntry.phone_e164 == alt,
                            DncEntry.active.is_(True),
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
        if dnc_hit:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "dnc_blocked",
                        "message": "This phone number is on your tenant's Do Not Call (DND) list.",
                    }
                },
            )

    if provider == "vobiz":
        from server.routes.dev_telephony import _outbound_vobiz
        from server.services.saas.call_admission import execute

        async def dial(admission_key):
            body.admission_key = admission_key
            result = await _outbound_vobiz(body, session_stub, number_tenant_id=workspace_tid)
            if isinstance(result, dict) and not result.get("ok"):
                result["error"] = _sanitize_tenant_dial_error(str(result.get("error") or ""))
            return result

        return await execute(
            tenant_id=principal.tenant_id, request_id=dial_request_id, provider=provider,
            payload={"agent": agent_id, "from": resolved_from, "to": to_number, "stack": stack, "contact": contact},
            operation=dial,
        )

    if not await acquire_outbound_slot(provider, to_number):
        return {
            "ok": False,
            "error": "An outbound call to this number is already in progress.",
            "code": "dial_in_progress",
        }
    try:
        res = None
        if provider == "telnyx":
            from server.services.outbound_dial_attempt import execute_dial_attempt
            res = await execute_dial_attempt(
                request_id=dial_request_id,
                scope=f"app:{principal.tenant_id}:{principal.user_id}:{provider}",
                payload={"agent": agent_id, "from": resolved_from, "to": to_number, "stack": stack},
                operation=lambda: _outbound_telnyx(body, session_stub),
            )
        else:
            return {"ok": False, "error": f"Provider {provider} not supported for subscriber PSTN yet"}

        if res and isinstance(res, dict) and not res.get("ok"):
            err = str(res.get("error") or "")
            res["error"] = _sanitize_tenant_dial_error(err)
        return res
    finally:
        release_outbound_slot(provider, to_number)


def _sanitize_tenant_dial_error(raw_err: str) -> str:
    raw_lower = raw_err.lower()
    if "balance" in raw_lower or "credit" in raw_lower:
        return "Telephony service is temporarily unavailable. Please contact support."
    if "rate limit" in raw_lower or "concurrency" in raw_lower:
        return "Call limit reached. Please wait a moment and try again."
    if "invalid" in raw_lower and ("phone" in raw_lower or "number" in raw_lower or "destination" in raw_lower):
        return "Please verify that the dialed phone number is valid and in standard format."
    if "timeout" in raw_lower:
        return "Telephony connection timed out. Please try again shortly."
    if "unreachable" in raw_lower or "network" in raw_lower:
        return "The destination carrier is currently unreachable. Please try again later."
    if "{" in raw_err or "http" in raw_lower or "vobiz api" in raw_lower or "telnyx api" in raw_lower or "exception" in raw_lower:
        return "Unable to connect call at this moment. Please verify the destination number and try again."
    return raw_err[:180]
