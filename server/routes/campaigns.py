"""Campaign + DNC + phone number APIs — Phase 5."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from server.auth.dependencies import require_app_session, require_permission
from server.auth.session import SessionData
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, DncEntry, PhoneNumber

router = APIRouter()


class CampaignCreate(BaseModel):
    name: str
    agent_id: str = Field(..., alias="agentId")
    concurrency: int = 5

    model_config = {"populate_by_name": True}


class ContactImport(BaseModel):
    contacts: list[dict[str, Any]] = Field(default_factory=list)


class DncBody(BaseModel):
    phone_e164: str = Field(..., alias="phoneE164")
    reason: str | None = None

    model_config = {"populate_by_name": True}


class PhoneNumberBody(BaseModel):
    e164: str


def _tenant_id(session: SessionData) -> uuid.UUID:
    settings = get_settings()
    raw = session.tenant_id or settings.default_tenant_id
    return uuid.UUID(raw)


@router.get("/api/campaigns")
async def list_campaigns(session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        return {"campaigns": []}
    tenant = _tenant_id(session)
    async with factory() as db:
        result = await db.execute(select(Campaign).where(Campaign.tenant_id == tenant))
        rows = result.scalars().all()
        return {
            "campaigns": [
                {
                    "campaign_id": str(r.campaign_id),
                    "name": r.name,
                    "status": r.status,
                    "agent_id": str(r.agent_id),
                    "concurrency": r.concurrency,
                }
                for r in rows
            ]
        }


@router.post("/api/campaigns")
async def create_campaign(body: CampaignCreate, session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    tenant = _tenant_id(session)
    cid = uuid.uuid4()
    async with factory() as db:
        db.add(
            Campaign(
                campaign_id=cid,
                tenant_id=tenant,
                agent_id=uuid.UUID(body.agent_id),
                name=body.name,
                status="draft",
                concurrency=body.concurrency,
            )
        )
        await db.commit()
    return {"ok": True, "campaign_id": str(cid)}


@router.post("/api/campaigns/{campaign_id}/contacts/import")
async def import_contacts(campaign_id: str, body: ContactImport, session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    imported = 0
    async with factory() as db:
        for c in body.contacts:
            phone = c.get("phone_e164") or c.get("phoneE164") or c.get("phone")
            if not phone:
                continue
            db.add(
                CampaignContact(
                    id=uuid.uuid4(),
                    campaign_id=uuid.UUID(campaign_id),
                    phone_e164=str(phone),
                    metadata_=c,
                )
            )
            imported += 1
        await db.commit()
    return {"ok": True, "imported": imported}


@router.post("/api/campaigns/{campaign_id}/start")
async def start_campaign(campaign_id: str, session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    run_id = uuid.uuid4()
    async with factory() as db:
        result = await db.execute(select(Campaign).where(Campaign.campaign_id == uuid.UUID(campaign_id)))
        camp = result.scalar_one_or_none()
        if camp is None:
            return {"ok": False, "error": {"code": "not_found", "message": "Campaign not found"}}
        camp.status = "running"
        db.add(
            CampaignRun(
                run_id=run_id,
                campaign_id=camp.campaign_id,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
    try:
        from worker.dialer import enqueue_campaign_run

        enqueue_campaign_run(campaign_id, str(run_id))
    except Exception:
        pass
    return {"ok": True, "run_id": str(run_id), "status": "running"}


@router.post("/api/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False}
    async with factory() as db:
        result = await db.execute(select(Campaign).where(Campaign.campaign_id == uuid.UUID(campaign_id)))
        camp = result.scalar_one_or_none()
        if camp:
            camp.status = "paused"
            await db.commit()
    return {"ok": True, "status": "paused"}


@router.post("/api/campaigns/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: str, session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False}
    async with factory() as db:
        result = await db.execute(select(Campaign).where(Campaign.campaign_id == uuid.UUID(campaign_id)))
        camp = result.scalar_one_or_none()
        if camp:
            camp.status = "cancelled"
            await db.commit()
    return {"ok": True, "status": "cancelled"}


@router.get("/api/campaigns/{campaign_id}/analytics")
async def campaign_analytics(campaign_id: str, session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        return {"attempts": 0, "connects": 0, "dispositions": {}}
    async with factory() as db:
        contacts = await db.execute(
            select(CampaignContact).where(CampaignContact.campaign_id == uuid.UUID(campaign_id))
        )
        rows = contacts.scalars().all()
        statuses: dict[str, int] = {}
        for r in rows:
            statuses[r.status] = statuses.get(r.status, 0) + 1
        return {"attempts": sum(statuses.values()), "connects": statuses.get("connected", 0), "dispositions": statuses}


@router.get("/api/dnc")
async def list_dnc(session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        return {"entries": []}
    tenant = _tenant_id(session)
    async with factory() as db:
        result = await db.execute(select(DncEntry).where(DncEntry.tenant_id == tenant))
        return {"entries": [{"phone_e164": r.phone_e164, "reason": r.reason} for r in result.scalars().all()]}


@router.post("/api/dnc")
async def add_dnc(body: DncBody, session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False}
    tenant = _tenant_id(session)
    async with factory() as db:
        db.add(DncEntry(id=uuid.uuid4(), tenant_id=tenant, phone_e164=body.phone_e164, reason=body.reason))
        await db.commit()
    return {"ok": True}


@router.get("/api/phone-numbers")
async def list_phone_numbers(session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.integrations")
    factory = get_session_factory()
    if factory is None:
        return {"numbers": []}
    tenant = _tenant_id(session)
    async with factory() as db:
        result = await db.execute(select(PhoneNumber).where(PhoneNumber.tenant_id == tenant))
        return {
            "numbers": [
                {"id": str(r.id), "e164": r.e164, "status": r.status, "plivo_number_id": r.plivo_number_id}
                for r in result.scalars().all()
            ]
        }


@router.post("/api/phone-numbers")
async def add_phone_number(body: PhoneNumberBody, session: SessionData = Depends(require_app_session)):
    require_permission(session, "app.integrations")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    tenant = _tenant_id(session)
    nid = uuid.uuid4()
    async with factory() as db:
        db.add(PhoneNumber(id=nid, tenant_id=tenant, e164=body.e164, status="connected"))
        await db.commit()
    return {"ok": True, "id": str(nid), "e164": body.e164, "status": "connected"}
