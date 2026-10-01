"""Google Sign-In — ID token verify + OAuth redirect + same-origin handoff."""
from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

_OAUTH_STATE_TTL_SEC = 600
_HANDOFF_TTL_SEC = 90
# state -> {"at": float, "return_to": str | None}
_oauth_states: dict[str, dict[str, Any]] = {}
# handoff_id -> auth payload + exp
_auth_handoffs: dict[str, dict[str, Any]] = {}

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


def allowed_frontend_origin(origin: str | None) -> str | None:
    """Return a normalized origin if allowlisted; else None."""
    if not origin:
        return None
    raw = origin.strip().rstrip("/")
    try:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    except Exception:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    candidate = f"{parsed.scheme}://{parsed.netloc}"
    settings = get_settings()
    allowed = {
        settings.voxly_frontend_url.rstrip("/"),
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://app-dev.hustlelabs.in",
    }
    if candidate in allowed:
        return candidate
    host = parsed.hostname or ""
    if host in ("localhost", "127.0.0.1") and parsed.scheme == "http":
        return candidate
    return None


def new_oauth_state(return_to: str | None = None) -> str:
    now = time.time()
    expired = [k for k, v in _oauth_states.items() if now - float(v.get("at", 0)) > _OAUTH_STATE_TTL_SEC]
    for k in expired:
        _oauth_states.pop(k, None)
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = {"at": now, "return_to": allowed_frontend_origin(return_to)}
    return state


def consume_oauth_state(state: str | None) -> dict[str, Any] | None:
    """Validate + pop OAuth state. Returns {"return_to": origin|None} or None if invalid."""
    if not state:
        return None
    entry = _oauth_states.pop(state, None)
    if entry is None:
        return None
    # Back-compat: older entries were plain floats
    if isinstance(entry, (int, float)):
        if time.time() - float(entry) > _OAUTH_STATE_TTL_SEC:
            return None
        return {"return_to": None}
    if time.time() - float(entry.get("at", 0)) > _OAUTH_STATE_TTL_SEC:
        return None
    return {"return_to": entry.get("return_to")}


def create_auth_handoff(payload: dict[str, Any]) -> str:
    """Store login payload briefly; SPA redeems via same-origin POST to set refresh cookie."""
    now = time.time()
    expired = [k for k, v in _auth_handoffs.items() if now > float(v.get("exp", 0))]
    for k in expired:
        _auth_handoffs.pop(k, None)
    hid = secrets.token_urlsafe(24)
    _auth_handoffs[hid] = {**payload, "exp": now + _HANDOFF_TTL_SEC}
    return hid


def consume_auth_handoff(handoff_id: str | None) -> dict[str, Any] | None:
    if not handoff_id:
        return None
    entry = _auth_handoffs.pop(handoff_id, None)
    if entry is None:
        return None
    if time.time() > float(entry.get("exp", 0)):
        return None
    return {k: v for k, v in entry.items() if k != "exp"}


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
