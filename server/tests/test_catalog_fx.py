"""Provider catalog applies live USD→INR."""
from __future__ import annotations


def test_apply_live_fx_to_catalog(monkeypatch):
    from server.config.env import get_settings
    from server.providers.catalog_refresh import apply_live_fx_to_catalog
    from server.services.usage_pricing import clear_fx_live_cache

    clear_fx_live_cache()
    monkeypatch.setenv("FX_RATE_LIVE", "true")
    monkeypatch.setenv("FX_RATE_INR", "95.64")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "server.services.usage_pricing._fetch_usd_inr",
        lambda: (91.25, "2026-09-27"),
    )
    out = apply_live_fx_to_catalog({"pricing_metadata": {"updated_at": "x"}, "providers": []})
    assert out["fx_rate_inr"] == 91.25
    assert out["fx_source"] == "live"
    assert out["fx_as_of"] == "2026-09-27"
    assert out["pricing_metadata"]["fx_rate_inr"] == 91.25
    get_settings.cache_clear()
    clear_fx_live_cache()
