"""FastAPI dependencies for SaaS subscriber JWT auth."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Header, HTTPException, Request

from server.auth.jwt_tokens import decode_access_token
from server.auth.session import cookie_names, parse_session_token
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.saas_models import User
from server.services.saas.platform_admins import effective_membership_role
from server.services.saas.tenant_guard import (
    DELETION_LIFECYCLE_STATUSES,
    SubscriberPrincipal,
    as_aware_utc,
    assert_membership,
    assert_session_tenant,
    tenant_in_deletion_grace,
)


def has_portal_session(request: Request) -> bool:
    """Valid dev or legacy app console cookie (Test Studio / dev portal)."""
    names = cookie_names()
    for cookie_name, kind in ((names["dev"], "dev"), (names["app"], "app")):
        token = request.cookies.get(cookie_name)
        if parse_session_token(token or "", kind):
            return True
    return False


def principal_from_access_token(token: str) -> SubscriberPrincipal | None:
    claims = decode_access_token(token)
    if claims is None:
        return None
    return SubscriberPrincipal.from_claims(claims)


async def require_subscriber_jwt(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SubscriberPrincipal:
    settings = get_settings()
    if not settings.saas_auth_enabled:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "saas_auth_disabled", "message": "SaaS auth is not enabled"}},
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_error", "message": "Bearer token required"}},
        )
    token = authorization.split(" ", 1)[1].strip()
    return await principal_from_verified_token(token, request_path=request.url.path)



async def principal_from_verified_token(token: str, *, request_path: str = "") -> SubscriberPrincipal:
    settings = get_settings()
    claims = decode_access_token(token)
    if claims is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_error", "message": "Invalid or expired token"}},
        )
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "db_unavailable", "message": "Database required for SaaS auth"}},
        )
    user_id = uuid.UUID(claims.user_id)
    tenant_id = uuid.UUID(claims.tenant_id)
    async with factory() as session:
        tenant = await assert_session_tenant(session, user_id, tenant_id)
        membership = await assert_membership(session, user_id, tenant_id)
        user = await session.get(User, user_id)
        if user is None or user.deleted_at is not None or user.status == "disabled":
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "auth_error", "message": "Invalid or expired token"}},
            )
        if settings.saas_require_email_verification_for_login and user.email_verified_at is None:
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "email_not_verified", "message": "Verify your email first"}},
            )

        if tenant is not None and tenant.status != "active":
            enforce_tenant_lifecycle(tenant, request_path)

        role = effective_membership_role(user.email, membership.role)
        return SubscriberPrincipal(
            user_id=user.user_id,
            tenant_id=tenant_id,
            role=role,
            email=user.email,
            auth_time=claims.auth_time,
            impersonator=claims.impersonator,
        )


# Reachable while a workspace is pending deletion, so the owner can see what will be
# restored, restore it, or take their data out. Everything else fails closed.
_DELETION_GRACE_EXEMPT_PATHS = frozenset({
    "/api/tenant/restore",
    "/api/tenant/restore-status",
    "/api/tenant/delete/cancel",
    "/api/auth/logout-all",
})
_DELETION_GRACE_EXEMPT_PREFIXES = ("/api/tenant/export",)


def _grace_exempt(path: str) -> bool:
    path = (path or "").rstrip("/") or "/"
    return path in _DELETION_GRACE_EXEMPT_PATHS or any(
        path == p or path.startswith(p + "/") for p in _DELETION_GRACE_EXEMPT_PREFIXES
    )


def enforce_tenant_lifecycle(tenant, request_path: str) -> None:
    """Fail closed for any workspace that is not active.

    - Pending deletion, inside the grace period: only the restore / export endpoints
      answer; everything else is 403 ``tenant_quarantined`` (the console shows the
      restore screen on that code).
    - Deleted, being torn down, or past the grace period: 403 ``workspace_deleted`` on
      every path, including restore — there is nothing left to restore.
    - Any other non-active state (e.g. past_due): 403 ``tenant_inactive``. It must not
      say "quarantined", or the console would tell the user their workspace is being
      deleted when it is not.
    """
    scheduled_purge_at = as_aware_utc(getattr(tenant, "scheduled_purge_at", None))
    if tenant_in_deletion_grace(tenant):
        if _grace_exempt(request_path):
            return
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_quarantined",
                "message": "This workspace is scheduled for deletion. Restore it to continue.",
                "scheduledPurgeAt": scheduled_purge_at.isoformat() if scheduled_purge_at else None,
            },
        )
    if tenant.status in DELETION_LIFECYCLE_STATUSES:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "workspace_deleted",
                "message": "This workspace was permanently deleted and can no longer be restored.",
            },
        )
    raise HTTPException(
        status_code=403,
        detail={"error": "tenant_inactive", "message": "This workspace is not active."},
    )


async def optional_subscriber_context(
    authorization: Annotated[str | None, Header()] = None,
) -> SubscriberPrincipal | None:
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return None
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    claims = decode_access_token(authorization.split(" ", 1)[1].strip())
    if claims is None:
        return None
    return SubscriberPrincipal.from_claims(claims)


async def require_subscriber_jwt_if_enabled(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SubscriberPrincipal | None:
    """
    When SaaS auth is on:
    - Bearer JWT -> validated subscriber principal (Dialtact console).
    - Dev/app portal session cookie -> None (routes use tenant_id_from_request).
    - Otherwise -> 401.
    """
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if decode_access_token(token) is not None:
            return await require_subscriber_jwt(request, authorization)
    if has_portal_session(request):
        return None
    raise HTTPException(
        status_code=401,
        detail={
            "error": {
                "code": "auth_error",
                "message": "Sign in (subscriber JWT or dev portal session required)",
            }
        },
    )
