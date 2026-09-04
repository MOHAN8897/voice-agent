"""Public URL resolution tests."""
from unittest.mock import patch

from server.config.urls import public_api_base


def test_public_api_base_prefers_public_tunnel_over_stale_exotel_secret(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("PUBLIC_TUNNEL_URL", "https://api-dev.hustlelabs.in")
    monkeypatch.setenv("EXOTEL_WEBHOOK_BASE_URL", "https://api-dev.hustlelabs.in")

    from server.config.env import get_settings

    get_settings.cache_clear()

    overlay = {"exotel_webhook_base_url": "https://dead-quick-tunnel.trycloudflare.com"}

    with patch("server.config.urls.dev_secrets_store.effective", side_effect=lambda field, default=None: overlay.get(field, default)):
        assert public_api_base() == "https://api-dev.hustlelabs.in"

    get_settings.cache_clear()
