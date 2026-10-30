"""Tenant APIs for "Callback needed in another language" (language-switch callback items)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from server.auth.api_tenant import ApiTenantContext, require_api_tenant
from server.auth.rbac import require_role_permission
from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.services.saas import language_switch_service as svc
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)
from server.utils.rate_limiter import RateLimiter, raise_rate_limited

router = APIRouter()
_dial_limiter = RateLimiter(max_requests=12, window_s=60)


class StatusBody(BaseModel):
    status: str = Field(pattern="^(pending|done|dismissed)$")


class CallNowBody(BaseModel):
    fromE164: str | None = Field(None, max_length=32)


class BulkCampaignBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=1000)
    name: str | None = Field(None, max_length=200)
    consentConfirmed: bool = False
    fromE164: str | None = Field(None, max_length=32)
    autoStart: bool = True


@router.get("/api/language-switch-requests")
async def list_requests(
    agentId: str | None = Query(None, max_length=64),
    status: str = Query("open", max_length=16),
    language: str | None = Query(None, max_length=16),
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),  # noqa: B008 -- FastAPI auth dependency.
):
    require_subscriber_permission(principal, "app.calls.read")
    from server.call.language_switch import language_name

    rows = await svc.list_language_switch_requests(subscriber_workspace_tenant_id(principal), agent_id=agentId,
                                                   status=status, language=language)
    languages = sorted({r["requestedLanguage"] for r in rows})
    return {"requests": rows, "languages": [{"code": c, "label": language_name(c)} for c in languages]}


@router.patch("/api/language-switch-requests/{item_id}")
async def patch_request(
    item_id: uuid.UUID, body: StatusBody,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),  # noqa: B008
):
    require_subscriber_permission(principal, "app.telephony.write")
    return await svc.update_language_switch_status(subscriber_workspace_tenant_id(principal), item_id, body.status)


@router.get("/api/language-switch-requests/readiness")
async def readiness(
    agentId: str = Query(..., max_length=64),
    language: str = Query(..., max_length=16),
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),  # noqa: B008
):
    """Can this agent call in that language now? The brain is rendered for the pack to prove it."""
    require_subscriber_permission(principal, "app.calls.read")
    from server.services.saas.call_callback_service import resolve_workspace_agent

    agent = await resolve_workspace_agent(agentId, str(subscriber_workspace_tenant_id(principal)))
    return await svc.language_readiness(agent, language)


@router.post("/api/language-switch-requests/{item_id}/call")
async def call_now(
    item_id: uuid.UUID, body: CallNowBody | None = None,
    principal: SubscriberPrincipal = Depends(require_subscriber_jwt),  # noqa: B008
):
    require_subscriber_permission(principal, "app.telephony.write")
    allowed, retry = _dial_limiter.allow(f"language-switch:{principal.tenant_id}")
    if not allowed:
        raise_rate_limited(retry, "Callback rate limit reached. Wait and try again.")
    return await svc.call_language_switch(principal, item_id, from_e164=(body.fromE164 if body else None))


@router.post("/api/language-switch-requests/campaign")
async def bulk_campaign(
    request: Request, body: BulkCampaignBody,
    ctx: ApiTenantContext = Depends(require_api_tenant),  # noqa: B008
):
    """One campaign per agent; every contact is called in its own requested language."""
    require_role_permission(ctx.role, "app.campaigns.write")
    if not body.consentConfirmed:
        raise HTTPException(400, detail={"error": {"code": "consent_required",
            "message": "Confirm that you have consent to call these contacts."}})
    from server.call.language_switch import language_name
    from server.routes.campaigns import CampaignCreate, create_campaign
    from server.services.saas.call_callback_service import resolve_workspace_agent

    tenant_id = ctx.workspace_tenant_id
    by_agent, skipped = await svc.campaign_contacts_for(tenant_id, list(dict.fromkeys(body.ids)))
    if not by_agent:
        raise HTTPException(409, detail={"error": {"code": "nothing_to_call",
            "message": "None of the selected contacts still need a callback."}})
    # Check every agent/language pair before creating anything.
    for agent_id, contacts in by_agent.items():
        agent = await resolve_workspace_agent(agent_id, str(tenant_id))
        await svc.validate_campaign_languages(agent, contacts)
    campaigns: list[dict[str, Any]] = []
    for agent_id, contacts in by_agent.items():
        langs = sorted({c["call_language"] for c in contacts})
        name = (body.name or "Language callbacks").strip()[:150] + " · " + ", ".join(language_name(c) for c in langs)
        created = await create_campaign(request, CampaignCreate(
            name=name[:255], agent_id=agent_id, contacts=contacts, consent_confirmed=True, auto_start=body.autoStart,
            from_e164=body.fromE164, description="Callbacks for callers who asked to speak another language.",
            client_request_id=f"ls-{uuid.uuid4().hex}",
        ), ctx)
        campaign_id = str(created.get("campaignId") or "")
        if campaign_id:
            await svc.mark_campaign_items(tenant_id, campaign_id, [c["language_switch_id"] for c in contacts])
        campaigns.append({"agentId": agent_id, "campaignId": campaign_id, "languages": langs,
                          "contacts": len(contacts), "status": (created.get("campaign") or {}).get("status")})
    return {"ok": True, "campaigns": campaigns, "skipped": skipped}
