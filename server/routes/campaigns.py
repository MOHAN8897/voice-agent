"""Campaign + DNC + phone number APIs — Phase 5 (+ SaaS tenant context)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ConfigDict, AliasChoices, field_validator
from sqlalchemy import select

from server.auth.api_tenant import ApiTenantContext, require_api_tenant
from server.auth.rbac import require_role_permission
from server.db.connection import get_session_factory
from server.db.models.entities import Agent
from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, DncEntry, PhoneNumber

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


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
    # Compliance Attestation
    consent_confirmed: bool = Field(..., validation_alias=AliasChoices("consentConfirmed", "consent_confirmed"))
    consent_version: str = Field("2026-10-v1", validation_alias=AliasChoices("consentVersion", "consent_version"))
    dnd_scrub_enabled: bool = Field(True, validation_alias=AliasChoices("dndScrubEnabled", "dnd_scrub_enabled"))

    @field_validator("consent_confirmed")
    @classmethod
    def validate_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must confirm consent to launch campaigns.")
        return v


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
    reason: str | None = "manual_operator"


class DncBulkBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    phones: list[str] = Field(default_factory=list)
    reason: str | None = "bulk_upload"


class DncDeactivateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    removal_reason: str = Field(
        ...,
        min_length=5,
        validation_alias=AliasChoices("removalReason", "removal_reason"),
        description="Reason for removing contact from DND list",
    )
    reconsent_confirmed: bool = Field(
        ...,
        validation_alias=AliasChoices("reconsentConfirmed", "reconsent_confirmed"),
        description="Must explicitly confirm new recipient authorization",
    )

    @field_validator("reconsent_confirmed")
    @classmethod
    def validate_reconsent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must explicitly confirm new recipient authorization.")
        return v


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
async def create_campaign(
    request: Request,
    body: CampaignCreate,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.campaigns.write")
    if not body.consent_confirmed:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "consent_required",
                    "message": "You must confirm that you have obtained required legal consent for these recipient contacts.",
                }
            },
        )
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
    client_ip = _client_ip(request) or "unknown"
    user_agent = (request.headers.get("user-agent") or "unknown")[:255]
    attested_user_id = uuid.UUID(ctx.subject) if ctx.subscriber and ctx.subject else None

    async with factory() as db:
        agent = await db.get(Agent, uuid.UUID(body.agent_id))
        if agent is None or agent.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})

        # Create Campaign record with legal attestation audit trail
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
            consent_confirmed=True,
            consent_attestation_version=body.consent_version,
            attested_by_user_id=attested_user_id,
            attested_at=datetime.now(timezone.utc),
            attested_ip=client_ip,
            attested_user_agent=user_agent,
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
        active_dnc_set: set[str] = set()
        if body.dnd_scrub_enabled:
            dnc_rows = await db.execute(
                select(DncEntry.phone_e164).where(
                    DncEntry.tenant_id == tenant_id,
                    DncEntry.active.is_(True),
                )
            )
            active_dnc_set = set(dnc_rows.scalars().all())

        dnd_excluded_count = 0
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

            # Check DND list exclusion
            is_dnc = e164 in active_dnc_set
            contact_status = "dnc_excluded" if is_dnc else "pending"
            if is_dnc:
                dnd_excluded_count += 1

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
                    status=contact_status,
                    metadata_=c_derived,
                    resolved_variables=resolved_vars,
                    attempts=0,
                )
            )
            imported_count += 1

        run_id = None
        if body.auto_start and (imported_count - dnd_excluded_count) > 0:
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
        "dndExcludedCount": dnd_excluded_count,
        "dnd_excluded_count": dnd_excluded_count,
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
            "dndExcludedCount": dnd_excluded_count,
            "dnd_excluded_count": dnd_excluded_count,
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
async def list_dnc(
    status: str = Query("active", description="active | inactive | all"),
    search: str | None = Query(None, description="Phone search substring"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.calls.read")
    factory = get_session_factory()
    if factory is None:
        return {"entries": [], "total": 0, "page": page, "limit": limit}
    tenant_id = ctx.workspace_tenant_id
    async with factory() as db:
        q = select(DncEntry).where(DncEntry.tenant_id == tenant_id)
        status_norm = (status or "active").strip().lower()
        if status_norm == "active":
            q = q.where(DncEntry.active.is_(True))
        elif status_norm in ("inactive", "deactivated"):
            q = q.where(DncEntry.active.is_(False))
        # "all" does not filter by active
        if search and search.strip():
            clean_search = search.strip().replace("%", "").replace("_", "")
            q = q.where(DncEntry.phone_e164.ilike(f"%{clean_search}%"))

        from sqlalchemy import func

        total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
        offset = (page - 1) * limit
        rows = await db.execute(q.order_by(DncEntry.added_at.desc()).offset(offset).limit(limit))
        entries = []
        for r in rows.scalars().all():
            entries.append({
                "id": str(r.id),
                "phone_e164": r.phone_e164,
                "phoneE164": r.phone_e164,
                "reason": r.reason,
                "source": getattr(r, "source", "manual") or "manual",
                "active": getattr(r, "active", True),
                "added_at": r.added_at.isoformat() if r.added_at else None,
                "addedAt": r.added_at.isoformat() if r.added_at else None,
                "removed_at": r.removed_at.isoformat() if getattr(r, "removed_at", None) else None,
                "removedAt": r.removed_at.isoformat() if getattr(r, "removed_at", None) else None,
                "removal_reason": getattr(r, "removal_reason", None),
                "removalReason": getattr(r, "removal_reason", None),
                "reconsent_confirmed": getattr(r, "reconsent_confirmed", False),
                "reconsentConfirmed": getattr(r, "reconsent_confirmed", False),
            })
        return {"entries": entries, "total": total, "page": page, "limit": limit}


@router.post("/api/dnc")
async def add_dnc(body: DncBody, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False}
    from server.services.saas.contact_import_service import normalize_e164_phone

    phone = (body.phone_e164 or "").strip()
    norm_phone, _ = normalize_e164_phone(phone, "US")
    norm_phone = norm_phone or phone
    tenant_id = ctx.workspace_tenant_id
    user_id = uuid.UUID(ctx.subject) if ctx.subscriber and ctx.subject else None

    async with factory() as db:
        existing = await db.execute(
            select(DncEntry).where(DncEntry.tenant_id == tenant_id, DncEntry.phone_e164 == norm_phone)
        )
        row = existing.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if row:
            row.active = True
            row.reason = body.reason or "manual_operator"
            row.source = "operator_ui"
            row.added_at = now
            row.added_by_user_id = user_id
            row.removed_at = None
            row.removed_by_user_id = None
            row.removal_reason = None
            row.reconsent_confirmed = False
        else:
            db.add(
                DncEntry(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    phone_e164=norm_phone,
                    reason=body.reason or "manual_operator",
                    source="operator_ui",
                    active=True,
                    added_at=now,
                    added_by_user_id=user_id,
                )
            )
        await db.commit()
    return {"ok": True, "phone_e164": norm_phone, "active": True}


@router.post("/api/dnc/bulk")
async def bulk_add_dnc(body: DncBulkBody, ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if factory is None:
        return {"ok": False, "added": 0}
    from server.services.saas.contact_import_service import normalize_e164_phone

    tenant_id = ctx.workspace_tenant_id
    user_id = uuid.UUID(ctx.subject) if ctx.subscriber and ctx.subject else None
    count = 0
    now = datetime.now(timezone.utc)

    async with factory() as db:
        for p in body.phones:
            raw = str(p or "").strip()
            if not raw:
                continue
            norm, _ = normalize_e164_phone(raw, "US")
            norm = norm or raw
            existing = await db.execute(
                select(DncEntry).where(DncEntry.tenant_id == tenant_id, DncEntry.phone_e164 == norm)
            )
            row = existing.scalar_one_or_none()
            if row:
                row.active = True
                row.reason = body.reason or "bulk_upload"
                row.source = "bulk_upload"
                row.added_at = now
                row.added_by_user_id = user_id
                row.removed_at = None
                row.removed_by_user_id = None
                row.removal_reason = None
                row.reconsent_confirmed = False
            else:
                db.add(
                    DncEntry(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        phone_e164=norm,
                        reason=body.reason or "bulk_upload",
                        source="bulk_upload",
                        active=True,
                        added_at=now,
                        added_by_user_id=user_id,
                    )
                )
            count += 1
        await db.commit()
    return {"ok": True, "added": count}


@router.post("/api/dnc/{phone_e164}/deactivate")
async def deactivate_dnc(
    phone_e164: str,
    body: DncDeactivateBody,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.campaigns.write")
    if not body.reconsent_confirmed:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "reconsent_required",
                    "message": "You must confirm that this contact has provided new authorization to receive calls.",
                }
            },
        )
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database required")
    tenant_id = ctx.workspace_tenant_id
    user_id = uuid.UUID(ctx.subject) if ctx.subscriber and ctx.subject else None

    async with factory() as db:
        clean_phone = phone_e164.strip()
        entry = await db.execute(
            select(DncEntry).where(DncEntry.tenant_id == tenant_id, DncEntry.phone_e164 == clean_phone)
        )
        row = entry.scalar_one_or_none()
        if not row:
            alt = f"+{clean_phone.lstrip('+')}" if not clean_phone.startswith("+") else clean_phone.lstrip("+")
            entry2 = await db.execute(
                select(DncEntry).where(DncEntry.tenant_id == tenant_id, DncEntry.phone_e164 == alt)
            )
            row = entry2.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="DND entry not found")
        row.active = False
        row.removed_at = datetime.now(timezone.utc)
        row.removed_by_user_id = user_id
        row.removal_reason = body.removal_reason.strip()
        row.reconsent_confirmed = True
        await db.commit()
    return {"ok": True, "phone_e164": row.phone_e164, "active": False}


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
