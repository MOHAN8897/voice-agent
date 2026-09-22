"""Google Sign-In — ID token verify + OAuth redirect."""
from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

_OAUTH_STATE_TTL_SEC = 600
_oauth_states: dict[str, float] = {}

from server.config.env import get_settings
from server.services.saas import auth_service
from server.services.saas.google_oauth_urls import google_oauth_redirect_uri


async def verify_google_id_token(id_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
        )
    if resp.status_code != 200:
        raise ValueError("invalid_token")
    data = resp.json()
    settings = get_settings()
    aud = data.get("aud")
    if settings.google_oauth_client_id and aud != settings.google_oauth_client_id:
        raise ValueError("invalid_audience")
    if data.get("email_verified") not in ("true", True, "1", 1):
        raise ValueError("email_not_verified")
    return data


async def login_or_register_google(id_token: str) -> dict[str, Any]:
    profile = await verify_google_id_token(id_token)
    email = str(profile.get("email") or "").lower()
    name = str(profile.get("name") or email.split("@")[0])
    if not email:
        raise ValueError("invalid_token")
    return await auth_service.login_or_create_oauth_user(
        email=email,
        full_name=name,
        provider="google",
    )


def google_oauth_authorize_url(state: str) -> str:
    settings = get_settings()
    if not settings.google_oauth_client_id:
        raise ValueError("google_not_configured")
    redirect = google_oauth_redirect_uri()
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> str:
    settings = get_settings()
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise ValueError("google_not_configured")
    redirect = google_oauth_redirect_uri()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        raise ValueError("token_exchange_failed")
    id_token = resp.json().get("id_token")
    if not id_token:
        raise ValueError("no_id_token")
    return str(id_token)


def new_oauth_state() -> str:
    now = time.time()
    expired = [k for k, t in _oauth_states.items() if now - t > _OAUTH_STATE_TTL_SEC]
    for k in expired:
        _oauth_states.pop(k, None)
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = now
    return state


def consume_oauth_state(state: str | None) -> bool:
    if not state:
        return False
    created = _oauth_states.pop(state, None)
    if created is None:
        return False
    return time.time() - created <= _OAUTH_STATE_TTL_SEC


def google_signin_config() -> dict[str, Any]:
    settings = get_settings()
    configured = bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)
    redirect = google_oauth_redirect_uri()
    return {
        "enabled": configured,
        "clientId": settings.google_oauth_client_id or "",
        "redirectUri": redirect,
        "javascriptOrigins": [settings.voxly_frontend_url.rstrip("/")],
    }
