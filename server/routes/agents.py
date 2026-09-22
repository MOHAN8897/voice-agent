"""Agent workspace routes — Phase 2."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt_if_enabled
from server.brain.agent_service import agent_service
from server.services.saas.tenant_guard import SubscriberPrincipal, require_subscriber_permission

router = APIRouter()


class CreateAgentBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    tenantId: Optional[str] = None
    languages: Optional[list[str]] = None


class PatchAgentBody(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    defaultTier: Optional[str] = None
    languages: Optional[list[str]] = None
    memorySchema: Optional[str] = None


def _tenant_id(principal: SubscriberPrincipal | None) -> str | None:
    return str(principal.tenant_id) if principal else None


@router.get("/api/agents")
async def list_agents(principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled)):
    agents = await agent_service.list_agents(tenant_id=_tenant_id(principal))
    return {"agents": agents}


@router.post("/api/agents")
async def create_agent(
    body: CreateAgentBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    tenant_id = _tenant_id(principal) or body.tenantId
    if principal and body.tenantId and body.tenantId != str(principal.tenant_id):
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_tenant", "message": "Invalid tenant"}})
    agent = await agent_service.create_agent(
        name=body.name,
        tenant_id=tenant_id,
        languages=body.languages,
    )
    return {"ok": True, "agent": agent}


@router.get("/api/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    try:
        return {"agent": await agent_service.get_agent(agent_id, tenant_id=_tenant_id(principal))}
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})


@router.patch("/api/agents/{agent_id}")
async def patch_agent(
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
    try:
        agent = await agent_service.patch_agent(agent_id, patch, tenant_id=_tenant_id(principal))
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    return {"ok": True, "agent": agent}


@router.put("/api/agents/{agent_id}")
async def put_agent(
    agent_id: str,
    body: PatchAgentBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    return await patch_agent(agent_id, body, principal)


@router.delete("/api/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    try:
        return await agent_service.delete_agent(agent_id, tenant_id=_tenant_id(principal))
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
