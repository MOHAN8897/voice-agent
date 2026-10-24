"""Compose per-call retail, pinned supplier spend and margin for platform admins.

Every number is read from the call's immutable snapshots or the admin rate
version. Missing measurements stay ``None``; this module never invents a tariff.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from server.services.saas.composed_costing import price_composed_usage

_STAGE_KEYS = ("stt", "llm", "tts")


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return float(number) if number.is_finite() else None


def _nonnegative(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _money(value: float | None, places: int) -> float | None:
    return round(value, places) if value is not None else None


def _fx_rate(meta: dict, current_rates: dict | None) -> float | None:
    snapshot = meta.get("rate_snapshot") if isinstance(meta.get("rate_snapshot"), dict) else {}
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    supplier = meta.get("provider_cost_snapshot") if isinstance(meta.get("provider_cost_snapshot"), dict) else {}
    for value in (
        snapshot.get("fxRateInr"),
        usage.get("fx_rate_inr"),
        supplier.get("fxRateInr"),
        (current_rates or {}).get("fx_rate_inr"),
    ):
        rate = _number(value)
        if rate is not None and rate > 0:
            return rate
    return None


def _retail(
    meta: dict,
    *,
    duration_sec: float,
    applied_inr_paise: Any,
    applied_usd_micros: Any,
    tier_rate: dict | None,
    fx: float | None,
) -> dict[str, Any]:
    duration = max(0.0, _number(duration_sec) or 0.0)
    minutes = duration / 60.0
    snapshot = meta.get("rate_snapshot") if isinstance(meta.get("rate_snapshot"), dict) else {}
    candidates = (
        ("applied", applied_inr_paise, applied_usd_micros),
        ("rate_snapshot", snapshot.get("inrPaisePerMin"), snapshot.get("usdMicrosPerMin")),
        (
            "catalog",
            (tier_rate or {}).get("inrPaisePerMin"),
            (tier_rate or {}).get("usdMicrosPerMin"),
        ),
    )
    for source, inr_paise, usd_micros in candidates:
        inr_rate = _nonnegative(inr_paise)
        usd_rate = _nonnegative(usd_micros)
        if inr_rate is None and usd_rate is None:
            continue
        inr_per_min = inr_rate / 100.0 if inr_rate is not None else (usd_rate * fx if usd_rate is not None and fx else None)
        usd_per_min = usd_rate / 1_000_000.0 if usd_rate is not None else (inr_rate / fx if inr_rate is not None and fx else None)
        return {
            "source": source,
            "rateInrPerMin": _money(inr_per_min, 2),
            "rateUsdPerMin": _money(usd_per_min, 4),
            "totalBilledInr": _money((inr_per_min or 0.0) * minutes, 2) if inr_per_min is not None else None,
            "totalBilledUsd": _money((usd_per_min or 0.0) * minutes, 4) if usd_per_min is not None else None,
        }
    # A zero-second call bills nothing even when no rate could be resolved.
    if duration == 0:
        return {
            "source": "zero_duration",
            "rateInrPerMin": None,
            "rateUsdPerMin": None,
            "totalBilledInr": 0.0,
            "totalBilledUsd": 0.0,
        }
    return {
        "source": "unavailable",
        "rateInrPerMin": None,
        "rateUsdPerMin": None,
        "totalBilledInr": None,
        "totalBilledUsd": None,
    }


def _stage_costs(result: dict | None) -> dict[str, dict[str, Any]]:
    stages = (result or {}).get("stages") if isinstance(result, dict) else {}
    output = {}
    for stage in _STAGE_KEYS:
        row = (stages or {}).get(stage) if isinstance((stages or {}).get(stage), dict) else {}
        components = row.get("components") if isinstance(row.get("components"), list) else []
        output[stage] = {
            "status": row.get("status"),
            "costInr": _number(row.get("costInr")),
            "costUsd": _number(row.get("costUsd")),
            "components": components,
        }
    return output


def _measured_stage_result(meta: dict) -> dict[str, Any] | None:
    # Recompute from the immutable snapshot instead of trusting the mutable cache:
    # older writers could price a model with a rate that was never pinned.
    snapshot = meta.get("provider_cost_snapshot")
    if isinstance(snapshot, dict):
        try:
            return price_composed_usage(snapshot, meta.get("stage_usage"))
        except (ValueError, KeyError, TypeError, ArithmeticError):
            return {"status": "incomplete", "missing": ["invalid_cost_snapshot"], "stages": {}, "totalInr": None, "totalUsd": None}
    stored = meta.get("provider_cost_result")
    if isinstance(stored, dict) and stored.get("status") in {"ready", "incomplete"}:
        return stored
    return None


def _carrier(meta: dict, *, channel: str, fx: float | None) -> dict[str, Any]:
    if channel != "pstn":
        return {"status": "not_applicable", "source": "not_applicable", "amountInr": 0.0, "amountUsd": 0.0, "raw": {}}
    billed = meta.get("carrier_billing") if isinstance(meta.get("carrier_billing"), dict) else {}
    amount = _nonnegative(billed.get("amount"))
    currency = str(billed.get("currency") or "").upper()
    if billed.get("source") == "vobiz_cdr" and amount is not None and currency in {"INR", "USD"}:
        inr = amount if currency == "INR" else (amount * fx if fx else None)
        usd = amount if currency == "USD" else (amount / fx if fx else None)
        return {
            "status": "actual",
            "source": "vobiz_cdr",
            "amountInr": _money(inr, 4),
            "amountUsd": _money(usd, 6),
            "raw": billed,
        }
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    inr = _nonnegative(usage.get("telephony_inr"))
    usd = _nonnegative(usage.get("telephony_usd"))
    if inr is None and usd is not None and fx:
        inr = usd * fx
    if usd is None and inr is not None and fx:
        usd = inr / fx
    if inr is None and usd is None:
        return {"status": "unavailable", "source": "unavailable", "amountInr": None, "amountUsd": None, "raw": billed}
    return {
        "status": "estimate",
        "source": str(usage.get("carrier_cost_source") or "tariff_estimate"),
        "amountInr": _money(inr, 4),
        "amountUsd": _money(usd, 6),
        "raw": billed,
    }


def _supplementary(meta: dict, *, fx: float | None) -> dict[str, Any]:
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    live_inr = _nonnegative(usage.get("live_transcript_inr")) or 0.0
    post_inr = _nonnegative(usage.get("post_call_transcript_inr")) or 0.0
    live_usd = _nonnegative(usage.get("live_transcript_usd")) or 0.0
    post_usd = _nonnegative(usage.get("post_call_transcript_usd")) or 0.0
    analysis_usd = _nonnegative(usage.get("post_call_analysis_usd")) or 0.0
    analysis_inr = analysis_usd * fx if fx is not None else (0.0 if analysis_usd == 0 else None)
    inr = live_inr + post_inr + analysis_inr if analysis_inr is not None else None
    return {
        "costInr": _money(inr, 4),
        "costUsd": _money(live_usd + post_usd + analysis_usd, 6),
    }


def _supplier(meta: dict, *, channel: str, fx: float | None) -> dict[str, Any]:
    measured = _measured_stage_result(meta)
    missing: list[str] = []
    stage_costs = _stage_costs(measured)
    if measured is not None:
        status = str(measured.get("status") or "incomplete")
        ai_inr = _number(measured.get("totalInr")) if status == "ready" else None
        ai_usd = _number(measured.get("totalUsd")) if status == "ready" else None
        missing.extend(str(item) for item in measured.get("missing") or [])
    else:
        usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
        ai_usd = _number(usage.get("model_cost_usd"))
        ai_inr = _number(usage.get("model_cost_inr"))
        if ai_inr is None and ai_usd is not None and fx:
            ai_inr = ai_usd * fx
        if ai_usd is None and ai_inr is not None and fx:
            ai_usd = ai_inr / fx
        status = "ready" if ai_inr is not None and ai_usd is not None else "incomplete"
        if status != "ready":
            missing.append("model_cost")
    carrier = _carrier(meta, channel=channel, fx=fx)
    other = _supplementary(meta, fx=fx)
    if carrier["status"] == "unavailable":
        missing.append("carrier_cost")
    if other["costInr"] is None or other["costUsd"] is None:
        missing.append("supplementary_cost")
        other_inr = other_usd = None
    else:
        other_inr, other_usd = other["costInr"], other["costUsd"]
        if other_inr == 0 and other_usd == 0:
            other_inr = other_usd = 0.0
    total_inr = total_usd = None
    if status == "ready" and carrier["amountInr"] is not None and other_inr is not None:
        total_inr = ai_inr + carrier["amountInr"] + other_inr
    if status == "ready" and carrier["amountUsd"] is not None and other_usd is not None:
        total_usd = ai_usd + carrier["amountUsd"] + other_usd
    if total_inr is None or total_usd is None:
        status = "incomplete"
        if "carrier_cost" not in missing and (carrier["amountInr"] is None or carrier["amountUsd"] is None):
            missing.append("carrier_cost")
    return {
        "status": status,
        "missing": list(dict.fromkeys(missing)),
        "totalInr": _money(total_inr, 4),
        "totalUsd": _money(total_usd, 6),
        "stages": stage_costs,
        "carrier": carrier,
        "other": other,
    }


def build_call_costs(
    *,
    meta: dict,
    channel: str,
    tier: str,
    duration_sec: float,
    applied_inr_paise: Any,
    applied_usd_micros: Any,
    current_rates: dict | None,
    tier_rate: dict | None = None,
) -> dict[str, Any]:
    channel_norm = str(channel or "pstn").strip().lower()
    fx = _fx_rate(meta, current_rates)
    retail = _retail(
        meta,
        duration_sec=duration_sec,
        applied_inr_paise=applied_inr_paise,
        applied_usd_micros=applied_usd_micros,
        tier_rate=tier_rate,
        fx=fx,
    )
    supplier = _supplier(meta, channel=channel_norm, fx=fx)
    margin_inr = margin_usd = margin_percent = None
    if retail["totalBilledInr"] is not None and supplier["totalInr"] is not None:
        margin_inr = retail["totalBilledInr"] - supplier["totalInr"]
        if retail["totalBilledInr"] > 0:
            margin_percent = margin_inr * 100.0 / retail["totalBilledInr"]
    if retail["totalBilledUsd"] is not None and supplier["totalUsd"] is not None:
        margin_usd = retail["totalBilledUsd"] - supplier["totalUsd"]
    status = "ready" if margin_inr is not None and retail["source"] != "unavailable" else "incomplete"
    missing = list(supplier["missing"])
    if retail["source"] == "unavailable":
        missing.append("retail_rate")
    return {
        "status": status,
        "missing": list(dict.fromkeys(missing)),
        "fxRateInr": _money(fx, 4),
        "tier": tier,
        "retail": retail,
        "supplier": supplier,
        "margin": {
            "inr": _money(margin_inr, 2),
            "usd": _money(margin_usd, 4),
            "percent": _money(margin_percent, 1),
        },
    }
