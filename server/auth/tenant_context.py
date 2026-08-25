"""Tenant context from auth session — Phase 5."""
from __future__ import annotations

from fastapi import Request

from server.auth.session import cookie_names, parse_session_token
from server.config.env import get_settings


def tenant_id_from_request(request: Request) -> str:
    """Resolve tenant_id from app/dev session or DEFAULT_TENANT_ID."""
    settings = get_settings()
    names = cookie_names()
    for cookie_name, kind in ((names["app"], "app"), (names["dev"], "dev")):
        token = request.cookies.get(cookie_name)
        session = parse_session_token(token or "", kind)
        if session and session.tenant_id:
            return session.tenant_id
    return settings.default_tenant_id
