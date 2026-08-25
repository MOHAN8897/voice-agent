"""FastAPI auth dependencies — Phase 5."""
from __future__ import annotations

from fastapi import Header, HTTPException, Request

from server.auth.rbac import role_has_permission
from server.auth.session import cookie_names, csrf_cookie_for_kind, parse_session_token, SessionData, verify_csrf
from server.config.env import get_settings


def _get_cookie(request: Request, name: str) -> str | None:
    return request.cookies.get(name)


async def require_dev_session(
    request: Request,
    x_csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
) -> SessionData:
    names = cookie_names()
    token = _get_cookie(request, names["dev"])
    session = parse_session_token(token or "", "dev")
    if session is None:
        settings = get_settings()
        if settings.dev_portal_username and settings.dev_portal_password:
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "auth_error", "message": "Dev session required"}},
            )
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_error", "message": "Dev portal credentials not configured"}},
        )
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_cookie = _get_cookie(request, names["dev_csrf"])
        if not verify_csrf(x_csrf_token, csrf_cookie):
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "auth_error", "message": "Invalid CSRF token"}},
            )
    return session


async def require_app_session(
    request: Request,
    x_csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
) -> SessionData:
    names = cookie_names()
    token = _get_cookie(request, names["app"])
    session = parse_session_token(token or "", "app")
    if session is None:
        settings = get_settings()
        if settings.app_console_username and settings.app_console_password:
            raise HTTPException(
                status_code=401,
                detail={"error": {"code": "auth_error", "message": "App session required"}},
            )
        return SessionData(
            kind="app",
            subject="dev-stub",
            tenant_id=settings.default_tenant_id,
            role="developer",
            issued_at=0,
        )
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_cookie = _get_cookie(request, names["app_csrf"])
        if not verify_csrf(x_csrf_token, csrf_cookie):
            raise HTTPException(
                status_code=403,
                detail={"error": {"code": "auth_error", "message": "Invalid CSRF token"}},
            )
    return session


def require_permission(session: SessionData, permission: str) -> None:
    if not role_has_permission(session.role, permission):
        raise HTTPException(status_code=403, detail={"error": {"code": "auth_error", "message": "Permission denied"}})
