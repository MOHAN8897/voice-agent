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
    tenant_id, _ = await resolve_calls_scope(request, authorization)
    return tenant_id


async def resolve_calls_scope(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> tuple[str, bool]:
    """Tenant id for the caller plus whether they may see internal economics.

    Call detail carries wholesale carrier cost, upstream model rates and the resolved
    provider stack. Those are the platform's numbers, so the endpoint needs to know the
    viewer's role to decide what to send — the tenant id alone cannot express that.
    """
    from server.services.saas.call_redaction import is_internal_viewer

    settings = get_settings()
    if settings.saas_auth_enabled:
        principal = await require_subscriber_jwt(request, authorization)
        require_subscriber_permission(principal, "app.calls.read")
        return str(principal.tenant_id), is_internal_viewer(principal.role)
    tenant_id = request.query_params.get("tenantId") or request.query_params.get("tenant_id")
    if tenant_id:
        return tenant_id, True
    return tenant_id_from_request(request), True


async def resolve_prompt_preview_tenant_id(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """Allow signed Dev Portal operators; keep subscriber previews tenant-scoped."""
    from server.auth.dependencies import require_permission
    from server.auth.session import cookie_names, parse_session_token

    names = cookie_names()
    session = parse_session_token(request.cookies.get(names["dev"], ""), "dev")
    if session is not None:
        require_permission(session, "dev.platform_brain")
        return None
    # Only a Dev Portal operator sees every tenant; a legacy app console cookie stays
    # scoped to the tenant it was issued for.
    app = parse_session_token(request.cookies.get(names["app"], ""), "app")
    if app is not None and app.tenant_id and not authorization:
        require_permission(app, "app.test_studio")
        return str(app.tenant_id)
    return await resolve_calls_tenant_id(request, authorization)
