"""Session cookies for Dev Portal and Business Console — Phase 5."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Literal

from server.config.env import get_settings

SessionKind = Literal["dev", "app"]
_COOKIE_DEV = "dev_session"
_COOKIE_APP = "app_session"
_COOKIE_CSRF_DEV = "dev_csrf"
_COOKIE_CSRF_APP = "app_csrf"
_TTL_SEC = 86400 * 7


@dataclass
class SessionData:
    kind: SessionKind
    subject: str
    tenant_id: str | None
    role: str
    issued_at: int


def _sign(payload: str) -> str:
    secret = get_settings().session_secret
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_session_token(kind: SessionKind, subject: str, tenant_id: str | None, role: str) -> str:
    issued = int(time.time())
    body = f"{kind}|{subject}|{tenant_id or ''}|{role}|{issued}"
    return f"{body}|{_sign(body)}"


def parse_session_token(token: str, expected_kind: SessionKind | None = None) -> SessionData | None:
    if not token or token.count("|") < 5:
        return None
    parts = token.split("|")
    sig = parts[-1]
    body = "|".join(parts[:-1])
    if _sign(body) != sig:
        return None
    kind, subject, tenant_id, role, issued_s = parts[0], parts[1], parts[2], parts[3], parts[4]
    if expected_kind and kind != expected_kind:
        return None
    try:
        issued = int(issued_s)
    except ValueError:
        return None
    if time.time() - issued > _TTL_SEC:
        return None
    tenant = tenant_id if tenant_id else None
    return SessionData(kind=kind, subject=subject, tenant_id=tenant, role=role, issued_at=issued)


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(header_token: str | None, cookie_token: str | None) -> bool:
    if not header_token or not cookie_token:
        return False
    return hmac.compare_digest(header_token, cookie_token)


def cookie_names() -> dict[str, str]:
    return {
        "dev": _COOKIE_DEV,
        "app": _COOKIE_APP,
        "dev_csrf": _COOKIE_CSRF_DEV,
        "app_csrf": _COOKIE_CSRF_APP,
    }


def csrf_cookie_for_kind(kind: SessionKind) -> str:
    names = cookie_names()
    return names["dev_csrf"] if kind == "dev" else names["app_csrf"]
