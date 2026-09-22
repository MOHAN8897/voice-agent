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
from server.services.saas.number_purchase_service import create_purchase_checkout, get_purchase
from server.services.saas.tenant_guard import SubscriberPrincipal, require_subscriber_permission
from server.services.saas.telephony_orchestrator import subscriber_outbound

router = APIRouter()


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


class AssignNumberBody(BaseModel):
    agentId: str


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
    return await subscriber_outbound(
        principal,
        agent_id=body.agentId,
        from_e164=body.fromE164,
        to_e164=body.toE164,
    )


@router.post("/api/calls/outbound")
async def calls_outbound_alias(body: OutboundCallBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    return await telephony_outbound(body, principal)


@router.get("/api/telephony/numbers")
async def list_numbers(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    factory = get_session_factory()
    if factory is None:
        return {"numbers": []}
    async with factory() as session:
        result = await session.execute(
            select(PhoneNumber).where(
                PhoneNumber.tenant_id == principal.tenant_id,
                PhoneNumber.released_at.is_(None),
            )
        )
        numbers = [
            {
                "id": str(n.id),
                "e164": n.e164,
                "status": n.status,
                "agentId": str(n.agent_id) if n.agent_id else None,
                "inboundEnabled": n.inbound_enabled,
                "outboundEnabled": n.outbound_enabled,
            }
            for n in result.scalars()
        ]
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
    return {"numbers": numbers}


@router.post("/api/telephony/buy")
async def buy_number(body: BuyNumberBody, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.billing.write")
    try:
        return await create_purchase_checkout(principal, e164=body.e164, country_code=body.country)
    except ValueError as e:
        code = str(e)
        if code == "verification_required":
            status = 402
        elif code == "stripe_not_configured":
            status = 503
        else:
            status = 400
        message = (
            "Stripe checkout is not configured for number purchases. Set STRIPE_SECRET_KEY and checkout URLs."
            if code == "stripe_not_configured"
            else code
        )
        raise HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


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
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        pn = await session.get(PhoneNumber, uuid.UUID(number_id))
        if pn is None or pn.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        agent = await session.get(Agent, uuid.UUID(body.agentId))
        if agent is None or agent.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
        pn.agent_id = agent.agent_id
        await session.commit()
    return {"ok": True}


@router.put("/api/telephony/numbers/{number_id}/routing")
async def update_routing(
    number_id: str,
    body: RoutingBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        pn = await session.get(PhoneNumber, uuid.UUID(number_id))
        if pn is None or pn.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        if body.agentId is not None:
            if body.agentId:
                agent = await session.get(Agent, uuid.UUID(body.agentId))
                if agent is None or agent.tenant_id != principal.tenant_id:
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
            "disposition": row.disposition,
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
    now = datetime.now(timezone.utc)
    async with factory() as session:
        pn = await session.get(PhoneNumber, uuid.UUID(number_id))
        if pn is None or pn.tenant_id != principal.tenant_id:
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
