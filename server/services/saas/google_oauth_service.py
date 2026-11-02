"""Google Sign-In — ID token verify + OAuth redirect + same-origin handoff."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

_OAUTH_STATE_TTL_SEC = 600
_HANDOFF_TTL_SEC = 90
# Process-local fallbacks for when Redis is not available. With Redis, states and
# handoffs are shared by every worker (a callback can land on any of them) and expire
# on their own.
# state -> {"at": float, "return_to": str | None, ...}
_oauth_states: dict[str, dict[str, Any]] = {}
# handoff_id -> auth payload + exp
_auth_handoffs: dict[str, dict[str, Any]] = {}
_MAX_LOCAL_ENTRIES = 5000
#: HttpOnly cookie holding sha256(state), set by /google/start in the browser that began
#: the sign-in; the callback refuses a state that browser did not start (login CSRF).
STATE_COOKIE = "dialtact_oauth_state"

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


def google_oauth_authorize_url(state: str, redirect_uri: str | None = None) -> str:
    settings = get_settings()
    if not settings.google_oauth_client_id:
        raise ValueError("google_not_configured")
    redirect = redirect_uri or google_oauth_redirect_uri()
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


async def exchange_code_for_tokens(code: str, redirect_uri: str | None = None) -> str:
    settings = get_settings()
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise ValueError("google_not_configured")
    redirect = redirect_uri or google_oauth_redirect_uri()
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


def state_cookie_value(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


async def _kv_put(prefix: str, key: str, value: dict[str, Any], ttl: int, local: dict[str, dict[str, Any]]) -> None:
    from server.utils.cache import _client

    client = await _client()
    if client is not None:
        try:
            await client.set(f"{prefix}:{key}", json.dumps(value), ex=ttl)
            return
        except Exception:
            pass
    now = time.time()
    for stale in [k for k, v in local.items() if now > float(v.get("exp", 0))]:
        local.pop(stale, None)
    if len(local) >= _MAX_LOCAL_ENTRIES:
        local.pop(next(iter(local)))
    local[key] = {**value, "exp": now + ttl}


async def _kv_pop(prefix: str, key: str, local: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    from server.utils.cache import _client

    client = await _client()
    if client is not None:
        try:
            pipe = client.pipeline(transaction=True)
            pipe.get(f"{prefix}:{key}")
            pipe.delete(f"{prefix}:{key}")
            raw, _ = await pipe.execute()
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
    entry = local.pop(key, None)
    if entry is None or time.time() > float(entry.get("exp", 0)):
        return None
    return {k: v for k, v in entry.items() if k != "exp"}


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
        settings.dialtact_frontend_url.rstrip("/"),
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://app-dev.dialtact.com",
        "https://dialtact.com",
        "https://www.dialtact.com",
        "https://app.dialtact.com",
        "https://app-dev.hustlelabs.in",
    }
    if candidate in allowed:
        return candidate
    host = parsed.hostname or ""
    # Any local dev server may sign in during development; never in production.
    if host in ("localhost", "127.0.0.1") and parsed.scheme == "http" and settings.app_environment == "development":
        return candidate
    return None


async def new_oauth_state(return_to: str | None = None, *, start_host: str | None = None) -> tuple[str, dict[str, Any]]:
    """A fresh state and its record. `bound` is true when the sign-in started on the same
    host the callback will land on, so the state cookie set now will be there to check."""
    state = secrets.token_urlsafe(24)
    origin = allowed_frontend_origin(return_to)
    redirect = google_oauth_redirect_uri(origin)
    bound = bool(start_host) and (urlparse(redirect).hostname or "").lower() == start_host.lower()
    entry = {"at": time.time(), "return_to": origin, "redirect_uri": redirect, "bound": bound}
    await _kv_put("oauth:state", state, entry, _OAUTH_STATE_TTL_SEC, _oauth_states)
    return state, entry


async def consume_oauth_state(state: str | None) -> dict[str, Any] | None:
    """Validate + pop OAuth state. Returns {"return_to", "redirect_uri", "bound"} or None if invalid."""
    if not state:
        return None
    entry = await _kv_pop("oauth:state", state, _oauth_states)
    if entry is None or time.time() - float(entry.get("at", 0)) > _OAUTH_STATE_TTL_SEC:
        return None
    return {
        "return_to": entry.get("return_to"),
        "redirect_uri": entry.get("redirect_uri"),
        "bound": bool(entry.get("bound")),
    }


async def create_auth_handoff(payload: dict[str, Any]) -> str:
    """Store login payload briefly; SPA redeems via same-origin POST to set refresh cookie."""
    hid = secrets.token_urlsafe(24)
    await _kv_put("oauth:handoff", hid, payload, _HANDOFF_TTL_SEC, _auth_handoffs)
    return hid


async def consume_auth_handoff(handoff_id: str | None) -> dict[str, Any] | None:
    if not handoff_id:
        return None
    return await _kv_pop("oauth:handoff", handoff_id, _auth_handoffs)


def google_signin_config() -> dict[str, Any]:
    settings = get_settings()
    configured = bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)
    redirect = google_oauth_redirect_uri()
    return {
        "enabled": configured,
        "clientId": settings.google_oauth_client_id or "",
        "redirectUri": redirect,
        "javascriptOrigins": [
            settings.dialtact_frontend_url.rstrip("/"),
            "https://dialtact.com",
            "https://www.dialtact.com",
            "https://app-dev.dialtact.com",
            "http://localhost:5173",
        ],
    }
