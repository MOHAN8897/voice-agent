"""FastAPI dependencies for SaaS subscriber JWT auth."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from server.auth.jwt_tokens import decode_access_token
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.saas_models import User
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    assert_membership,
    assert_tenant_active,
)


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
    claims = decode_access_token(token)
    if claims is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_error", "message": "Invalid or expired token"}},
        )
    principal = SubscriberPrincipal.from_claims(claims)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "db_unavailable", "message": "Database required for SaaS auth"}},
        )
    async with factory() as session:
        await assert_tenant_active(session, principal.tenant_id)
        await assert_membership(session, principal.user_id, principal.tenant_id)
        user = await session.get(User, principal.user_id)
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
    return principal


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
    """When SaaS auth is on, same validation as require_subscriber_jwt (membership, tenant, user)."""
    settings = get_settings()
    if not settings.saas_auth_enabled:
        return None
    return await require_subscriber_jwt(request, authorization)
