"""Razorpay payment settings the admin owns.

International Payments is enabled in the Razorpay dashboard, not by an API call,
so this module records the operator's choice and the currency to charge in, and
the admin panel reads it back. Without the flag the server deliberately charges
INR, because an unapproved account would decline the foreign card after the
customer had already entered their details.

Storage: the shared `config_versions` table (resource `payment_settings` /
`platform`), one row per change so the history is auditable, and every
instance reads the same value. A short in-process cache keeps the sync
getters cheap; `refresh()` (awaited on the checkout and admin paths) bounds
staleness. The old per-instance `payment_settings.json` is imported once when
the table has no row, and stays the store only when no database is configured.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from server.config.env import get_settings
from server.services.saas.razorpay_service import (
    MIN_CHARGE,
    SUPPORTED_CURRENCIES,
    normalize_currency,
)

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_mtime: float = 0.0

#: Database-backed value and when it was read (monotonic seconds).
_db_cache: dict[str, Any] | None = None
_db_loaded_at: float = 0.0
#: How long one instance may serve a value another instance has changed.
DB_CACHE_TTL_SECONDS = 15.0

_RESOURCE_TYPE = "payment_settings"
_RESOURCE_ID = "platform"


def _path() -> Path:
    return get_settings().data_path / "payment_settings.json"


def _load_file() -> dict[str, Any]:
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


def _load() -> dict[str, Any]:
    """The current settings: the database value once loaded, else the file."""
    if _db_cache is not None:
        return _db_cache
    return _load_file()


def _save(data: dict[str, Any]) -> None:
    """File store, used only when there is no database."""
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


def _clean(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    out: dict[str, Any] = {}
    if isinstance(data.get("internationalEnabled"), bool):
        out["internationalEnabled"] = data["internationalEnabled"]
    code = str(data.get("currency") or "").strip().upper()
    if code in SUPPORTED_CURRENCIES:
        out["currency"] = code
    return out


async def _latest_row(session):
    from sqlalchemy import select

    from server.db.models.entities import ConfigVersion

    return (
        await session.execute(
            select(ConfigVersion)
            .where(
                ConfigVersion.resource_type == _RESOURCE_TYPE,
                ConfigVersion.resource_id == _RESOURCE_ID,
            )
            .order_by(ConfigVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def refresh(*, force: bool = False) -> dict[str, Any]:
    """Load the shared settings from the database (cached for a few seconds).

    On first use with an empty table, the legacy JSON file is imported as
    version 1 so an upgrade keeps the operator's existing choice. A database
    error keeps the last known value rather than flipping the charge currency.
    """
    global _db_cache, _db_loaded_at
    from server.db.connection import get_session_factory

    factory = get_session_factory()
    if factory is None:
        return _load()
    if (
        not force
        and _db_cache is not None
        and time.monotonic() - _db_loaded_at < DB_CACHE_TTL_SECONDS
    ):
        return _db_cache
    try:
        from server.db.models.entities import ConfigVersion

        async with factory() as session:
            row = await _latest_row(session)
            if row is None:
                data = _clean(_load_file())
                if data:
                    session.add(
                        ConfigVersion(
                            resource_type=_RESOURCE_TYPE,
                            resource_id=_RESOURCE_ID,
                            version=1,
                            payload={**data, "importedFrom": "payment_settings.json"},
                        )
                    )
                    await session.commit()
                    logger.info("payment settings imported from the legacy JSON file")
            else:
                data = _clean(row.payload)
    except Exception as exc:
        logger.warning("payment settings load failed error_type=%s", type(exc).__name__)
        return _load()
    _db_cache = data
    _db_loaded_at = time.monotonic()
    return data


def reset_cache_for_tests() -> None:
    global _cache, _cache_mtime, _db_cache, _db_loaded_at
    with _LOCK:
        _cache = None
        _cache_mtime = 0.0
    _db_cache = None
    _db_loaded_at = 0.0


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
    from server.config.env import razorpay_config_issues

    return {
        "configured": bool(key and secret),
        # Masked: the full key never leaves the server.
        "keyId": _mask(key),
        # Without the endpoint secret the webhook route refuses every delivery,
        # so the panel must be able to say payments are only confirmed by the
        # browser callback.
        "webhookConfigured": bool((settings.razorpay_webhook_secret or "").strip()),
        # Codes only (never values): reused webhook secret, test key in prod.
        "configIssues": razorpay_config_issues(settings),
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


async def update_settings(
    *,
    international_enabled: bool | None = None,
    currency: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Save the operator's choice for every instance, as a new version row."""
    global _db_cache, _db_loaded_at
    if currency is not None:
        code = str(currency).strip().upper()
        if code not in SUPPORTED_CURRENCIES:
            raise ValueError("unsupported_currency")
        currency = code

    from server.db.connection import get_session_factory

    factory = get_session_factory()
    if factory is None:
        data = dict(_load_file())
        if currency is not None:
            data["currency"] = currency
        if international_enabled is not None:
            data["internationalEnabled"] = bool(international_enabled)
        _save(data)
        return settings_state()

    from server.db.models.entities import ConfigVersion

    async with factory() as session:
        row = await _latest_row(session)
        data = _clean(row.payload) if row is not None else _clean(_load_file())
        if currency is not None:
            data["currency"] = currency
        if international_enabled is not None:
            data["internationalEnabled"] = bool(international_enabled)
        session.add(
            ConfigVersion(
                resource_type=_RESOURCE_TYPE,
                resource_id=_RESOURCE_ID,
                version=(int(row.version) + 1) if row is not None else 1,
                payload={**data, "updatedBy": actor} if actor else dict(data),
            )
        )
        await session.commit()
    _db_cache = _clean(data)
    _db_loaded_at = time.monotonic()
    return settings_state()


__all__ = [
    "charge_currency",
    "is_international_enabled",
    "normalize_currency",
    "refresh",
    "settings_state",
    "update_settings",
]
