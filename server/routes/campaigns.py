"""Campaign + DNC + phone number APIs — Phase 5 (+ SaaS tenant context)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, AliasChoices
from sqlalchemy import select

from server.auth.api_tenant import ApiTenantContext, require_api_tenant
from server.auth.rbac import require_role_permission
from server.db.connection import get_session_factory
from server.db.models.entities import Agent
from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, DncEntry, PhoneNumber

router = APIRouter()


class CampaignCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    agent_id: str = Field(..., validation_alias=AliasChoices("agentId", "agent_id"))
    description: str | None = None
    default_country: str = Field("US", validation_alias=AliasChoices("defaultCountry", "default_country"))
    concurrency: int = 5
    max_attempts: int | None = Field(
        None, validation_alias=AliasChoices("maxAttempts", "max_attempts")
    )
    retry_delay_minutes: int | None = Field(
        None, validation_alias=AliasChoices("retryDelayMinutes", "retry_delay_minutes")
    )
    from_e164: str | None = Field(None, validation_alias=AliasChoices("fromE164", "from_e164"))
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    contact_list_id: str | None = Field(None, validation_alias=AliasChoices("contactListId", "contact_list_id"))
    auto_start: bool = Field(False, validation_alias=AliasChoices("autoStart", "auto_start"))


class ValidateVariablesBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    agent_id: str = Field(..., validation_alias=AliasChoices("agentId", "agent_id"))
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    contact_list_id: str | None = Field(None, validation_alias=AliasChoices("contactListId", "contact_list_id"))


class CampaignStatusPatch(BaseModel):
    status: str = Field(..., min_length=1)


class ContactImport(BaseModel):
    contacts: list[dict[str, Any]] = Field(default_factory=list)


class DncBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    phone_e164: str = Field(..., validation_alias=AliasChoices("phoneE164", "phone_e164"))
    reason: str | None = None


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
    tenant_id = ctx.workspace_tenant_id
    async with factory() as db:
        result = await db.execute(select(Campaign).where(Campaign.tenant_id == tenant_id).order_by(Campaign.created_at.desc()))
        rows = result.scalars().all()
        from sqlalchemy import func

        out = []
        for r in rows:
            cnt = await db.scalar(
                select(func.count()).select_from(CampaignContact).where(CampaignContact.campaign_id == r.campaign_id)
            ) or 0
            out.append({
                "campaignId": str(r.campaign_id),
                "campaign_id": str(r.campaign_id),
                "id": str(r.campaign_id),
                "name": r.name,
                "description": r.description,
                "defaultCountry": r.default_country,
                "status": r.status,
                "agentId": str(r.agent_id),
                "agent_id": str(r.agent_id),
                "concurrency": r.concurrency,
                "concurrencyLimit": r.concurrency,
                "retryRules": r.retry_rules or {},
                "retry_rules": r.retry_rules or {},
                "totalContacts": cnt,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            })
        return {"campaigns": out}


@router.post("/api/campaigns/validate-variables")
async def validate_variables(
    body: ValidateVariablesBody,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.campaigns.write")
    from server.services.saas.call_callback_service import resolve_workspace_agent
    from server.services.saas.contact_import_service import validate_agent_variables_against_contacts
    from server.db.models.phase5_models import Contact

    agent = await resolve_workspace_agent(body.agent_id, str(ctx.workspace_tenant_id))
    texts = [
        str(agent.get("system_prompt") or ""),
        str(agent.get("opening_greeting") or ""),
        str(agent.get("brief") or ""),
    ]

    contacts_to_check = list(body.contacts or [])
    if not contacts_to_check and body.contact_list_id:
        factory = get_session_factory()
        if factory:
            async with factory() as session:
                rows = await session.execute(
                    select(Contact).where(
                        Contact.contact_list_id == uuid.UUID(body.contact_list_id),
                        Contact.tenant_id == ctx.workspace_tenant_id,
                    )
                )
                contacts_to_check = [
                    {
                        "phone": r.phone,
                        "first_name": r.first_name,
                        "last_name": r.last_name,
                        "full_name": r.full_name,
                        "email": r.email,
                        "company": r.company,
                        "custom_fields": r.custom_fields,
                    }
                    for r in rows.scalars().all()
                ]

    report = validate_agent_variables_against_contacts(texts, contacts_to_check)
    return {"ok": True, **report}


@router.post("/api/campaigns")
async def create_campaign(body: CampaignCreate, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "error": {"code": "config_error", "message": "Database not configured"}}
    from server.config.env import get_settings
    from server.services.saas.contact_import_service import (
        derive_names,
        normalize_e164_phone,
        resolve_contact_variables,
    )
    from server.db.models.phase5_models import Contact

    settings = get_settings()
    tenant_id = ctx.workspace_tenant_id
    # Cap below Telnyx/plan headroom — never trust the client concurrency alone.
    hard_cap = max(1, min(20, int(settings.campaign_max_concurrency or 20)))
    concurrency = max(1, min(hard_cap, int(body.concurrency or 1)))
    max_attempts = max(1, min(5, int(body.max_attempts or settings.campaign_default_retry_attempts or 3)))
    retry_delay = max(5, min(24 * 60, int(body.retry_delay_minutes or 30)))
    retry_rules = {
        "max_attempts": max_attempts,
        "retry_delay_minutes": retry_delay,
    }
    schedule: dict[str, Any] = {}
    if body.from_e164:
        schedule["from_e164"] = body.from_e164.strip()
    cid = uuid.uuid4()
    imported_count = 0

    async with factory() as db:
        agent = await db.get(Agent, uuid.UUID(body.agent_id))
        if agent is None or agent.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})

        # Create Campaign record
        camp = Campaign(
            campaign_id=cid,
            tenant_id=tenant_id,
            agent_id=agent.agent_id,
            name=body.name.strip(),
            description=body.description.strip() if body.description else None,
            default_country=body.default_country or "US",
            status="running" if body.auto_start else "draft",
            concurrency=concurrency,
            retry_rules=retry_rules,
            schedule=schedule,
        )
        db.add(camp)

        # Gather contacts list
        raw_contact_list = list(body.contacts or [])
        if body.contact_list_id:
            cl_contacts = await db.execute(
                select(Contact).where(
                    Contact.contact_list_id == uuid.UUID(body.contact_list_id),
                    Contact.tenant_id == tenant_id,
                )
            )
            for r in cl_contacts.scalars().all():
                raw_contact_list.append({
                    "id": str(r.id),
                    "phone": r.phone,
                    "first_name": r.first_name,
                    "last_name": r.last_name,
                    "full_name": r.full_name,
                    "email": r.email,
                    "company": r.company,
                    "job_title": r.job_title,
                    "country": r.country,
                    "city": r.city,
                    "state": r.state,
                    "timezone": r.timezone,
                    "notes": r.notes,
                    "custom_fields": r.custom_fields,
                })

        # Process and snapshot contacts
        seen_phones: set[str] = set()
        for c in raw_contact_list:
            raw_phone = str(c.get("phone") or c.get("phone_e164") or c.get("phoneE164") or "").strip()
            if not raw_phone:
                continue

            # Normalize to E.164
            e164, err = normalize_e164_phone(raw_phone, body.default_country)
            if not e164:
                continue

            # Default keep first for duplicates in batch
            if e164 in seen_phones:
                continue
            seen_phones.add(e164)

            # Derive names & variables snapshot
            c_derived = derive_names(dict(c))
            c_derived["phone"] = e164
            resolved_vars = resolve_contact_variables(c_derived)

            contact_uuid = None
            if c.get("id"):
                try:
                    contact_uuid = uuid.UUID(str(c["id"]))
                except Exception:
                    pass

            db.add(
                CampaignContact(
                    id=uuid.uuid4(),
                    campaign_id=cid,
                    contact_id=contact_uuid,
                    phone_e164=e164,
                    phone_snapshot=e164,
                    status="pending",
                    metadata_=c_derived,
                    resolved_variables=resolved_vars,
                    attempts=0,
                )
            )
            imported_count += 1

        run_id = None
        if body.auto_start and imported_count > 0:
            run_id = uuid.uuid4()
            db.add(
                CampaignRun(
                    run_id=run_id,
                    campaign_id=cid,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
            )

        await db.commit()

    if body.auto_start and run_id:
        try:
            from server.services.saas.campaign_runner import spawn_campaign_runner
            from server.services.saas.tenant_guard import SubscriberPrincipal

            principal = SubscriberPrincipal(
                user_id=uuid.UUID(ctx.subject) if ctx.subscriber else uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                role=ctx.role,
                email=ctx.email or "",
            )
            spawn_campaign_runner(
                str(cid),
                str(run_id),
                principal=principal,
                workspace_tenant_id=ctx.workspace_tenant_id,
            )
        except Exception:
            pass

    return {
        "ok": True,
        "campaignId": str(cid),
        "campaign_id": str(cid),
        "id": str(cid),
        "totalContacts": imported_count,
        "campaign": {
            "campaignId": str(cid),
            "campaign_id": str(cid),
            "id": str(cid),
            "name": body.name,
            "description": body.description,
            "defaultCountry": body.default_country,
            "status": "running" if body.auto_start else "draft",
            "agentId": str(agent.agent_id),
            "agent_id": str(agent.agent_id),
            "concurrency": concurrency,
            "retryRules": retry_rules,
            "retry_rules": retry_rules,
            "schedule": schedule,
            "totalContacts": imported_count,
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
        camp = await _campaign_for_tenant(db, campaign_id, ctx.workspace_tenant_id)
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
        await _campaign_for_tenant(db, campaign_id, ctx.workspace_tenant_id)
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
        camp = await _campaign_for_tenant(db, campaign_id, ctx.workspace_tenant_id)
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
    # Prefer in-process dialer (works without Redis). Redis enqueue stays best-effort.
    try:
        from server.services.saas.campaign_runner import spawn_campaign_runner
        from server.services.saas.tenant_guard import SubscriberPrincipal

        principal = SubscriberPrincipal(
            user_id=uuid.UUID(ctx.subject) if ctx.subscriber else uuid.uuid4(),
            tenant_id=ctx.tenant_id,
            role=ctx.role,
            email=ctx.email or "",
        )
        spawn_campaign_runner(
            campaign_id,
            str(run_id),
            principal=principal,
            workspace_tenant_id=ctx.workspace_tenant_id,
        )
    except Exception:
        pass
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
        camp = await _campaign_for_tenant(db, campaign_id, ctx.workspace_tenant_id)
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
        camp = await _campaign_for_tenant(db, campaign_id, ctx.workspace_tenant_id)
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
        await _campaign_for_tenant(db, campaign_id, ctx.workspace_tenant_id)
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
