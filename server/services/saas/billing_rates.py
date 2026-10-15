"""Runtime billing rate management with database versioning.

USD and INR rates are retained at their native billing precision (microdollars and
paise). The other currency is derived at the configured FX rate, never the live
market rate. Rates are versioned, and calls snapshot both legs at initiation so
past calls are never re-priced.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select, update

from server.config.env import get_settings

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_PATH = Path(__file__).resolve().parents[3] / "data" / "billing_rates.json"
_cache: dict[str, Any] | None = None
_USD_MICRODOLLARS_PER_DOLLAR = 1_000_000
_USD_MICRODOLLARS_PER_CENT = 10_000


class BillingConfigurationError(RuntimeError):
    """Raised when billing rates cannot be verified or resolved from database/cache."""
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Billing rates must be valid decimal values.") from exc
    if not result.is_finite():
        raise ValueError("Billing rates must be finite decimal values.")
    return result


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _to_scaled_int(value: Any, scale: int, *, label: str) -> int:
    amount = _decimal(value)
    scaled = amount * scale
    if scaled != scaled.to_integral_value():
        decimals = 2 if scale == 100 else 6
        raise ValueError(f"{label} supports at most {decimals} decimal places.")
    return int(scaled)


def _expand_rate_data(data: dict[str, Any]) -> dict[str, int | float]:
    """Add exact/minor-unit rate fields while preserving legacy rate rows."""
    fx = _decimal(data.get("fx_rate_inr") or 95.64)
    expanded: dict[str, int | float] = {
        "version": int(data.get("version") or 1),
        "fx_rate_inr": float(fx),
    }
    fields = (
        ("pstn_rate_usd_cents_per_min", "pstn_rate_usd_micros_per_min", "pstn_rate_inr_paise_per_min"),
        ("web_agent_rate_usd_cents_per_min", "web_agent_rate_usd_micros_per_min", "web_agent_rate_inr_paise_per_min"),
        ("did_monthly_usd_cents", "did_monthly_usd_micros", "did_monthly_inr_paise"),
    )
    for cents_key, micros_key, paise_key in fields:
        cents = int(data.get(cents_key) or 0)
        micros_value = data.get(micros_key)
        paise_value = data.get(paise_key)
        expanded[cents_key] = cents
        expanded[micros_key] = (
            int(micros_value)
            if micros_value is not None
            else cents * _USD_MICRODOLLARS_PER_CENT
        )
        expanded[paise_key] = (
            int(paise_value)
            if paise_value is not None
            else _round_half_up(Decimal(cents) * fx)
        )
    return expanded


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
    """Load latest active rate version from database. If table is empty, seeds Version 1.

    Raises BillingConfigurationError if rates cannot be resolved — never silently
    falls back to hardcoded env defaults so a misconfigured deployment is caught
    immediately rather than charging the wrong rate.
    """
    from server.db.connection import get_session_factory
    from server.db.models.saas_models import BillingRateVersion

    factory = get_session_factory()
    if factory is None:
        # No DB available — use disk cache if it was written by a previous run.
        disk = _load_disk_fallback()
        if disk and disk.get("pstn_rate_usd_cents_per_min"):
            logger.warning(
                "[BILLING_RATES] DB unavailable — using disk-cached rates (version %s). "
                "Resolve the DB connection before rates next change.",
                disk.get("version", "?"),
            )
            return disk
        # No disk cache either: fail loudly. Using hardcoded env values here would
        # mean calls are billed at whatever the env says, not at the admin-set rate.
        raise BillingConfigurationError(
            "[BILLING_RATES] DB session factory is None and no disk cache exists. "
            "Cannot resolve billing rates — check DATABASE_URL and restart."
        )

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
                    "pstn_rate_usd_micros_per_min": latest.pstn_rate_usd_micros_per_min,
                    "web_agent_rate_usd_micros_per_min": latest.web_agent_rate_usd_micros_per_min,
                    "did_monthly_usd_micros": latest.did_monthly_usd_micros,
                    "pstn_rate_inr_paise_per_min": latest.pstn_rate_inr_paise_per_min,
                    "web_agent_rate_inr_paise_per_min": latest.web_agent_rate_inr_paise_per_min,
                    "did_monthly_inr_paise": latest.did_monthly_inr_paise,
                    "fx_rate_inr": float(latest.fx_rate_inr),
                    "effective_from": latest.effective_from.isoformat() if latest.effective_from else _utcnow().isoformat(),
                    "created_by": latest.created_by,
                    "reason": latest.reason,
                }
                # Old versions legitimately have NULL in the native-rate
                # columns. Normalize those from the original cents and FX,
                # while preserving any values entered directly in INR.
                normalized = {**data, **_expand_rate_data(data)}
                set_cached_rates(normalized)
                return normalized

            # Table is empty: seed Version 1 explicitly into database
            settings = get_settings()
            fx = _decimal(getattr(settings, "fx_rate_inr", 0) or 95.64)
            pstn_cents = int(settings.pstn_rate_usd_cents_per_min)
            web_cents = int(settings.web_agent_rate_usd_cents_per_min)
            did_cents = int(settings.did_monthly_usd_cents)
            v1 = BillingRateVersion(
                version=1,
                pstn_rate_usd_cents_per_min=pstn_cents,
                web_agent_rate_usd_cents_per_min=web_cents,
                did_monthly_usd_cents=did_cents,
                pstn_rate_usd_micros_per_min=pstn_cents * _USD_MICRODOLLARS_PER_CENT,
                web_agent_rate_usd_micros_per_min=web_cents * _USD_MICRODOLLARS_PER_CENT,
                did_monthly_usd_micros=did_cents * _USD_MICRODOLLARS_PER_CENT,
                pstn_rate_inr_paise_per_min=_round_half_up(Decimal(pstn_cents) * fx),
                web_agent_rate_inr_paise_per_min=_round_half_up(Decimal(web_cents) * fx),
                did_monthly_inr_paise=_round_half_up(Decimal(did_cents) * fx),
                fx_rate_inr=float(fx),
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
                "pstn_rate_usd_micros_per_min": v1.pstn_rate_usd_micros_per_min,
                "web_agent_rate_usd_micros_per_min": v1.web_agent_rate_usd_micros_per_min,
                "did_monthly_usd_micros": v1.did_monthly_usd_micros,
                "pstn_rate_inr_paise_per_min": v1.pstn_rate_inr_paise_per_min,
                "web_agent_rate_inr_paise_per_min": v1.web_agent_rate_inr_paise_per_min,
                "did_monthly_inr_paise": v1.did_monthly_inr_paise,
                "fx_rate_inr": float(v1.fx_rate_inr),
                "effective_from": v1.effective_from.isoformat(),
                "created_by": v1.created_by,
                "reason": v1.reason,
            }
            _save_disk_backup(data)
            return data
        except Exception as e:
            logger.error("[BILLING_RATES] DB load failed: %s", e)
            # A stale disk copy can silently re-price calls after another
            # worker has saved a new version. When the database is configured,
            # a failed read must not masquerade as the current rate version.
            raise BillingConfigurationError(f"Billing rates cannot be resolved: {e}") from e


def effective_rates() -> dict[str, int | float]:
    """Synchronous read for effective rates, cached with disk/settings fallback."""
    global _cache
    with _LOCK:
        if _cache and _cache.get("pstn_rate_usd_cents_per_min"):
            return _expand_rate_data(_cache)

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
    for key in (
        "pstn_rate_usd_micros_per_min",
        "web_agent_rate_usd_micros_per_min",
        "did_monthly_usd_micros",
        "pstn_rate_inr_paise_per_min",
        "web_agent_rate_inr_paise_per_min",
        "did_monthly_inr_paise",
    ):
        if ov.get(key) is not None:
            res[key] = int(ov[key])
    expanded = _expand_rate_data(res)
    _save_disk_backup(expanded)
    return expanded


def usd_to_inr_cents(usd_cents: int, *, fx: float | None = None) -> int:
    """INR paise for a USD price, at the configured (chargeable) rate."""
    rate = float(fx if fx is not None else effective_rates()["fx_rate_inr"])
    return int(round(usd_cents * rate))


def rates_with_derived_inr() -> dict[str, int | float]:
    """Return configured INR rates and legacy-derived fallbacks."""
    return effective_rates()


async def load_current_rates() -> dict[str, int | float]:
    """Read current rates from the database, retaining local-only dev fallback."""
    from server.db.connection import get_session_factory

    if get_session_factory() is None:
        return _expand_rate_data(rates_with_derived_inr())
    return await load_rates_from_db_or_seed()


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
    rate_currency: str = "USD",
    pstn_usd_per_min: Decimal | float | str | None = None,
    web_usd_per_min: Decimal | float | str | None = None,
    did_monthly_usd: Decimal | float | str | None = None,
    pstn_inr_per_min: Decimal | float | str | None = None,
    web_inr_per_min: Decimal | float | str | None = None,
    did_monthly_inr: Decimal | float | str | None = None,
    fx_rate_inr: Decimal | float | str | None = None,
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

    currency = str(rate_currency or "USD").upper()
    if currency not in {"USD", "INR"}:
        raise ValueError("Rate currency must be USD or INR.")

    # Never build a new version from this worker's possibly stale process cache.
    curr = await load_current_rates()
    new_fx_decimal = (
        max(Decimal("0.01"), _decimal(fx_rate_inr))
        if fx_rate_inr is not None
        else _decimal(curr["fx_rate_inr"])
    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    new_fx = float(new_fx_decimal)

    def resolve_rate(
        *,
        usd_value: Decimal | float | str | None,
        inr_value: Decimal | float | str | None,
        current_cents: int,
        current_micros: int,
        current_paise: int,
        allow_zero: bool,
        label: str,
    ) -> tuple[int, int, int]:
        value = inr_value if currency == "INR" else usd_value
        if value is None:
            return current_cents, current_micros, current_paise

        amount = _decimal(value)
        if amount < 0 or (amount == 0 and not allow_zero):
            raise ValueError(f"{label} must be {'non-negative' if allow_zero else 'positive'}.")

        if currency == "INR":
            paise = _to_scaled_int(amount, 100, label=label)
            micros = _round_half_up(
                (Decimal(paise) / Decimal(100) / new_fx_decimal)
                * _USD_MICRODOLLARS_PER_DOLLAR
            )
        else:
            micros = _to_scaled_int(amount, _USD_MICRODOLLARS_PER_DOLLAR, label=label)
            paise = _round_half_up(
                (Decimal(micros) / _USD_MICRODOLLARS_PER_DOLLAR)
                * new_fx_decimal
                * 100
            )

        if amount == 0:
            cents = 0
            micros = 0
            paise = 0
        else:
            cents = max(1, _round_half_up(Decimal(micros) / _USD_MICRODOLLARS_PER_CENT))
            if micros <= 0 or paise <= 0:
                raise ValueError(f"{label} is too small to represent at the configured precision.")
        return cents, micros, paise

    new_pstn, pstn_micros, pstn_paise = resolve_rate(
        usd_value=pstn_usd_per_min,
        inr_value=pstn_inr_per_min,
        current_cents=int(curr["pstn_rate_usd_cents_per_min"]),
        current_micros=int(curr["pstn_rate_usd_micros_per_min"]),
        current_paise=int(curr["pstn_rate_inr_paise_per_min"]),
        allow_zero=False,
        label="PSTN rate",
    )
    new_web, web_micros, web_paise = resolve_rate(
        usd_value=web_usd_per_min,
        inr_value=web_inr_per_min,
        current_cents=int(curr["web_agent_rate_usd_cents_per_min"]),
        current_micros=int(curr["web_agent_rate_usd_micros_per_min"]),
        current_paise=int(curr["web_agent_rate_inr_paise_per_min"]),
        allow_zero=False,
        label="Browser agent rate",
    )
    new_did, did_micros, did_paise = resolve_rate(
        usd_value=did_monthly_usd,
        inr_value=did_monthly_inr,
        current_cents=int(curr["did_monthly_usd_cents"]),
        current_micros=int(curr["did_monthly_usd_micros"]),
        current_paise=int(curr["did_monthly_inr_paise"]),
        allow_zero=True,
        label="Phone number rental rate",
    )

    from server.db.connection import get_session_factory
    from server.db.models.saas_models import BillingRateVersion

    factory = get_session_factory()
    now = _utcnow()

    if factory is not None:
        async with factory() as session:
            # Lock the latest version so concurrent admin saves serialize.
            res = await session.execute(
                select(BillingRateVersion.id)
                .order_by(desc(BillingRateVersion.version))
                .limit(1)
                .with_for_update()
            )
            res.scalar_one_or_none()
            # Read the version in a fresh statement after any lock wait.
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
                pstn_rate_usd_micros_per_min=pstn_micros,
                web_agent_rate_usd_micros_per_min=web_micros,
                did_monthly_usd_micros=did_micros,
                pstn_rate_inr_paise_per_min=pstn_paise,
                web_agent_rate_inr_paise_per_min=web_paise,
                did_monthly_inr_paise=did_paise,
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
        "pstn_rate_usd_micros_per_min": pstn_micros,
        "web_agent_rate_usd_micros_per_min": web_micros,
        "did_monthly_usd_micros": did_micros,
        "pstn_rate_inr_paise_per_min": pstn_paise,
        "web_agent_rate_inr_paise_per_min": web_paise,
        "did_monthly_inr_paise": did_paise,
        "fx_rate_inr": new_fx,
        "effective_from": now.isoformat(),
        "created_by": actor,
        "reason": clean_reason,
    }
    _save_disk_backup(updated_data)
    return _expand_rate_data(updated_data)


def update_rates(
    *,
    pstn_usd_per_min: float | None = None,
    web_usd_per_min: float | None = None,
    did_monthly_usd: float | None = None,
    fx_rate_inr: float | None = None,
) -> dict[str, int | float]:
    """Synchronous compatibility wrapper — DEPRECATED.

    This writes only to the disk cache and bypasses the versioned DB table,
    meaning a restart will lose any change made here and the audit log will have
    no record of it.  Use ``update_rates_versioned`` (async) instead.

    This function now raises RuntimeError in every context except unit tests
    (detected by the absence of a live session factory) so callers are forced to
    migrate.  Tests that need a synchronous shortcut should call
    ``set_cached_rates`` directly.
    """
    from server.db.connection import get_session_factory

    if get_session_factory() is not None:
        raise RuntimeError(
            "update_rates() is deprecated and must not be called when a DB is "
            "configured — use await update_rates_versioned() instead. "
            "This call would have written only to the disk cache, bypassing "
            "the billing_rate_versions audit table."
        )
    # Allowed path: tests that run without a DB and need a synchronous stub.
    data = dict(_load_disk_fallback())
    if fx_rate_inr is not None:
        data["fx_rate_inr"] = max(0.01, float(fx_rate_inr))
    fx = _decimal(data.get("fx_rate_inr") or 95.64)
    for usd_value, cents_key, micros_key, paise_key in (
        (
            pstn_usd_per_min,
            "pstn_rate_usd_cents_per_min",
            "pstn_rate_usd_micros_per_min",
            "pstn_rate_inr_paise_per_min",
        ),
        (
            web_usd_per_min,
            "web_agent_rate_usd_cents_per_min",
            "web_agent_rate_usd_micros_per_min",
            "web_agent_rate_inr_paise_per_min",
        ),
        (
            did_monthly_usd,
            "did_monthly_usd_cents",
            "did_monthly_usd_micros",
            "did_monthly_inr_paise",
        ),
    ):
        micros = (
            _to_scaled_int(usd_value, _USD_MICRODOLLARS_PER_DOLLAR, label="USD rate")
            if usd_value is not None
            else int(data.get(micros_key) or int(data.get(cents_key) or 0) * _USD_MICRODOLLARS_PER_CENT)
        )
        data[micros_key] = micros
        data[cents_key] = (
            max(1, _round_half_up(Decimal(micros) / _USD_MICRODOLLARS_PER_CENT))
            if micros > 0
            else 0
        )
        data[paise_key] = _round_half_up(
            (Decimal(micros) / _USD_MICRODOLLARS_PER_DOLLAR) * fx * 100
        )
    _save_disk_backup(data)
    return rates_with_derived_inr()
