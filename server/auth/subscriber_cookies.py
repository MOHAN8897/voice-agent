"""HttpOnly refresh-token cookies for subscriber auth (Voxly / SPA)."""
from __future__ import annotations

import os

from fastapi import Request, Response

from server.config.env import get_settings

REFRESH_COOKIE = "voxly_refresh"


def _cookie_opts() -> dict:
    settings = get_settings()
    # Secure in production. Localhost HTTP must keep Secure=false or the browser
    # drops the cookie. Optional VOXLY_COOKIE_SECURE=1 when SPA is HTTPS-only.
    override = (os.getenv("VOXLY_COOKIE_SECURE") or "").strip().lower()
    if override in ("1", "true", "yes"):
        secure = True
    elif override in ("0", "false", "no"):
        secure = False
    else:
        secure = settings.app_environment == "production"
    return {"httponly": True, "secure": secure, "samesite": "lax", "path": "/"}


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    max_age = settings.jwt_refresh_ttl_days * 86400
    response.set_cookie(REFRESH_COOKIE, refresh_token, max_age=max_age, **_cookie_opts())


def clear_refresh_cookie(response: Response) -> None:
    opts = _cookie_opts()
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/",
        httponly=True,
        samesite=opts["samesite"],
        secure=opts["secure"],
    )
    # Ensure cookie is cleared for browsers that ignore delete_cookie without max_age=0
    response.set_cookie(
        REFRESH_COOKIE,
        "",
        max_age=0,
        path="/",
        httponly=True,
        samesite=opts["samesite"],
        secure=opts["secure"],
    )


def refresh_from_request(request: Request, body_token: str | None) -> str | None:
    if body_token:
        return body_token
    return request.cookies.get(REFRESH_COOKIE)
