"""Tenant isolation helpers for subscriber API."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

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
# `deleting` is a teardown in progress: the data is already being destroyed.
UNUSABLE_TENANT_STATUSES = frozenset({"suspended", "deleted", "cancelled", "pending_deletion", "deleting"})

# A workspace the owner deleted that is still inside its grace period. It may back a
# session, but only so the owner can restore it or export data (see
# subscriber_dependencies._DELETION_GRACE_EXEMPT_PATHS); every other API refuses it.
RESTORABLE_TENANT_STATUS = "quarantined"

# Statuses that belong to the self-serve deletion lifecycle.
DELETION_LIFECYCLE_STATUSES = frozenset({"quarantined", "deleting", "deleted", "pending_deletion"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware_utc(value: datetime | None) -> datetime | None:
    """Timestamps from some drivers (SQLite in tests) come back naive; treat as UTC."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def tenant_in_deletion_grace(tenant: Tenant | None, now: datetime | None = None) -> bool:
    """Quarantined for deletion and the grace period has not run out yet.

    The purge date alone decides it. (Whether such a tenant may back a *session* is
    tenant_is_usable's question, which also rejects a stamped deleted_at.)
    """
    if tenant is None:
        return False
    if tenant.status != RESTORABLE_TENANT_STATUS:
        return False
    purge_at = as_aware_utc(getattr(tenant, "scheduled_purge_at", None))
    return purge_at is not None and purge_at > (now or _utcnow())


def tenant_deletion_is_final(tenant: Tenant | None, now: datetime | None = None) -> bool:
    """The workspace was deleted by its owner and can no longer be restored."""
    if tenant is None:
        return False
    if tenant.status in ("deleting", "deleted", "pending_deletion"):
        return True
    return tenant.status == RESTORABLE_TENANT_STATUS and not tenant_in_deletion_grace(tenant, now)


def tenant_is_usable(tenant: Tenant | None) -> bool:
    """
    Whether a tenant may still back a session.

    Issue-time (login/refresh) and verify-time (assert_session_tenant) must agree on
    this. When they disagreed, login happily minted a token for a soft-deleted
    tenant and every later request failed the deleted_at check with 404 "Not found".

    A quarantined workspace is usable only inside its grace period, and only so the
    restore screen can be reached; past the purge date it is gone.
    """
    if tenant is None:
        return False
    if tenant.deleted_at is not None or tenant.status in UNUSABLE_TENANT_STATUSES:
        return False
    if tenant.status == RESTORABLE_TENANT_STATUS:
        return tenant_in_deletion_grace(tenant)
    return True


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

    A live workspace always wins over one pending deletion; the pending one is chosen
    only when it is all the user has, which is what lands its owner on the restore
    screen after signing in again.
    """
    result = await session.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, Tenant.tenant_id == TenantMembership.tenant_id)
        .where(TenantMembership.user_id == user_id)
        .order_by(TenantMembership.created_at, TenantMembership.tenant_id)
    )
    pending: tuple[TenantMembership, Tenant] | None = None
    for membership, tenant in result.all():
        if not tenant_is_usable(tenant):
            continue
        if tenant.status == RESTORABLE_TENANT_STATUS:
            if pending is None:
                pending = (membership, tenant)
            continue
        return membership, tenant
    return pending


async def user_lost_workspace_to_deletion(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """True when one of the user's workspaces was deleted and is past restoring.

    Lets sign-in say "this workspace was permanently deleted" instead of the generic
    "invalid email or password" once the password itself has been verified.
    """
    result = await session.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, Tenant.tenant_id == TenantMembership.tenant_id)
        .where(TenantMembership.user_id == user_id)
    )
    return any(tenant_deletion_is_final(tenant) for _m, tenant in result.all())


@dataclass(frozen=True)
class SubscriberPrincipal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    email: str
    # Epoch seconds of the interactive sign-in behind this token; None after a silent
    # refresh. Used to require a fresh authentication for workspace restore.
    auth_time: int | None = None
    # Support handoff actor, when this session is an impersonation.
    impersonator: str | None = None

    @classmethod
    def from_claims(cls, claims: AccessTokenClaims) -> SubscriberPrincipal:
        return cls(
            user_id=uuid.UUID(claims.user_id),
            tenant_id=uuid.UUID(claims.tenant_id),
            role=claims.role,
            email=claims.email,
            auth_time=claims.auth_time,
            impersonator=claims.impersonator,
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
