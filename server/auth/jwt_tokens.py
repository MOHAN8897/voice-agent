"""JWT access tokens for SaaS subscriber API."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from server.config.env import get_settings


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: str
    tenant_id: str
    role: str
    email: str


def create_access_token(claims: AccessTokenClaims) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.jwt_access_ttl_minutes * 60
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": claims.user_id,
        "tid": claims.tenant_id,
        "role": claims.role,
        "email": claims.email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, expires_in


def decode_access_token(token: str) -> AccessTokenClaims | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    tid = payload.get("tid")
    role = payload.get("role")
    email = payload.get("email")
    if not sub or not tid or not role:
        return None
    return AccessTokenClaims(
        user_id=str(sub),
        tenant_id=str(tid),
        role=str(role),
        email=str(email or ""),
    )
