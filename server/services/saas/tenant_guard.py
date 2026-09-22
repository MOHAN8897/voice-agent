"""Tenant isolation helpers for subscriber API."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.jwt_tokens import AccessTokenClaims
from server.auth.rbac import role_has_permission
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.saas_models import TenantMembership


@dataclass(frozen=True)
class SubscriberPrincipal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    email: str

    @classmethod
    def from_claims(cls, claims: AccessTokenClaims) -> SubscriberPrincipal:
        return cls(
            user_id=uuid.UUID(claims.user_id),
            tenant_id=uuid.UUID(claims.tenant_id),
            role=claims.role,
            email=claims.email,
        )


async def assert_tenant_active(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
    if tenant.status in ("suspended", "deleted", "pending_deletion"):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "tenant_suspended", "message": "Organization is not active"}},
        )
    return tenant


async def assert_membership(session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> TenantMembership:
    result = await session.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
    return row


async def load_agent_for_tenant(agent_id: str, tenant_id: uuid.UUID) -> Agent:
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": {"code": "db_unavailable", "message": "Database required"}})
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    async with factory() as session:
        agent = await session.get(Agent, aid)
        if agent is None or agent.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
        return agent


def require_subscriber_permission(principal: SubscriberPrincipal, permission: str) -> None:
    if not role_has_permission(principal.role, permission):
        raise HTTPException(status_code=403, detail={"error": {"code": "auth_error", "message": "Permission denied"}})
