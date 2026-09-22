"""Google OAuth state + config helpers."""
from __future__ import annotations

from server.services.saas.google_oauth_service import (
    consume_oauth_state,
    google_signin_config,
    new_oauth_state,
)


def test_oauth_state_single_use():
    state = new_oauth_state()
    assert consume_oauth_state(state) is True
    assert consume_oauth_state(state) is False


def test_google_signin_config_shape():
    cfg = google_signin_config()
    assert "enabled" in cfg
    assert "clientId" in cfg
    assert "redirectUri" in cfg
    assert "javascriptOrigins" in cfg
    assert cfg["redirectUri"].endswith("/api/auth/google/callback")
