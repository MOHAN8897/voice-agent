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

# Statuses that mean the tenant can no longer back a session. `cancelled` is what
# the admin soft-delete sets (dev_admin.delete_tenant also stamps deleted_at), so it
# belongs here — leaving it out let login/refresh mint a token for a deleted workspace.
UNUSABLE_TENANT_STATUSES = frozenset({"suspended", "deleted", "cancelled", "pending_deletion"})


def tenant_is_usable(tenant: Tenant | None) -> bool:
    """
    Whether a tenant may still back a session.

    Issue-time (login/refresh) and verify-time (assert_session_tenant) must agree on
    this. When they disagreed, login happily minted a token for a soft-deleted
    tenant and every later request failed the deleted_at check with 404 "Not found".
    """
    if tenant is None:
        return False
    return tenant.deleted_at is None and tenant.status not in UNUSABLE_TENANT_STATUSES


async def resolve_usable_tenant(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[TenantMembership, Tenant] | None:
    """
    The tenant a session should act on: the user's oldest membership whose tenant is
    still usable, or None when they have none.

    Deterministic and lifecycle-aware on purpose. `refresh` used to take an arbitrary
    membership (`limit(1)` with no ORDER BY), so a user holding both a live workspace
    and a soft-deleted one got a token for whichever row came back first — and then
    every console request 404'd on it. Ordering by created_at (then tenant_id as a
    tie-break, since created_at need not be unique) keeps the choice stable, and
    skipping unusable tenants keeps a deleted workspace from being selected at all.
    """
    result = await session.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, Tenant.tenant_id == TenantMembership.tenant_id)
        .where(TenantMembership.user_id == user_id)
        .order_by(TenantMembership.created_at, TenantMembership.tenant_id)
    )
    for membership, tenant in result.all():
        if tenant_is_usable(tenant):
            return membership, tenant
    return None


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


def subscriber_workspace_tenant_id(principal: SubscriberPrincipal) -> uuid.UUID:
    """Tenant used for agents, phone lines, and call records (dev testers → platform default)."""
    from server.services.saas.dev_tester_workspace import workspace_tenant_id_for_subscriber

    return workspace_tenant_id_for_subscriber(principal.tenant_id, principal.email)


async def assert_session_tenant(
    session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> Tenant:
    """
    The tenant an existing session token may act on.

    A deleted workspace is normally a 404 — it must not be confirmed to exist. But a
    token minted before that deletion, where the user still has a live workspace, is
    a *stale* session rather than a missing one. Answering 404 there left the console
    showing every resource as "Not found" with a Retry button that could not possibly
    help, because the client only re-establishes a session on 401. Answer 401 instead
    so the client refreshes onto the workspace that survives.
    """
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.deleted_at is not None:
        if await resolve_usable_tenant(session, user_id) is not None:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "auth_error",
                        "message": "Your workspace changed. Sign in again to continue.",
                    }
                },
            )
        # No surviving workspace — nothing to fall back to, so stay a 404.
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
