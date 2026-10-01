"""Google OAuth state + config helpers."""
from __future__ import annotations

from server.services.saas.google_oauth_service import (
    consume_auth_handoff,
    consume_oauth_state,
    create_auth_handoff,
    google_signin_config,
    new_oauth_state,
)


def test_oauth_state_single_use():
    state = new_oauth_state("http://localhost:5173")
    info = consume_oauth_state(state)
    assert info is not None
    assert info.get("return_to") == "http://localhost:5173"
    assert consume_oauth_state(state) is None


def test_auth_handoff_single_use():
    hid = create_auth_handoff({"accessToken": "a", "refreshToken": "r", "user": {"email": "x@y.z"}})
    data = consume_auth_handoff(hid)
    assert data is not None
    assert data["accessToken"] == "a"
    assert consume_auth_handoff(hid) is None


def test_google_signin_config_shape():
    cfg = google_signin_config()
    assert "enabled" in cfg
    assert "clientId" in cfg
    assert "redirectUri" in cfg
    assert "javascriptOrigins" in cfg
    assert cfg["redirectUri"].endswith("/api/auth/google/callback")
