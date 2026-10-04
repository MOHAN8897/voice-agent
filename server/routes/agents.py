"""Agent workspace routes — Phase 2."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict

from server.auth.subscriber_dependencies import require_subscriber_jwt_if_enabled
from server.auth.tenant_context import tenant_id_from_request
from server.brain.agent_service import agent_service
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)

router = APIRouter()


class CreateAgentBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255)
    tenantId: Optional[str] = None
    languages: Optional[list[str]] = None
    recordingDisclosureEnabled: Optional[bool] = None
    recordingDisclosureText: Optional[str] = None


class PatchAgentBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    status: Optional[str] = None
    defaultTier: Optional[str] = None
    languages: Optional[list[str]] = None
    memorySchema: Optional[str] = None
    recordingDisclosureEnabled: Optional[bool] = None
    recordingDisclosureText: Optional[str] = None


def _tenant_id(request: Request, principal: SubscriberPrincipal | None) -> str | None:
    if principal:
        return str(subscriber_workspace_tenant_id(principal))
    return tenant_id_from_request(request)


@router.get("/api/agents")
async def list_agents(
    request: Request,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    agents = await agent_service.list_agents(tenant_id=_tenant_id(request, principal))
    return {"agents": agents}


@router.post("/api/agents")
async def create_agent(
    request: Request,
    body: CreateAgentBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    tenant_id = _tenant_id(request, principal) or body.tenantId
    if principal and body.tenantId and body.tenantId != str(principal.tenant_id):
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_tenant", "message": "Invalid tenant"}})
    agent = await agent_service.create_agent(
        name=body.name,
        tenant_id=tenant_id,
        languages=body.languages,
        recording_disclosure_enabled=body.recordingDisclosureEnabled or False,
        recording_disclosure_text=body.recordingDisclosureText,
    )
    return {"ok": True, "agent": agent}


@router.get("/api/agents/{agent_id}")
async def get_agent(
    request: Request,
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    try:
        return {"agent": await agent_service.get_agent(agent_id, tenant_id=_tenant_id(request, principal))}
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})


@router.patch("/api/agents/{agent_id}")
async def patch_agent(
    request: Request,
    agent_id: str,
    body: PatchAgentBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    patch: dict[str, Any] = {}
    if body.name is not None:
        patch["name"] = body.name
    if body.status is not None:
        patch["status"] = body.status
    if body.defaultTier is not None:
        patch["default_tier"] = body.defaultTier
    if body.languages is not None:
        patch["languages"] = body.languages
    if body.memorySchema is not None:
        patch["memory_schema"] = body.memorySchema
    if body.recordingDisclosureEnabled is not None:
        patch["recording_disclosure_enabled"] = body.recordingDisclosureEnabled
    if body.recordingDisclosureText is not None:
        patch["recording_disclosure_text"] = body.recordingDisclosureText
    try:
        agent = await agent_service.patch_agent(agent_id, patch, tenant_id=_tenant_id(request, principal))
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    return {"ok": True, "agent": agent}


@router.put("/api/agents/{agent_id}")
async def put_agent(
    request: Request,
    agent_id: str,
    body: PatchAgentBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    return await patch_agent(request, agent_id, body, principal)


@router.delete("/api/agents/{agent_id}")
async def delete_agent(
    request: Request,
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    try:
        return await agent_service.delete_agent(agent_id, tenant_id=_tenant_id(request, principal))
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
