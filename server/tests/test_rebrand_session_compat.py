"""The Voxly -> Dialtact rename must not log anybody out or drop deployment config."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import Response

from server.auth import subscriber_cookies as cookies


def test_legacy_refresh_cookie_is_still_accepted():
    request = SimpleNamespace(cookies={cookies.LEGACY_REFRESH_COOKIE: "old-token"})
    assert cookies.refresh_from_request(request, None) == "old-token"


def test_current_refresh_cookie_wins_over_legacy():
    request = SimpleNamespace(
        cookies={cookies.REFRESH_COOKIE: "new-token", cookies.LEGACY_REFRESH_COOKIE: "old-token"}
    )
    assert cookies.refresh_from_request(request, None) == "new-token"


def test_logout_clears_both_cookie_names():
    response = Response()
    cookies.clear_refresh_cookie(response)
    headers = " ".join(v.decode() for k, v in response.raw_headers if k == b"set-cookie")
    assert f"{cookies.REFRESH_COOKIE}=" in headers
    assert f"{cookies.LEGACY_REFRESH_COOKIE}=" in headers


def test_old_frontend_url_env_name_still_configures_the_app(monkeypatch):
    from server.config.env import Settings

    monkeypatch.delenv("DIALTACT_FRONTEND_URL", raising=False)
    monkeypatch.setenv("VOXLY_FRONTEND_URL", "https://app.example.test")
    assert Settings().dialtact_frontend_url == "https://app.example.test"
