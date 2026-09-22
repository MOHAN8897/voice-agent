"""Shared Google OAuth redirect defaults (Vite proxy = same-origin cookies)."""
from __future__ import annotations

from server.config.env import get_settings


def google_oauth_redirect_uri() -> str:
    settings = get_settings()
    if settings.google_oauth_redirect_uri:
        return settings.google_oauth_redirect_uri.strip()
    base = settings.voxly_frontend_url.rstrip("/")
    return f"{base}/api/auth/google/callback"
