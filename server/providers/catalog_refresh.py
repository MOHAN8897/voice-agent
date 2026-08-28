"""Refresh provider registry when dev overlay or env changes."""
from __future__ import annotations

from server.config.env import get_settings
from server.providers.registry import ProviderRegistry, get_provider_registry, init_provider_registry


def refresh_provider_registry() -> ProviderRegistry:
    """Reload dev secrets overlay and rebuild catalog (development only)."""
    settings = get_settings()
    if settings.app_environment != "development":
        return get_provider_registry()

    from server.services.dev_secrets_store import dev_secrets_store

    dev_secrets_store.reload()
    return init_provider_registry(settings)


def get_fresh_catalog() -> dict:
    return refresh_provider_registry().get_catalog()
