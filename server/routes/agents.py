"""Agent workspace routes — Phase 2."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.brain.agent_service import agent_service

router = APIRouter()


class CreateAgentBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    tenantId: Optional[str] = None


class PatchAgentBody(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    defaultTier: Optional[str] = None
    languages: Optional[list[str]] = None
    memorySchema: Optional[str] = None


@router.get("/api/agents")
async def list_agents():
    agents = await agent_service.list_agents()
    return {"agents": agents}


@router.post("/api/agents")
async def create_agent(body: CreateAgentBody):
    agent = await agent_service.create_agent(name=body.name, tenant_id=body.tenantId)
    return {"ok": True, "agent": agent}


@router.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    try:
        return {"agent": await agent_service.get_agent(agent_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})


@router.patch("/api/agents/{agent_id}")
async def patch_agent(agent_id: str, body: PatchAgentBody):
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
        agent = await agent_service.patch_agent(agent_id, patch)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    return {"ok": True, "agent": agent}
