"""Auth routes — Dev Portal and Business Console login."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from server.auth.passwords import verify_portal_password
from server.auth.rbac import ROLE_DEVELOPER
from server.auth.session import cookie_names, create_csrf_token, create_session_token, parse_session_token
from server.config.env import get_settings
from server.utils.rate_limiter import RateLimiter

router = APIRouter()
_login_limiter = RateLimiter(max_requests=10, window_s=300)


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


def _cookie_opts() -> dict:
    secure = get_settings().app_environment == "production"
    return {"httponly": True, "secure": secure, "samesite": "lax", "path": "/"}


def _set_session_cookies(response: Response, kind: str, token: str, csrf: str) -> None:
    names = cookie_names()
    cookie_name = names["dev"] if kind == "dev" else names["app"]
    csrf_name = names["dev_csrf"] if kind == "dev" else names["app_csrf"]
    opts = _cookie_opts()
    response.set_cookie(cookie_name, token, max_age=86400 * 7, **opts)
    response.set_cookie(csrf_name, csrf, httponly=False, secure=opts["secure"], samesite="lax", path="/", max_age=86400 * 7)


def _clear_session_cookies(response: Response, kind: str) -> None:
    names = cookie_names()
    cookie_name = names["dev"] if kind == "dev" else names["app"]
    csrf_name = names["dev_csrf"] if kind == "dev" else names["app_csrf"]
    opts = _cookie_opts()
    response.delete_cookie(
        cookie_name,
        path="/",
        httponly=True,
        samesite=opts["samesite"],
        secure=opts["secure"],
    )
    response.delete_cookie(
        csrf_name,
        path="/",
        httponly=False,
        samesite=opts["samesite"],
        secure=opts["secure"],
    )


@router.post("/api/dev/login")
async def dev_login(body: LoginBody, request: Request, response: Response):
    settings = get_settings()
    if not settings.dev_portal_username or not settings.dev_portal_password:
        return {"ok": False, "error": {"code": "auth_error", "message": "Dev portal not configured"}}
    ip = request.client.host if request.client else "unknown"
    allowed, retry = _login_limiter.allow(f"dev:{ip}:{body.username}")
    if not allowed:
        return {
            "ok": False,
            "error": {"code": "rate_limit", "message": "Too many login attempts", "retry_after": retry},
        }
    if body.username != settings.dev_portal_username or not verify_portal_password(
        settings.dev_portal_password, body.password
    ):
        return {"ok": False, "error": {"code": "auth_error", "message": "Invalid credentials"}}
    csrf = create_csrf_token()
    token = create_session_token("dev", body.username, settings.default_tenant_id, ROLE_DEVELOPER)
    _set_session_cookies(response, "dev", token, csrf)
    return {"ok": True, "role": ROLE_DEVELOPER, "csrf_token": csrf}


@router.post("/api/dev/logout")
async def dev_logout(response: Response):
    _clear_session_cookies(response, "dev")
    return {"ok": True}


@router.get("/api/dev/logout")
async def dev_logout_get(response: Response):
    _clear_session_cookies(response, "dev")
    return {"ok": True}


@router.post("/api/app/login")
async def app_login(body: LoginBody, response: Response):
    settings = get_settings()
    if settings.saas_auth_enabled:
        raise HTTPException(
            status_code=410,
            detail={
                "error": {
                    "code": "deprecated",
                    "message": "Use POST /api/auth/login with email and password",
                }
            },
        )
    if not settings.app_console_username or not settings.app_console_password:
        return {"ok": False, "error": {"code": "auth_error", "message": "App login not configured"}}
    allowed, retry = _login_limiter.allow(f"app:{body.username}")
    if not allowed:
        return {
            "ok": False,
            "error": {"code": "rate_limit", "message": "Too many login attempts", "retry_after": retry},
        }
    if body.username != settings.app_console_username or not verify_portal_password(
        settings.app_console_password, body.password
    ):
        return {"ok": False, "error": {"code": "auth_error", "message": "Invalid credentials"}}
    csrf = create_csrf_token()
    token = create_session_token("app", body.username, settings.default_tenant_id, ROLE_DEVELOPER)
    _set_session_cookies(response, "app", token, csrf)
    return {"ok": True, "role": ROLE_DEVELOPER, "csrf_token": csrf}


@router.post("/api/app/logout")
async def app_logout(response: Response):
    _clear_session_cookies(response, "app")
    return {"ok": True}


@router.get("/api/app/logout")
async def app_logout_get(response: Response):
    _clear_session_cookies(response, "app")
    return {"ok": True}


@router.get("/api/auth/session")
async def auth_session():
    settings = get_settings()
    return {
        "dev_configured": bool(settings.dev_portal_username and settings.dev_portal_password),
        "app_configured": bool(settings.app_console_username and settings.app_console_password),
        "saas_auth_enabled": settings.saas_auth_enabled,
        "environment": settings.app_environment,
        "default_tenant_id": settings.default_tenant_id,
    }


@router.get("/api/auth/me")
async def auth_me(request: Request):
    settings = get_settings()
    if settings.saas_auth_enabled:
        from server.auth.jwt_tokens import decode_access_token
        from server.services.saas import auth_service as saas_auth

        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            claims = decode_access_token(auth_header.split(" ", 1)[1].strip())
            if claims is None:
                raise HTTPException(
                    status_code=401,
                    detail={"error": {"code": "auth_error", "message": "Invalid or expired token"}},
                )
            import uuid

            try:
                return await saas_auth.get_me(uuid.UUID(claims.user_id), uuid.UUID(claims.tenant_id))
            except ValueError:
                raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Not found"}})
    names = cookie_names()
    session = parse_session_token(request.cookies.get(names["app"]) or "", "app")
    if session:
        csrf = request.cookies.get(names["app_csrf"])
        return {
            "ok": True,
            "authenticated": True,
            "subject": session.subject,
            "role": session.role,
            "tenant_id": session.tenant_id,
            "csrf_token": csrf,
        }
    if settings.app_console_username and settings.app_console_password:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_error", "message": "App session required"}},
        )
    return {"ok": True, "authenticated": False, "subject": "dev-stub", "role": "developer"}


@router.get("/api/auth/dev-me")
async def auth_dev_me(request: Request):
    settings = get_settings()
    names = cookie_names()
    session = parse_session_token(request.cookies.get(names["dev"]) or "", "dev")
    if session:
        csrf = request.cookies.get(names["dev_csrf"])
        return {
            "ok": True,
            "authenticated": True,
            "subject": session.subject,
            "role": session.role,
            "tenant_id": session.tenant_id,
            "csrf_token": csrf,
        }
    if settings.dev_portal_username and settings.dev_portal_password:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_error", "message": "Dev session required"}},
        )
    raise HTTPException(
        status_code=401,
        detail={"error": {"code": "auth_error", "message": "Dev portal credentials not configured"}},
    )
