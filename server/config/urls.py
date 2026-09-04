"""Central URL resolution — single source for API, app, webhooks, and WSS."""
from __future__ import annotations

from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store


def _strip(url: str) -> str:
    return str(url).rstrip("/")


def public_api_base() -> str:
    """
    Public API base used for Telnyx/Plivo WSS, Exotel webhooks, and external callbacks.
    Priority: PUBLIC_TUNNEL_URL (named tunnel) → EXOTEL_WEBHOOK_BASE_URL → local API.

    PUBLIC_TUNNEL_URL wins so a stale dev_secrets exotel_webhook_base_url from an old
    quick tunnel cannot break Telnyx media streaming.
    """
    settings = get_settings()
    for key, fallback in (
        ("public_tunnel_url", settings.public_tunnel_url),
        ("exotel_webhook_base_url", settings.exotel_webhook_base_url),
    ):
        val = dev_secrets_store.effective(key, fallback)
        if val:
            return _strip(str(val))
    return f"http://127.0.0.1:{settings.port}"


def public_app_base() -> str:
    """Public website URL (marketing / dev portal / share link)."""
    settings = get_settings()
    val = dev_secrets_store.effective("client_url", settings.client_url)
    return _strip(str(val or "http://localhost:3000"))


def ws_public_base() -> str:
    """WebSocket base for PSTN AgentStream and browser WS when using public API."""
    api = public_api_base()
    if api.startswith("https://"):
        return "wss://" + api[len("https://") :]
    if api.startswith("http://"):
        return "ws://" + api[len("http://") :]
    return api


def local_api_base() -> str:
    settings = get_settings()
    return f"http://127.0.0.1:{settings.port}"
