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
    SubscriberPrincipal,
    assert_membership,
    assert_tenant_active,
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
    return await principal_from_verified_token(token)


async def principal_from_verified_token(token: str) -> SubscriberPrincipal:
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
        await assert_tenant_active(session, tenant_id)
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
        role = effective_membership_role(user.email, membership.role)
        return SubscriberPrincipal(
            user_id=user.user_id,
            tenant_id=tenant_id,
            role=role,
            email=user.email,
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
    - Bearer JWT -> validated subscriber principal (Voxly console).
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
