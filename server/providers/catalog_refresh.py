"""Refresh provider registry when dev overlay or env changes."""
from __future__ import annotations

from typing import Any

from server.config.env import get_settings
from server.providers.registry import ProviderRegistry, get_provider_registry, init_provider_registry
from server.services.dev_runtime import effective_app_environment


def apply_live_fx_to_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """Refresh USD→INR on every catalog read (live API when FX_RATE_LIVE=true)."""
    from server.services.usage_pricing import build_pricing_metadata, resolve_fx_rate_inr

    fx_info = resolve_fx_rate_inr()
    rate = float(fx_info["rate"])
    out = dict(catalog)
    out["fx_rate_inr"] = rate
    out["fx_source"] = fx_info.get("source")
    out["fx_as_of"] = fx_info.get("as_of")
    meta = dict(out.get("pricing_metadata") or {})
    meta.update(build_pricing_metadata(rate))
    meta["fx_rate_inr"] = rate
    meta["fx_source"] = fx_info.get("source")
    meta["fx_as_of"] = fx_info.get("as_of")
    out["pricing_metadata"] = meta
    return out


def refresh_provider_registry() -> ProviderRegistry:
    """Reload dev secrets overlay and rebuild catalog (development only)."""
    if effective_app_environment() != "development":
        return get_provider_registry()

    from server.services.dev_secrets_store import dev_secrets_store

    dev_secrets_store.reload()
    return init_provider_registry(get_settings())


def get_fresh_catalog() -> dict:
    if effective_app_environment() == "development":
        reg = refresh_provider_registry()
    else:
        reg = get_provider_registry()
    return apply_live_fx_to_catalog(reg.get_catalog())


def get_live_fx() -> dict[str, Any]:
    from server.services.usage_pricing import resolve_fx_rate_inr

    info = resolve_fx_rate_inr()
    return {
        "fx_rate_inr": float(info["rate"]),
        "source": info.get("source"),
        "as_of": info.get("as_of"),
    }
