"""HttpOnly refresh-token cookies for subscriber auth (Voxly / SPA)."""
from __future__ import annotations

from fastapi import Request, Response

from server.config.env import get_settings

REFRESH_COOKIE = "voxly_refresh"


def _cookie_opts() -> dict:
    secure = get_settings().app_environment == "production"
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
