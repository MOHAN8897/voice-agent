"""Subscriber telephony API (PRD-05, PRD-04)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Call
from server.db.models.phase5_models import PhoneNumber
from server.db.models.saas_models import TelephonyContact
from server.services.saas.number_purchase_service import (
    create_purchase_checkout,
    get_purchase,
    purchase_with_wallet,
)
from server.services.saas.dev_tester_workspace import ensure_dev_tester_phone_line
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)
from server.services.saas.voice_catalog import phone_voice_catalog
from server.services.saas.telephony_orchestrator import subscriber_outbound
from server.config.constants import constants
from server.utils.rate_limiter import RateLimiter, raise_rate_limited

router = APIRouter()
_outbound_limiter = RateLimiter(max_requests=12, window_s=60)
_buy_limiter = RateLimiter(max_requests=8, window_s=3600)


class OutboundCallBody(BaseModel):
    agentId: str
    fromE164: str | None = None
    toE164: str

    @model_validator(mode="before")
    @classmethod
    def reject_stack_fields(cls, data):
        if isinstance(data, dict):
            for key in ("stackOverride", "stack_override", "tier", "pipeline"):
                if key in data:
                    raise ValueError(f"{key} not allowed for subscriber calls")
        return data


class BuyNumberBody(BaseModel):
    e164: str = Field(..., min_length=8)
    country: str = Field("IN", max_length=8)
    payMethod: str = Field("wallet")
    assignAgentId: str | None = None


class AssignNumberBody(BaseModel):
    agentId: str | None = None


class RoutingBody(BaseModel):
    agentId: str | None = None
    inboundEnabled: bool | None = None
    outboundEnabled: bool | None = None


class ContactBody(BaseModel):
    name: str
    phone: str
    notes: str | None = None


@router.post("/api/telephony/calls/outbound")
async def telephony_outbound(body: OutboundCallBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    settings = get_settings()
    if not settings.saas_telephony_enabled:
        raise HTTPException(status_code=503, detail={"error": {"code": "telephony_disabled", "message": "Telephony disabled"}})
    allowed, retry = _outbound_limiter.allow(f"out:{principal.tenant_id}")
    if not allowed:
        raise_rate_limited(retry, "Outbound call rate limit reached. Wait and try again.")
    return await subscriber_outbound(
        principal,
        agent_id=body.agentId,
        from_e164=body.fromE164,
        to_e164=body.toE164,
    )


@router.post("/api/calls/outbound")
async def calls_outbound_alias(body: OutboundCallBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    return await telephony_outbound(body, principal)


@router.get("/api/telephony/voice-options")
async def telephony_voice_options(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    """Subscriber-safe voice list for the production phone AI stack (no dev stack UI)."""
    languages = [
        {"code": code, "label": label}
        for code, label in constants.SUPPORTED_LANGUAGES.items()
    ]
    return {
        "stackLabel": "Live phone AI",
        "stackDescription": "Same voice engine for incoming calls, outgoing calls, and browser practice calls.",
        "defaultVoiceId": "marin",
        "voices": phone_voice_catalog(),
        "languages": languages,
    }


@router.get("/api/telephony/numbers")
async def list_numbers(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    workspace_tid = subscriber_workspace_tenant_id(principal)
    await ensure_dev_tester_phone_line(workspace_tid, principal.email)
    factory = get_session_factory()
    if factory is None:
        return {"numbers": []}
    async with factory() as session:
        result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == workspace_tid,
                PhoneNumber.released_at.is_(None),
            )
        )
        numbers = []
        settings = get_settings()
        monthly_usd = round(settings.did_monthly_usd_cents / 100.0, 2)
        monthly_inr = round(settings.did_monthly_inr_paise / 100.0, 2)
        for n in result.scalars():
            numbers.append(
                {
                    "id": str(n.id),
                    "e164": n.e164,
                    "status": n.status,
                    "agentId": str(n.agent_id) if n.agent_id else None,
                    "inboundEnabled": n.inbound_enabled,
                    "outboundEnabled": n.outbound_enabled,
                    "billingSource": n.billing_source,
                    "monthlyCost": monthly_usd,
                    "monthlyInr": monthly_inr,
                }
            )
    return {"numbers": numbers}


@router.get("/api/telephony/numbers/search")
async def search_numbers(
    country: str = "IN",
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    from server.services.telnyx_client import TelnyxClient

    client = TelnyxClient()
    numbers = await client.search_available_numbers(country=country, limit=10)
    settings = get_settings()
    monthly_inr = round(settings.did_monthly_inr_paise / 100.0, 2)
    monthly_usd = round(settings.did_monthly_usd_cents / 100.0, 2)
    priced = []
    for row in numbers:
        item = dict(row) if isinstance(row, dict) else {"e164": str(row)}
        item.setdefault("monthlyInr", monthly_inr)
        item.setdefault("monthlyUsd", monthly_usd)
        item.setdefault("fee", monthly_usd)
        priced.append(item)
    return {"numbers": priced, "didMonthlyInr": monthly_inr, "didMonthlyUsd": monthly_usd}


@router.post("/api/telephony/buy")
async def buy_number(body: BuyNumberBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.write")
    allowed, retry = _buy_limiter.allow(f"buy:{principal.tenant_id}")
    if not allowed:
        raise_rate_limited(retry, "Number purchase rate limit reached.")
    pay = (body.payMethod or "wallet").strip().lower()
    try:
        if pay == "stripe":
            return await create_purchase_checkout(
                principal,
                e164=body.e164,
                country_code=body.country,
                assign_agent_id=body.assignAgentId,
            )
        return await purchase_with_wallet(
            principal,
            e164=body.e164,
            country_code=body.country,
            assign_agent_id=body.assignAgentId,
        )
    except HTTPException:
        raise
    except ValueError as e:
        code = str(e)
        if code == "verification_required":
            status = 403
        elif code == "stripe_not_configured":
            status = 503
        elif code == "insufficient_balance":
            status = 402
        else:
            status = 400
        messages = {
            "stripe_not_configured": "Card checkout is not configured. Use wallet credits to buy a number.",
            "verification_required": "Verify your email before buying a number.",
            "number_reserved": "This number is reserved by another checkout. Try a different number.",
            "number_unavailable": "This number is no longer available.",
            "number_limit": "This workspace has reached its phone number limit.",
            "invalid_e164": "Enter a valid E.164 number.",
            "invalid_agent": "Choose a valid agent to assign this number to.",
            "insufficient_balance": "Add funds to your wallet before buying a number.",
        }
        raise HTTPException(
            status_code=status,
            detail={"error": {"code": code, "message": messages.get(code, code)}},
        )


@router.get("/api/telephony/purchases/{purchase_id}")
async def get_purchase_status(purchase_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    row = await get_purchase(uuid.UUID(purchase_id), principal.tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
    return row


@router.post("/api/telephony/numbers/{number_id}/assign")
async def assign_number(
    number_id: str,
    body: AssignNumberBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    try:
        number_uuid = uuid.UUID(number_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_number_id", "message": "Invalid phone line id"}},
        )
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        pn = await session.get(PhoneNumber, number_uuid)
        if pn is None or pn.tenant_id != workspace_tid or pn.released_at is not None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        if pn.status not in ("active", "pending"):
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "number_not_assignable", "message": "Number is not active"}},
            )
        agent_id = (body.agentId or "").strip()
        if not agent_id:
            pn.agent_id = None
            await session.commit()
            return {"ok": True, "agentId": None}
        agent = await session.get(Agent, uuid.UUID(agent_id))
        if agent is None or agent.tenant_id != workspace_tid:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
        pn.agent_id = agent.agent_id
        await session.commit()
    return {"ok": True, "agentId": str(agent.agent_id)}


@router.put("/api/telephony/numbers/{number_id}/routing")
async def update_routing(
    number_id: str,
    body: RoutingBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        pn = await session.get(PhoneNumber, uuid.UUID(number_id))
        if pn is None or pn.tenant_id != workspace_tid:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        if body.agentId is not None:
            if body.agentId:
                agent = await session.get(Agent, uuid.UUID(body.agentId))
                if agent is None or agent.tenant_id != workspace_tid:
                    raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
                pn.agent_id = agent.agent_id
            else:
                pn.agent_id = None
        if body.inboundEnabled is not None:
            pn.inbound_enabled = body.inboundEnabled
        if body.outboundEnabled is not None:
            pn.outbound_enabled = body.outboundEnabled
        await session.commit()
    return {"ok": True}


@router.get("/api/telephony/contacts")
async def list_contacts(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    factory = get_session_factory()
    if factory is None:
        return {"contacts": []}
    async with factory() as session:
        result = await session.execute(
            select(TelephonyContact).where(TelephonyContact.tenant_id == principal.tenant_id)
        )
        return {
            "contacts": [
                {"contactId": str(c.contact_id), "name": c.name, "phone": c.phone, "notes": c.notes}
                for c in result.scalars()
            ]
        }


@router.post("/api/telephony/contacts")
async def create_contact(body: ContactBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    from datetime import datetime, timezone

    async with factory() as session:
        row = TelephonyContact(
            tenant_id=principal.tenant_id,
            name=body.name.strip(),
            phone=body.phone.strip(),
            notes=body.notes,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return {"ok": True, "contactId": str(row.contact_id)}


@router.get("/api/calls/{call_id}")
async def get_call_detail(call_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
    async with factory() as session:
        row = await session.get(Call, uuid.UUID(call_id))
        if row is None or row.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        return {
            "callId": str(row.call_id),
            "agentId": str(row.agent_id),
            "direction": row.direction,
            "channel": row.channel,
            "startedAt": row.started_at.isoformat(),
            "endedAt": row.ended_at.isoformat() if row.ended_at else None,
            "durationSec": row.duration_sec,
            "disposition": row.disposition,
            "endReason": row.end_reason,
        }


@router.patch("/api/telephony/contacts/{contact_id}")
async def patch_contact(
    contact_id: str,
    body: ContactBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.get(TelephonyContact, uuid.UUID(contact_id))
        if row is None or row.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        row.name = body.name.strip()
        row.phone = body.phone.strip()
        row.notes = body.notes
        await session.commit()
    return {"ok": True}


@router.post("/api/telephony/numbers/{number_id}/release")
async def release_number(number_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    from datetime import datetime, timezone

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    workspace_tid = subscriber_workspace_tenant_id(principal)
    now = datetime.now(timezone.utc)
    async with factory() as session:
        pn = await session.get(PhoneNumber, uuid.UUID(number_id))
        if pn is None or pn.tenant_id != workspace_tid:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        pn.released_at = now
        pn.status = "released"
        pn.inbound_enabled = False
        pn.outbound_enabled = False
        pn.agent_id = None
        await session.commit()
    return {"ok": True}


@router.delete("/api/telephony/contacts/{contact_id}")
async def delete_contact(contact_id: str, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.get(TelephonyContact, uuid.UUID(contact_id))
        if row is None or row.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        await session.delete(row)
        await session.commit()
    return {"ok": True}
