"""Campaign + DNC + phone number APIs — Phase 5 (+ SaaS tenant context)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from server.auth.api_tenant import ApiTenantContext, require_api_tenant
from server.auth.rbac import require_role_permission
from server.db.connection import get_session_factory
from server.db.models.entities import Agent
from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, DncEntry, PhoneNumber

router = APIRouter()


class CampaignCreate(BaseModel):
    name: str
    agent_id: str = Field(..., alias="agentId")
    concurrency: int = 5

    model_config = {"populate_by_name": True}


class CampaignStatusPatch(BaseModel):
    status: str = Field(..., min_length=1)


class ContactImport(BaseModel):
    contacts: list[dict[str, Any]] = Field(default_factory=list)


class DncBody(BaseModel):
    phone_e164: str = Field(..., alias="phoneE164")
    reason: str | None = None

    model_config = {"populate_by_name": True}


class PhoneNumberBody(BaseModel):
    e164: str


async def _campaign_for_tenant(db, campaign_id: str, tenant_id: uuid.UUID) -> Campaign:
    result = await db.execute(select(Campaign).where(Campaign.campaign_id == uuid.UUID(campaign_id)))
    camp = result.scalar_one_or_none()
    if camp is None or camp.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Campaign not found"}})
    return camp


@router.get("/api/campaigns")
async def list_campaigns(ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        return {"campaigns": []}
    async with factory() as db:
        result = await db.execute(select(Campaign).where(Campaign.tenant_id == ctx.tenant_id))
        rows = result.scalars().all()
        return {
            "campaigns": [
                {
                    "campaignId": str(r.campaign_id),
                    "campaign_id": str(r.campaign_id),
                    "name": r.name,
                    "status": r.status,
                    "agentId": str(r.agent_id),
                    "agent_id": str(r.agent_id),
                    "concurrency": r.concurrency,
                }
                for r in rows
            ]
        }


@router.post("/api/campaigns")
async def create_campaign(body: CampaignCreate, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    cid = uuid.uuid4()
    async with factory() as db:
        agent = await db.get(Agent, uuid.UUID(body.agent_id))
        if agent is None or agent.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
        db.add(
            Campaign(
                campaign_id=cid,
                tenant_id=ctx.tenant_id,
                agent_id=agent.agent_id,
                name=body.name,
                status="draft",
                concurrency=body.concurrency,
            )
        )
        await db.commit()
    return {
        "ok": True,
        "campaignId": str(cid),
        "campaign_id": str(cid),
        "campaign": {
            "campaignId": str(cid),
            "campaign_id": str(cid),
            "name": body.name,
            "status": "draft",
            "agentId": str(agent.agent_id),
            "agent_id": str(agent.agent_id),
            "concurrency": body.concurrency,
        },
    }


@router.patch("/api/campaigns/{campaign_id}/status")
async def patch_campaign_status(
    campaign_id: str,
    body: CampaignStatusPatch,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False}
    async with factory() as db:
        camp = await _campaign_for_tenant(db, campaign_id, ctx.tenant_id)
        camp.status = body.status
        await db.commit()
    return {"ok": True, "status": body.status}


@router.post("/api/campaigns/{campaign_id}/contacts/import")
async def import_contacts(
    campaign_id: str,
    body: ContactImport,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    imported = 0
    async with factory() as db:
        await _campaign_for_tenant(db, campaign_id, ctx.tenant_id)
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
async def start_campaign(campaign_id: str, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    run_id = uuid.uuid4()
    async with factory() as db:
        camp = await _campaign_for_tenant(db, campaign_id, ctx.tenant_id)
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
    return {"ok": True, "runId": str(run_id), "run_id": str(run_id), "status": "running"}


@router.post("/api/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False}
    async with factory() as db:
        camp = await _campaign_for_tenant(db, campaign_id, ctx.tenant_id)
        camp.status = "paused"
        await db.commit()
    return {"ok": True, "status": "paused"}


@router.post("/api/campaigns/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: str, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False}
    async with factory() as db:
        camp = await _campaign_for_tenant(db, campaign_id, ctx.tenant_id)
        camp.status = "cancelled"
        await db.commit()
    return {"ok": True, "status": "cancelled"}


@router.get("/api/campaigns/{campaign_id}/analytics")
async def campaign_analytics(campaign_id: str, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        return {"attempts": 0, "connects": 0, "dispositions": {}}
    async with factory() as db:
        await _campaign_for_tenant(db, campaign_id, ctx.tenant_id)
        contacts = await db.execute(
            select(CampaignContact).where(CampaignContact.campaign_id == uuid.UUID(campaign_id))
        )
        rows = contacts.scalars().all()
        statuses: dict[str, int] = {}
        for r in rows:
            statuses[r.status] = statuses.get(r.status, 0) + 1
        return {"attempts": sum(statuses.values()), "connects": statuses.get("connected", 0), "dispositions": statuses}


@router.get("/api/dnc")
async def list_dnc(ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        return {"entries": []}
    async with factory() as db:
        result = await db.execute(select(DncEntry).where(DncEntry.tenant_id == ctx.tenant_id))
        return {"entries": [{"phone_e164": r.phone_e164, "reason": r.reason} for r in result.scalars().all()]}


@router.post("/api/dnc")
async def add_dnc(body: DncBody, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False}
    async with factory() as db:
        db.add(
            DncEntry(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                phone_e164=body.phone_e164,
                reason=body.reason,
            )
        )
        await db.commit()
    return {"ok": True}


@router.get("/api/phone-numbers")
async def list_phone_numbers(ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.integrations")
    factory = get_session_factory()
    if factory is None:
        return {"numbers": []}
    async with factory() as db:
        result = await db.execute(
            select(PhoneNumber).where(PhoneNumber.tenant_id == ctx.tenant_id, PhoneNumber.released_at.is_(None))
        )
        return {
            "numbers": [
                {
                    "id": str(r.id),
                    "e164": r.e164,
                    "status": r.status,
                    "agentId": str(r.agent_id) if r.agent_id else None,
                }
                for r in result.scalars().all()
            ]
        }


@router.post("/api/phone-numbers")
async def add_phone_number(body: PhoneNumberBody, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.integrations")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    nid = uuid.uuid4()
    async with factory() as db:
        db.add(
            PhoneNumber(
                id=nid,
                tenant_id=ctx.tenant_id,
                e164=body.e164,
                status="connected",
                billing_source="manual",
            )
        )
        await db.commit()
    return {"ok": True, "id": str(nid), "e164": body.e164, "status": "connected"}
