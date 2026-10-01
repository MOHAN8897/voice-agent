"""Runtime billing rate overrides (admin-editable). Falls back to env Settings."""
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


def effective_rates() -> dict[str, int | float]:
    settings = get_settings()
    ov = _load()
    return {
        "pstn_rate_usd_cents_per_min": int(ov.get("pstn_rate_usd_cents_per_min") or settings.pstn_rate_usd_cents_per_min),
        "pstn_rate_inr_paise_per_min": int(ov.get("pstn_rate_inr_paise_per_min") or settings.pstn_rate_inr_paise_per_min),
        "web_agent_rate_usd_cents_per_min": int(
            ov.get("web_agent_rate_usd_cents_per_min") or settings.web_agent_rate_usd_cents_per_min
        ),
        "web_agent_rate_inr_paise_per_min": int(
            ov.get("web_agent_rate_inr_paise_per_min") or settings.web_agent_rate_inr_paise_per_min
        ),
        "did_monthly_inr_paise": int(ov.get("did_monthly_inr_paise") or settings.did_monthly_inr_paise),
        "did_monthly_usd_cents": int(ov.get("did_monthly_usd_cents") or settings.did_monthly_usd_cents),
        "fx_rate_inr": float(ov.get("fx_rate_inr") or getattr(settings, "fx_rate_inr", 0) or 95.64),
    }


def update_rates(
    *,
    pstn_inr_per_min: float | None = None,
    web_inr_per_min: float | None = None,
    pstn_usd_per_min: float | None = None,
    web_usd_per_min: float | None = None,
    did_monthly_inr: float | None = None,
) -> dict[str, int | float]:
    data = dict(_load())
    if pstn_inr_per_min is not None:
        data["pstn_rate_inr_paise_per_min"] = max(1, int(round(float(pstn_inr_per_min) * 100)))
    if web_inr_per_min is not None:
        data["web_agent_rate_inr_paise_per_min"] = max(1, int(round(float(web_inr_per_min) * 100)))
    if pstn_usd_per_min is not None:
        data["pstn_rate_usd_cents_per_min"] = max(1, int(round(float(pstn_usd_per_min) * 100)))
    if web_usd_per_min is not None:
        data["web_agent_rate_usd_cents_per_min"] = max(1, int(round(float(web_usd_per_min) * 100)))
    if did_monthly_inr is not None:
        data["did_monthly_inr_paise"] = max(0, int(round(float(did_monthly_inr) * 100)))
    _save(data)
    return effective_rates()
