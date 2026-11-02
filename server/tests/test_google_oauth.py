"""Google OAuth state + config helpers."""
from __future__ import annotations

from server.services.saas.google_oauth_service import (
    consume_auth_handoff,
    consume_oauth_state,
    create_auth_handoff,
    google_signin_config,
    new_oauth_state,
)


async def test_oauth_state_single_use():
    state, entry = await new_oauth_state("http://localhost:5173", start_host="localhost")
    info = await consume_oauth_state(state)
    assert info is not None
    assert info.get("return_to") == "http://localhost:5173"
    # Started on the host the callback lands on, so the callback checks the state cookie.
    assert info.get("bound") is True
    assert await consume_oauth_state(state) is None


async def test_oauth_state_from_another_host_is_not_cookie_bound():
    state, _ = await new_oauth_state("http://localhost:5173", start_host="api.example.com")
    assert (await consume_oauth_state(state))["bound"] is False


async def test_auth_handoff_single_use():
    hid = await create_auth_handoff({"accessToken": "a", "refreshToken": "r", "user": {"email": "x@y.z"}})
    data = await consume_auth_handoff(hid)
    assert data is not None
    assert data["accessToken"] == "a"
    assert await consume_auth_handoff(hid) is None


def test_state_cookie_value_is_a_hash_of_the_state():
    from server.services.saas.google_oauth_service import state_cookie_value

    assert state_cookie_value("abc") != "abc"
    assert state_cookie_value("abc") == state_cookie_value("abc")
    assert len(state_cookie_value("abc")) == 64


def test_google_signin_config_shape():
    cfg = google_signin_config()
    assert "enabled" in cfg
    assert "clientId" in cfg
    assert "redirectUri" in cfg
    assert "javascriptOrigins" in cfg
    assert cfg["redirectUri"].endswith("/api/auth/google/callback")
    assert "https://dialtact.com" in cfg["javascriptOrigins"]


def test_dynamic_redirect_uri_for_dialtact():
    from server.services.saas.google_oauth_urls import google_oauth_redirect_uri

    assert google_oauth_redirect_uri("https://dialtact.com") == "https://dialtact.com/api/auth/google/callback"
    assert google_oauth_redirect_uri("https://www.dialtact.com") == "https://dialtact.com/api/auth/google/callback"
    assert google_oauth_redirect_uri("https://app-dev.dialtact.com") == "https://app-dev.dialtact.com/api/auth/google/callback"
    assert google_oauth_redirect_uri("http://localhost:5173") == "http://localhost:5173/api/auth/google/callback"
    # Malicious or untrusted origins fall back safely
    assert google_oauth_redirect_uri("https://evil-phishing.com") != "https://evil-phishing.com/api/auth/google/callback"
