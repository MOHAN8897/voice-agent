"""SaaS Phase 1 — JWT and auth helpers (no live DB required)."""
from __future__ import annotations

import uuid

from server.auth.jwt_tokens import AccessTokenClaims, create_access_token, decode_access_token
from server.config.env import get_settings


def test_access_token_roundtrip():
    get_settings.cache_clear()
    claims = AccessTokenClaims(
        user_id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        role="customer_admin",
        email="test@example.com",
    )
    token, expires_in = create_access_token(claims)
    assert expires_in > 0
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded.user_id == claims.user_id
    assert decoded.tenant_id == claims.tenant_id
    assert decoded.role == claims.role


def test_access_token_rejects_garbage():
    assert decode_access_token("not-a-jwt") is None
