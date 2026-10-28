"""CRM leads — tenant-scoped (PRD-08 Phase 7)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.db.connection import get_session_factory
from server.db.models.entities import Agent
from server.db.models.saas_models import Lead
from server.services.saas.tenant_guard import SubscriberPrincipal, require_subscriber_permission
from server.services.saas.lead_scoring import enrich_leads, retire_converted_followups

router = APIRouter()
LeadStage = Literal["new", "contacted", "qualified", "meeting_booked", "converted", "unqualified"]


class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=320)
    stage: LeadStage = "new"
    confirmConverted: bool = False
    notes: str | None = Field(None, max_length=20000)
    #: Which AI employee owns this lead. Optional — a hand-created CRM lead may
    #: belong to the workspace rather than to one agent.
    agentId: str | None = Field(None, max_length=36)


class LeadStagePatch(BaseModel):
    stage: LeadStage
    confirmConverted: bool = False
    expectedUpdatedAt: datetime | None = None


class LeadNotesPatch(BaseModel):
    notes: str | None = Field(None, max_length=20000)
    stage: LeadStage | None = None
    confirmConverted: bool = False
    agentId: str | None = Field(None, max_length=36)
    expectedUpdatedAt: datetime | None = None


def _check_revision(row: Lead, expected: datetime | None) -> None:
    current = row.updated_at if row.updated_at.tzinfo else row.updated_at.replace(tzinfo=timezone.utc)
    if expected is not None and current != (expected if expected.tzinfo else expected.replace(tzinfo=timezone.utc)):
        raise HTTPException(status_code=409, detail="This lead changed. Reload it before saving; your edits have been kept.")


def _lead_dict(row: Lead) -> dict:
    return {
        "leadId": str(row.lead_id),
        # Ownership is what scopes a lead to one agent workspace. Returning it is
        # not optional: the console filters by it, and a lead with no owner simply
        # never matches an agent, which silently reads as "this agent has no leads".
        "agentId": row.agent_id,
        "name": row.name,
        "phone": row.phone,
        "email": row.email,
        "stage": row.stage,
        "notes": row.notes,
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
    }


def _lead_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=404, detail="Lead not found") from None


async def _check_agent(session, agent_id: str | None, tenant_id) -> None:
    if not agent_id:
        return
    agent = await session.scalar(select(Agent.agent_id).where(
        Agent.agent_id == _lead_uuid(agent_id), Agent.tenant_id == tenant_id,
    ))
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/api/leads")
async def list_leads(
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
    agentId: Annotated[str | None, Query(alias="agentId", max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    stage: Annotated[LeadStage | None, Query()] = None,
    search: Annotated[str, Query(max_length=200)] = "",
    hasPhone: Annotated[bool | None, Query()] = None,
    updatedSince: Annotated[datetime | None, Query()] = None,
    sort: Annotated[Literal["updated", "created", "name"], Query()] = "updated",
):
    """Leads for the workspace, or for one agent when `agentId` is given.

    The filter is a real query, not a client-side one: an agent workspace must
    never receive another agent's leads in the payload, even briefly.
    """
    require_subscriber_permission(principal, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        return {"leads": [], "total": 0, "stageCounts": {}, "limit": limit, "offset": offset}
    async with factory() as session:
        stmt = select(Lead).where(Lead.tenant_id == principal.tenant_id)
        if agentId == "unassigned":
            stmt = stmt.where(Lead.agent_id.is_(None))
        elif agentId:
            stmt = stmt.where(Lead.agent_id == agentId)
        if stage:
            stmt = stmt.where(Lead.stage == stage)
        if search.strip():
            stmt = stmt.where(or_(*(column.icontains(search.strip(), autoescape=True)
                for column in (Lead.name, Lead.phone, Lead.email, Lead.notes))))
        phone_present = func.length(func.trim(func.coalesce(Lead.phone, ""))) > 0
        if hasPhone is not None:
            stmt = stmt.where(phone_present if hasPhone else ~phone_present)
        if updatedSince:
            stmt = stmt.where(Lead.updated_at >= updatedSince)
        # Counts use the same tenant and filters as the paginated data.
        counts = (await session.execute(stmt.with_only_columns(Lead.stage, func.count())
            .group_by(Lead.stage))).all()
        stage_counts = dict(counts)
        ordering = {"updated": Lead.updated_at.desc(), "created": Lead.created_at.desc(), "name": Lead.name.asc()}[sort]
        result = await session.execute(stmt.order_by(ordering, Lead.lead_id).limit(limit).offset(offset))
        items = [_lead_dict(r) for r in result.scalars()]
        return {"leads": await enrich_leads(items, principal.tenant_id), "total": sum(stage_counts.values()),
            "stageCounts": stage_counts, "limit": limit, "offset": offset}


@router.post("/api/leads")
async def create_lead(body: LeadCreate, principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)]):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    now = datetime.now(timezone.utc)
    async with factory() as session:
        if not body.name.strip():
            raise HTTPException(status_code=422, detail="Name is required")
        if body.stage == "converted" and not body.confirmConverted:
            raise HTTPException(status_code=409, detail="Confirm conversion before creating a converted lead")
        await _check_agent(session, body.agentId, principal.tenant_id)
        row = Lead(
            tenant_id=principal.tenant_id,
            agent_id=(body.agentId or None),
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
    return {"ok": True, "lead": (await enrich_leads([_lead_dict(row)], principal.tenant_id))[0]}


@router.patch("/api/leads/{lead_id}/stage")
async def patch_lead_stage(
    lead_id: str,
    body: LeadStagePatch,
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.scalar(select(Lead).where(Lead.lead_id == _lead_uuid(lead_id), Lead.tenant_id == principal.tenant_id).with_for_update())
        if row is None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        _check_revision(row, body.expectedUpdatedAt)
        if body.stage == "converted" and row.stage != "converted" and not body.confirmConverted:
            raise HTTPException(status_code=409, detail="Confirm that this lead became a customer before marking Converted")
        row.stage = body.stage
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
    if row.stage == "converted":
        await retire_converted_followups(principal.tenant_id, row.phone)
    return {"ok": True}


@router.patch("/api/leads/{lead_id}")
async def patch_lead(
    lead_id: str,
    body: LeadNotesPatch,
    principal: Annotated[SubscriberPrincipal, Depends(require_subscriber_jwt)],
):
    require_subscriber_permission(principal, "app.telephony.write")
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    async with factory() as session:
        row = await session.scalar(select(Lead).where(Lead.lead_id == _lead_uuid(lead_id), Lead.tenant_id == principal.tenant_id).with_for_update())
        if row is None:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
        _check_revision(row, body.expectedUpdatedAt)
        if "notes" in body.model_fields_set:
            row.notes = body.notes
        if "agentId" in body.model_fields_set:
            await _check_agent(session, body.agentId, principal.tenant_id)
            row.agent_id = body.agentId or None
        if body.stage is not None:
            if body.stage == "converted" and row.stage != "converted" and not body.confirmConverted:
                raise HTTPException(status_code=409, detail="Confirm that this lead became a customer before marking Converted")
            row.stage = body.stage
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
    if row.stage == "converted":
        await retire_converted_followups(principal.tenant_id, row.phone)
    return {"ok": True, "lead": (await enrich_leads([_lead_dict(row)], principal.tenant_id))[0]}
