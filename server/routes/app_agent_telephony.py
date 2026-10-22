"""Agent telephony configuration API — operational phone settings.

Separate from ``agents_business_brain`` on purpose: this is how the *phone* behaves,
not how the *agent* thinks. Every route is tenant-scoped through
``load_agent_for_tenant``, so an agent id from another workspace is a 404.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.services.saas.telephony_profile import (
    AFTER_HOURS_ACTIONS,
    DEFAULT_TIMEZONE,
    TelephonyProfileError,
    get_or_create_profile,
    get_profile,
    public_profile,
    update_profile,
    validate_policy_payload,
)
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    load_agent_for_tenant,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)

router = APIRouter()


class BusinessHoursBody(BaseModel):
    businessHours: dict[str, list[dict[str, str]]] = Field(default_factory=dict)


class TelephonyProfileBody(BaseModel):
    greetingPhrase: str | None = Field(None, max_length=500)
    businessHours: dict[str, Any] | None = None
    closedDates: list[str] | None = None
    timezone: str | None = Field(None, max_length=64)
    afterHoursAction: str | None = Field(None, max_length=24)
    transferNumber: str | None = Field(None, max_length=32)
    inboundEnabled: bool | None = None
    outboundEnabled: bool | None = None


def _fail(exc: TelephonyProfileError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": {"code": "invalid_telephony_profile", "message": str(exc)}},
    )


@router.get("/api/agents/{agent_id}/telephony-profile")
async def read_telephony_profile(
    agent_id: str,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.calls.read")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    await load_agent_for_tenant(agent_id, workspace_tid)
    profile = await get_or_create_profile(agent_id, workspace_tid)
    return {"profile": public_profile(profile), "afterHoursActions": list(AFTER_HOURS_ACTIONS)}


@router.put("/api/agents/{agent_id}/telephony-profile")
async def write_telephony_profile(
    agent_id: str,
    body: TelephonyProfileBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    await load_agent_for_tenant(agent_id, workspace_tid)

    hours = dict(body.businessHours or {})
    if body.closedDates is not None:
        hours["closed"] = body.closedDates
    payload = validate_policy_payload(
        {
            "greeting_phrase": body.greetingPhrase,
            "business_hours": hours if (body.businessHours is not None or body.closedDates is not None) else None,
            "timezone": body.timezone,
            "after_hours_action": body.afterHoursAction,
            "transfer_number": body.transferNumber,
            "inbound_enabled": body.inboundEnabled,
            "outbound_enabled": body.outboundEnabled,
        }
    )
    try:
        profile = await update_profile(agent_id, workspace_tid, payload)
    except TelephonyProfileError as exc:
        raise _fail(exc)
    return {"ok": True, "profile": public_profile(profile)}


@router.get("/api/agents/{agent_id}/telephony-profile/effective")
async def effective_telephony_profile(
    agent_id: str,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    """What the live inbound path would decide right now, and why.

    Lets the console show the real runtime decision instead of implying the
    settings are decorative.
    """
    require_subscriber_permission(principal, "app.calls.read")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    await load_agent_for_tenant(agent_id, workspace_tid)
    profile = await get_profile(agent_id)
    from server.services.saas.telephony_profile import default_decision, evaluate_inbound_policy

    decision = evaluate_inbound_policy(profile)
    return {
        "decision": decision.to_dict(),
        "hasProfile": profile is not None,
        "timezone": (profile or {}).get("timezone") or DEFAULT_TIMEZONE,
    }
