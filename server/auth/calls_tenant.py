"""Resolve tenant scope for call archive APIs."""
from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, Request

from server.auth.subscriber_dependencies import require_subscriber_jwt
from server.auth.tenant_context import tenant_id_from_request
from server.config.env import get_settings
from server.services.saas.tenant_guard import require_subscriber_permission


async def resolve_calls_tenant_id(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    settings = get_settings()
    if settings.saas_auth_enabled:
        principal = await require_subscriber_jwt(request, authorization)
        require_subscriber_permission(principal, "app.calls.read")
        return str(principal.tenant_id)
    tenant_id = request.query_params.get("tenantId") or request.query_params.get("tenant_id")
    if tenant_id:
        return tenant_id
    return tenant_id_from_request(request)
