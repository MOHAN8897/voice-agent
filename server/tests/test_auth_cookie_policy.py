"""Auth cookie + no-store policy helpers."""
from __future__ import annotations

import os

from server.auth.subscriber_cookies import _cookie_opts


def test_cookie_secure_defaults_off_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.delenv("VOXLY_COOKIE_SECURE", raising=False)
    from server.config.env import get_settings

    get_settings.cache_clear()
    opts = _cookie_opts()
    assert opts["httponly"] is True
    assert opts["samesite"] == "lax"
    assert opts["secure"] is False
    get_settings.cache_clear()


def test_cookie_secure_override(monkeypatch):
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("VOXLY_COOKIE_SECURE", "1")
    from server.config.env import get_settings

    get_settings.cache_clear()
    assert _cookie_opts()["secure"] is True
    monkeypatch.setenv("VOXLY_COOKIE_SECURE", "0")
    assert _cookie_opts()["secure"] is False
    get_settings.cache_clear()
