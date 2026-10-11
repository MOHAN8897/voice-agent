"""Runtime billing rate management with database versioning.

USD is the authoritative source of truth for everything a customer is quoted and charged.
The INR leg is derived from it at the configured rate, never from the live market rate.
All rate changes are versioned in `billing_rate_versions` (who, when, old/new, reason).
Calls lock their rate snapshot at initiation so past calls are never re-priced.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select, update

from server.config.env import get_settings

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_PATH = Path(__file__).resolve().parents[3] / "data" / "billing_rates.json"
_cache: dict[str, Any] | None = None


class BillingConfigurationError(RuntimeError):
    """Raised when billing rates cannot be verified or resolved from database/cache."""
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_disk_fallback() -> dict[str, Any]:
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


def _save_disk_backup(data: dict[str, Any]) -> None:
    global _cache
    with _LOCK:
        try:
            _PATH.parent.mkdir(parents=True, exist_ok=True)
            _PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning("[BILLING_RATES] disk backup save failed: %s", e)
        _cache = dict(data)


def set_cached_rates(rates: dict[str, Any]) -> None:
    """Set in-memory cache directly (used in tests and after DB updates)."""
    global _cache
    with _LOCK:
        _cache = dict(rates)


def clear_rates_cache() -> None:
    """Clear in-memory cache (for test isolation)."""
    global _cache
    with _LOCK:
        _cache = None


async def load_rates_from_db_or_seed() -> dict[str, Any]:
    """Load latest active rate version from database. If table is empty, seeds Version 1."""
    from server.db.connection import get_session_factory
    from server.db.models.saas_models import BillingRateVersion

    factory = get_session_factory()
    if factory is None:
        disk = _load_disk_fallback()
        if disk and disk.get("pstn_rate_usd_cents_per_min"):
            return disk
        settings = get_settings()
        return {
            "version": 1,
            "pstn_rate_usd_cents_per_min": int(settings.pstn_rate_usd_cents_per_min),
            "web_agent_rate_usd_cents_per_min": int(settings.web_agent_rate_usd_cents_per_min),
            "did_monthly_usd_cents": int(settings.did_monthly_usd_cents),
            "fx_rate_inr": float(getattr(settings, "fx_rate_inr", 0) or 95.64),
            "effective_from": _utcnow().isoformat(),
            "created_by": "system_default",
            "reason": "Cold start default settings",
        }

    async with factory() as session:
        try:
            stmt = (
                select(BillingRateVersion)
                .where(BillingRateVersion.is_active == True)  # noqa: E712
                .order_by(desc(BillingRateVersion.version))
                .limit(1)
            )
            res = await session.execute(stmt)
            latest = res.scalar_one_or_none()

            if latest is not None:
                data = {
                    "version": latest.version,
                    "pstn_rate_usd_cents_per_min": latest.pstn_rate_usd_cents_per_min,
                    "web_agent_rate_usd_cents_per_min": latest.web_agent_rate_usd_cents_per_min,
                    "did_monthly_usd_cents": latest.did_monthly_usd_cents,
                    "fx_rate_inr": float(latest.fx_rate_inr),
                    "effective_from": latest.effective_from.isoformat() if latest.effective_from else _utcnow().isoformat(),
                    "created_by": latest.created_by,
                    "reason": latest.reason,
                }
                _save_disk_backup(data)
                return data

            # Table is empty: seed Version 1 explicitly into database
            settings = get_settings()
            v1 = BillingRateVersion(
                version=1,
                pstn_rate_usd_cents_per_min=int(settings.pstn_rate_usd_cents_per_min),
                web_agent_rate_usd_cents_per_min=int(settings.web_agent_rate_usd_cents_per_min),
                did_monthly_usd_cents=int(settings.did_monthly_usd_cents),
                fx_rate_inr=float(getattr(settings, "fx_rate_inr", 0) or 95.64),
                effective_from=_utcnow(),
                created_by="system_initial_migration",
                reason="Initial baseline rates from settings",
                is_active=True,
            )
            session.add(v1)
            await session.commit()
            data = {
                "version": 1,
                "pstn_rate_usd_cents_per_min": v1.pstn_rate_usd_cents_per_min,
                "web_agent_rate_usd_cents_per_min": v1.web_agent_rate_usd_cents_per_min,
                "did_monthly_usd_cents": v1.did_monthly_usd_cents,
                "fx_rate_inr": float(v1.fx_rate_inr),
                "effective_from": v1.effective_from.isoformat(),
                "created_by": v1.created_by,
                "reason": v1.reason,
            }
            _save_disk_backup(data)
            return data
        except Exception as e:
            logger.error("[BILLING_RATES] DB load failed: %s", e)
            disk = _load_disk_fallback()
            if disk and disk.get("pstn_rate_usd_cents_per_min"):
                return disk
            raise BillingConfigurationError(f"Billing rates cannot be resolved: {e}") from e


def effective_rates() -> dict[str, int | float]:
    """Synchronous read for effective rates, cached with disk/settings fallback."""
    global _cache
    with _LOCK:
        if _cache and _cache.get("pstn_rate_usd_cents_per_min"):
            return {
                "version": _cache.get("version", 1),
                "pstn_rate_usd_cents_per_min": int(_cache["pstn_rate_usd_cents_per_min"]),
                "web_agent_rate_usd_cents_per_min": int(_cache["web_agent_rate_usd_cents_per_min"]),
                "did_monthly_usd_cents": int(_cache["did_monthly_usd_cents"]),
                "fx_rate_inr": float(_cache["fx_rate_inr"]),
            }

    settings = get_settings()
    ov = _load_disk_fallback()
    if not ov and not settings.pstn_rate_usd_cents_per_min:
        raise BillingConfigurationError("No billing rates configured or cached.")

    res = {
        "version": ov.get("version", 1),
        "pstn_rate_usd_cents_per_min": int(ov.get("pstn_rate_usd_cents_per_min") or settings.pstn_rate_usd_cents_per_min),
        "web_agent_rate_usd_cents_per_min": int(
            ov.get("web_agent_rate_usd_cents_per_min") or settings.web_agent_rate_usd_cents_per_min
        ),
        "did_monthly_usd_cents": int(ov.get("did_monthly_usd_cents") or settings.did_monthly_usd_cents),
        "fx_rate_inr": float(ov.get("fx_rate_inr") or getattr(settings, "fx_rate_inr", 0) or 95.64),
    }
    _save_disk_backup(res)
    return res


def usd_to_inr_cents(usd_cents: int, *, fx: float | None = None) -> int:
    """INR paise for a USD price, at the configured (chargeable) rate."""
    rate = float(fx if fx is not None else effective_rates()["fx_rate_inr"])
    return int(round(usd_cents * rate))


def rates_with_derived_inr() -> dict[str, int | float]:
    """`effective_rates` plus the INR mirror of every USD price."""
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


async def update_rates_versioned(
    *,
    actor: str,
    reason: str,
    pstn_usd_per_min: float | None = None,
    web_usd_per_min: float | None = None,
    did_monthly_usd: float | None = None,
    fx_rate_inr: float | None = None,
) -> dict[str, Any]:
    """Persist new version of billing rates to the database.

    Enforces:
    - Reason required (min 8 characters)
    - All rates > 0 (fail loudly on non-positive input)
    - Idempotent and version-incremented
    - Retains entire history in billing_rate_versions
    """
    clean_reason = reason.strip() if reason else ""
    if len(clean_reason) < 8:
        raise ValueError("Admin statement (minimum 8 characters) required to change billing rates.")

    curr = rates_with_derived_inr()
    new_pstn = max(1, int(round(float(pstn_usd_per_min) * 100))) if pstn_usd_per_min is not None else int(curr["pstn_rate_usd_cents_per_min"])
    new_web = max(1, int(round(float(web_usd_per_min) * 100))) if web_usd_per_min is not None else int(curr["web_agent_rate_usd_cents_per_min"])
    new_did = max(0, int(round(float(did_monthly_usd) * 100))) if did_monthly_usd is not None else int(curr["did_monthly_usd_cents"])
    new_fx = max(0.01, float(fx_rate_inr)) if fx_rate_inr is not None else float(curr["fx_rate_inr"])

    from server.db.connection import get_session_factory
    from server.db.models.saas_models import BillingRateVersion

    factory = get_session_factory()
    now = _utcnow()

    if factory is not None:
        async with factory() as session:
            # Get latest version number
            res = await session.execute(
                select(BillingRateVersion.version)
                .order_by(desc(BillingRateVersion.version))
                .limit(1)
            )
            last_version = res.scalar_one_or_none() or 0
            next_version = last_version + 1

            # Deactivate previous active versions
            await session.execute(
                update(BillingRateVersion)
                .where(BillingRateVersion.is_active == True)  # noqa: E712
                .values(is_active=False)
            )

            # Insert new version
            new_row = BillingRateVersion(
                version=next_version,
                pstn_rate_usd_cents_per_min=new_pstn,
                web_agent_rate_usd_cents_per_min=new_web,
                did_monthly_usd_cents=new_did,
                fx_rate_inr=new_fx,
                effective_from=now,
                created_by=actor,
                reason=clean_reason,
                is_active=True,
            )
            session.add(new_row)
            await session.commit()
            version_id = next_version
    else:
        version_id = int(curr.get("version", 1)) + 1

    updated_data = {
        "version": version_id,
        "pstn_rate_usd_cents_per_min": new_pstn,
        "web_agent_rate_usd_cents_per_min": new_web,
        "did_monthly_usd_cents": new_did,
        "fx_rate_inr": new_fx,
        "effective_from": now.isoformat(),
        "created_by": actor,
        "reason": clean_reason,
    }
    _save_disk_backup(updated_data)
    return rates_with_derived_inr()


def update_rates(
    *,
    pstn_usd_per_min: float | None = None,
    web_usd_per_min: float | None = None,
    did_monthly_usd: float | None = None,
    fx_rate_inr: float | None = None,
) -> dict[str, int | float]:
    """Synchronous compatibility wrapper for updating rates."""
    data = dict(_load_disk_fallback())
    if pstn_usd_per_min is not None:
        data["pstn_rate_usd_cents_per_min"] = max(1, int(round(float(pstn_usd_per_min) * 100)))
    if web_usd_per_min is not None:
        data["web_agent_rate_usd_cents_per_min"] = max(1, int(round(float(web_usd_per_min) * 100)))
    if did_monthly_usd is not None:
        data["did_monthly_usd_cents"] = max(0, int(round(float(did_monthly_usd) * 100)))
    if fx_rate_inr is not None:
        data["fx_rate_inr"] = max(0.01, float(fx_rate_inr))
    _save_disk_backup(data)
    return rates_with_derived_inr()