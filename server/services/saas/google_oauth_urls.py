"""Shared Google OAuth redirect defaults (Vite proxy = same-origin cookies)."""
from __future__ import annotations

from server.config.env import get_settings


def google_oauth_redirect_uri(origin: str | None = None) -> str:
    if origin:
        from server.services.saas.google_oauth_service import allowed_frontend_origin

        allowed = allowed_frontend_origin(origin)
        if allowed:
            canonical = allowed.replace("://www.dialtact.com", "://dialtact.com")
            return f"{canonical.rstrip('/')}/api/auth/google/callback"
    settings = get_settings()
    if settings.google_oauth_redirect_uri:
        return settings.google_oauth_redirect_uri.strip()
    base = settings.voxly_frontend_url.rstrip("/")
    canonical_base = base.replace("://www.dialtact.com", "://dialtact.com")
    return f"{canonical_base}/api/auth/google/callback"
