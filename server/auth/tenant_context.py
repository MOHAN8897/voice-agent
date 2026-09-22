"""Tenant context from auth session — Phase 5."""
from __future__ import annotations

from fastapi import Request

from server.auth.session import cookie_names, parse_session_token
from server.config.env import get_settings


def tenant_id_from_request(request: Request) -> str:
    """Resolve tenant_id from Bearer JWT, app/dev session, or DEFAULT_TENANT_ID."""
    settings = get_settings()
    if settings.saas_auth_enabled:
        from server.auth.jwt_tokens import decode_access_token

        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            claims = decode_access_token(auth.split(" ", 1)[1].strip())
            if claims and claims.tenant_id:
                return claims.tenant_id
    names = cookie_names()
    for cookie_name, kind in ((names["app"], "app"), (names["dev"], "dev")):
        token = request.cookies.get(cookie_name)
        session = parse_session_token(token or "", kind)
        if session and session.tenant_id:
            return session.tenant_id
    return settings.default_tenant_id
