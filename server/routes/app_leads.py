"""CRM leads — tenant-scoped (PRD-08 Phase 7)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.db.connection import get_session_factory
from server.db.models.saas_models import Lead
from server.services.saas.tenant_guard import SubscriberPrincipal, require_subscriber_permission

router = APIRouter()


class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1)
    phone: str | None = None
    email: str | None = None
    stage: str = "new"
    notes: str | None = None


class LeadStagePatch(BaseModel):
    stage: str = Field(..., min_length=1)


class LeadNotesPatch(BaseModel):
    notes: str | None = None


def _lead_dict(row: Lead) -> dict:
    return {
        "leadId": str(row.lead_id),
        "name": row.name,
        "phone": row.phone,
        "email": row.email,
        "stage": row.stage,
        "notes": row.notes,
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
    }


@router.get("/api/leads")
async def list_leads(principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        return {"leads": []}
    async with factory() as session:
        result = await session.execute(
            select(Lead).where(Lead.tenant_id == principal.tenant_id).order_by(Lead.updated_at.desc()).limit(500)
        )
        return {"leads": [_lead_dict(r) for r in result.scalars()]}


@router.post("/api/leads")
async def create_lead(body: LeadCreate, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    now = datetime.now(timezone.utc)
    async with factory() as session:
        row = Lead(
            tenant_id=principal.tenant_id,
            name=body.name.strip(),
            phone=body.phone,
            email=body.email,
            stage=body.stage,
            notes=body.notes,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return {"ok": True, "lead": _lead_dict(row)}


@router.patch("/api/leads/{lead_id}/stage")
async def patch_lead_stage(
    lead_id: str,
    body: LeadStagePatch,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.get(Lead, uuid.UUID(lead_id))
        if row is None or row.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        row.stage = body.stage
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
    return {"ok": True}


@router.patch("/api/leads/{lead_id}")
async def patch_lead(
    lead_id: str,
    body: LeadNotesPatch,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),
):
    require_subscriber_permission(principal, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.get(Lead, uuid.UUID(lead_id))
        if row is None or row.tenant_id != principal.tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        if body.notes is not None:
            row.notes = body.notes
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
    return {"ok": True, "lead": _lead_dict(row)}
