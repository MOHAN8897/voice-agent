"""Razorpay payment settings the admin owns.

International Payments is enabled in the Razorpay dashboard, not by an API call,
so this module records the operator's choice and the currency to charge in, and
the admin panel reads it back. Without the flag the server deliberately charges
INR, because an unapproved account would decline the foreign card after the
customer had already entered their details.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from server.config.env import get_settings
from server.services.saas.razorpay_service import (
    MIN_CHARGE,
    SUPPORTED_CURRENCIES,
    normalize_currency,
)

_LOCK = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_mtime: float = 0.0


def _path() -> Path:
    return get_settings().data_path / "payment_settings.json"


def _load() -> dict[str, Any]:
    global _cache, _cache_mtime
    with _LOCK:
        path = _path()
        mtime = 0.0
        if path.is_file():
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
        if _cache is not None and mtime == _cache_mtime:
            return _cache
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                _cache = raw if isinstance(raw, dict) else {}
            except Exception:
                _cache = {}
        else:
            _cache = {}
        _cache_mtime = mtime
        return _cache


def _save(data: dict[str, Any]) -> None:
    global _cache, _cache_mtime
    with _LOCK:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        _cache = dict(data)
        try:
            _cache_mtime = path.stat().st_mtime
        except OSError:
            _cache_mtime = 0.0


def is_international_enabled() -> bool:
    """Env acts as the default; the panel's saved choice overrides it."""
    override = _load().get("internationalEnabled")
    if isinstance(override, bool):
        return override
    return bool(get_settings().razorpay_international_enabled)


def charge_currency() -> str:
    """The currency orders are created in, after aliasing and the toggle."""
    if not is_international_enabled():
        return "INR"
    saved = _load().get("currency")
    code = str(saved or get_settings().razorpay_currency or "INR").strip().upper()
    return code if code in SUPPORTED_CURRENCIES else "INR"


def settings_state() -> dict[str, Any]:
    """Everything the admin panel needs to render the payments tab."""
    settings = get_settings()
    key = (settings.razorpay_api_key or "").strip()
    secret = (settings.razorpay_api_secret or "").strip()
    international = is_international_enabled()
    currency = charge_currency()
    return {
        "configured": bool(key and secret),
        # Masked: the full key never leaves the server.
        "keyId": _mask(key),
        "testMode": key.startswith("rzp_test"),
        "internationalEnabled": international,
        # Razorpay exposes NO endpoint reporting whether International Payments is
        # approved, and it must not be inferred from the API: a probe that creates
        # a foreign order returns Razorpay's rate-limit "Authentication failed"
        # as readily as a real refusal, so any such check reports whatever the
        # throttling state happened to be. This flag therefore records only what
        # the operator chose, and the panel says so rather than implying a check.
        "internationalVerified": None,
        "internationalNote": (
            "Confirm approval in Razorpay under Account & Settings → Payment methods "
            "→ International payments. There is no API to read this."
        ),
        "currency": currency,
        "availableCurrencies": list(SUPPORTED_CURRENCIES),
        "minCharge": MIN_CHARGE.get(currency, 1.0),
        "supportsUpi": currency == "INR",
        "settlesIn": "INR",
    }


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:6]}…{value[-4:]}"


def update_settings(
    *, international_enabled: bool | None = None, currency: str | None = None
) -> dict[str, Any]:
    if currency is not None:
        code = str(currency).strip().upper()
        if code not in SUPPORTED_CURRENCIES:
            raise ValueError("unsupported_currency")
        data = dict(_load())
        data["currency"] = code
        _save(data)
    if international_enabled is not None:
        data = dict(_load())
        data["internationalEnabled"] = bool(international_enabled)
        _save(data)
    return settings_state()