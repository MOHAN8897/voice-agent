"""Subscriber follow-up settings and review queue. All writes require phone permissions."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import ProgrammingError, OperationalError

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.services.saas import followup_service as service
from server.services.saas.followup_policy import FollowUpConfig
from server.services.saas.tenant_guard import SubscriberPrincipal, load_agent_for_tenant, require_subscriber_permission, subscriber_workspace_tenant_id

router = APIRouter()


class PolicyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: FollowUpConfig
    revision: int
    acknowledgeCharges: bool = False


class JobWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["schedule", "cancel"]
    dueAt: datetime | None = None
    expectedUpdatedAt: datetime
    confirm: bool = False


async def storage(operation):
    try:
        return await operation
    except (ProgrammingError, OperationalError):
        raise HTTPException(503, detail={"error": {"code": "followup_storage_pending", "message": "Follow-up scheduling is not ready. Ask your administrator to complete the database update. Existing manual callbacks remain available."}}) from None


@router.get("/api/agents/{agent_id}/follow-up-policy")
async def policy_read(agent_id: UUID, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.calls.read")
    tid = subscriber_workspace_tenant_id(principal)
    await load_agent_for_tenant(str(agent_id), tid)
    return await storage(service.read_policy(tid, agent_id))


@router.put("/api/agents/{agent_id}/follow-up-policy")
async def policy_write(agent_id: UUID, body: PolicyWrite, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    await load_agent_for_tenant(str(agent_id), subscriber_workspace_tenant_id(principal))
    return await storage(service.save_policy(principal, agent_id, body.config, body.revision, body.acknowledgeCharges))


@router.get("/api/follow-ups")
async def jobs_read(agentId: UUID | None = None, status: Literal["active", "needs_review", "scheduled", "completed", "suppressed", "cancelled", "expired"] | None = "active",
                    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                    principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.calls.read")
    return await storage(service.list_jobs(subscriber_workspace_tenant_id(principal), agentId, status, limit, offset))


@router.patch("/api/follow-ups/{job_id}")
async def job_write(job_id: UUID, body: JobWrite, principal: SubscriberPrincipal = Depends(require_subscriber_jwt)):
    require_subscriber_permission(principal, "app.telephony.write")
    if not body.confirm:
        raise HTTPException(422, "Confirm this change. Scheduled calls use your wallet and honor DND and calling hours.")
    return await storage(service.edit_job(principal, job_id, body.action, body.dueAt, body.expectedUpdatedAt))
