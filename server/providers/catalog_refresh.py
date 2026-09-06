"""Refresh provider registry when dev overlay or env changes."""
from __future__ import annotations

from server.config.env import get_settings
from server.providers.registry import ProviderRegistry, get_provider_registry, init_provider_registry
from server.services.dev_runtime import effective_app_environment


def refresh_provider_registry() -> ProviderRegistry:
    """Reload dev secrets overlay and rebuild catalog (development only)."""
    if effective_app_environment() != "development":
        return get_provider_registry()

    from server.services.dev_secrets_store import dev_secrets_store

    dev_secrets_store.reload()
    return init_provider_registry(get_settings())


def get_fresh_catalog() -> dict:
    return refresh_provider_registry().get_catalog()
