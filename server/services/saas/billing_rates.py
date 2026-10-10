"""Runtime billing rate overrides (admin-editable). Falls back to env Settings.

USD is the source of truth for everything a customer is quoted and charged. The
INR leg is derived from it at the *configured* rate, never from the live market
rate — a customer's price must not move between quote and invoice.

`live_fx()` exposes the market rate for display in the admin panel only. It is
deliberately not used for charging.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from server.config.env import get_settings

_LOCK = threading.Lock()
_PATH = Path(__file__).resolve().parents[3] / "data" / "billing_rates.json"
_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _cache
    with _LOCK:
        if _cache is not None:
            return _cache
        if _PATH.is_file():
            try:
                _cache = json.loads(_PATH.read_text(encoding="utf-8"))
            except Exception:
                _cache = {}
        else:
            _cache = {}
        return _cache


def _save(data: dict[str, Any]) -> None:
    global _cache
    with _LOCK:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        _cache = dict(data)


def usd_to_inr_cents(usd_cents: int, *, fx: float | None = None) -> int:
    """INR paise for a USD price, at the configured (chargeable) rate."""
    rate = float(fx if fx is not None else effective_rates()["fx_rate_inr"])
    return int(round(usd_cents * rate))


def effective_rates() -> dict[str, int | float]:
    settings = get_settings()
    ov = _load()
    return {
        "pstn_rate_usd_cents_per_min": int(ov.get("pstn_rate_usd_cents_per_min") or settings.pstn_rate_usd_cents_per_min),
        "web_agent_rate_usd_cents_per_min": int(
            ov.get("web_agent_rate_usd_cents_per_min") or settings.web_agent_rate_usd_cents_per_min
        ),
        # Number rental. USD is authoritative; the INR mirror is derived so an
        # admin who has only ever touched the INR field still gets a sane price.
        "did_monthly_usd_cents": int(ov.get("did_monthly_usd_cents") or settings.did_monthly_usd_cents),
        # fx_rate_inr is the rate money is actually converted at.
        "fx_rate_inr": float(ov.get("fx_rate_inr") or getattr(settings, "fx_rate_inr", 0) or 96.78),
    }


def rates_with_derived_inr() -> dict[str, int | float]:
    """`effective_rates` plus the INR mirror of every USD price.

    One place derives it, so the admin panel, the catalog and the wallet can
    never quote three different numbers for the same thing.
    """
    rates = dict(effective_rates())
    fx = float(rates["fx_rate_inr"])
    rates["pstn_rate_inr_paise_per_min"] = usd_to_inr_cents(
        int(rates["pstn_rate_usd_cents_per_min"]), fx=fx
    )
    rates["web_agent_rate_inr_paise_per_min"] = usd_to_inr_cents(
        int(rates["web_agent_rate_usd_cents_per_min"]), fx=fx
    )
    rates["did_monthly_inr_paise"] = usd_to_inr_cents(int(rates["did_monthly_usd_cents"]), fx=fx)
    return rates


def live_fx() -> dict[str, Any]:
    """Market USD→INR for display only. Never used to compute a charge."""
    from server.services.usage_pricing import resolve_fx_rate_inr

    resolved = resolve_fx_rate_inr(preferred=float(effective_rates()["fx_rate_inr"]))
    rate = resolved.get("rate")
    return {
        "liveRateInr": float(rate) if rate else None,
        "source": resolved.get("source"),
        "asOf": resolved.get("as_of"),
        "chargeRateInr": float(effective_rates()["fx_rate_inr"]),
    }


def update_rates(
    *,
    pstn_usd_per_min: float | None = None,
    web_usd_per_min: float | None = None,
    did_monthly_usd: float | None = None,
    fx_rate_inr: float | None = None,
) -> dict[str, int | float]:
    """Persist USD prices and the chargeable FX rate. INR is derived, not stored."""
    data = dict(_load())
    if pstn_usd_per_min is not None:
        data["pstn_rate_usd_cents_per_min"] = max(1, int(round(float(pstn_usd_per_min) * 100)))
    if web_usd_per_min is not None:
        data["web_agent_rate_usd_cents_per_min"] = max(1, int(round(float(web_usd_per_min) * 100)))
    if did_monthly_usd is not None:
        data["did_monthly_usd_cents"] = max(0, int(round(float(did_monthly_usd) * 100)))
    if fx_rate_inr is not None:
        data["fx_rate_inr"] = max(0.01, float(fx_rate_inr))
    # Drop the derived INR keys so a stale stored value can never be read back.
    for derived in (
        "pstn_rate_inr_paise_per_min",
        "web_agent_rate_inr_paise_per_min",
        "did_monthly_inr_paise",
    ):
        data.pop(derived, None)
    _save(data)
    return rates_with_derived_inr()