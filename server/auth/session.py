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
    #: Set for dev sessions held by a stored platform-admin account
    #: (`a:<account_id>:<epoch>`); None for the env-configured built-in login.
    account_ref: str | None = None


def _sign(payload: str) -> str:
    secret = get_settings().session_secret
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_session_token(
    kind: SessionKind,
    subject: str,
    tenant_id: str | None,
    role: str,
    account_ref: str | None = None,
) -> str:
    issued = int(time.time())
    body = f"{kind}|{subject}|{tenant_id or ''}|{role}|{issued}"
    if account_ref:
        body = f"{body}|{account_ref}"
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
    ref = parts[5] if len(parts) >= 7 and parts[5] else None
    if kind == "dev":
        if ref:
            # A stored admin account: valid only while the account is active and the
            # token's epoch is current, and it authorizes with the *current* role.
            from server.auth.admin_sessions import resolve_account_ref

            state = resolve_account_ref(ref)
            if state is None:
                return None
            subject, role = state.username, state.role
        elif _is_builtin_dev_subject(subject) and role == "developer":
            # Sessions issued before admin roles existed: the env login is the
            # built-in super admin.
            role = "super_admin"
    return SessionData(kind=kind, subject=subject, tenant_id=tenant, role=role, issued_at=issued, account_ref=ref)


def _is_builtin_dev_subject(subject: str) -> bool:
    expected = (get_settings().dev_portal_username or "").strip()
    return bool(expected) and expected.casefold() == (subject or "").strip().casefold()


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
