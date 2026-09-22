"""Resolve tenant + role for subscriber JWT or legacy app session."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from server.auth.dependencies import require_app_session
from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.config.env import get_settings


@dataclass(frozen=True)
class ApiTenantContext:
    tenant_id: uuid.UUID
    role: str
    subject: str
    subscriber: bool


async def require_api_tenant(
    request: Request,
    x_csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
    authorization: str | None = Header(None),
) -> ApiTenantContext:
    settings = get_settings()
    if settings.saas_auth_enabled:
        principal = await require_subscriber_jwt(request, authorization)
        return ApiTenantContext(
            tenant_id=principal.tenant_id,
            role=principal.role,
            subject=str(principal.user_id),
            subscriber=True,
        )
    session = await require_app_session(request, x_csrf_token)
    tid = session.tenant_id or settings.default_tenant_id
    return ApiTenantContext(
        tenant_id=uuid.UUID(tid),
        role=session.role,
        subject=session.subject,
        subscriber=False,
    )
