"""Estimated server (hosting) cost of a live call on Railway.

Railway bills containers per second for the vCPU and memory they actually use,
plus network egress. A call occupies a share of the voice service for as long
as it is connected, so its hosting cost is

    minutes * (vCPU share * vCPU price + GB share * memory price)
    + minutes * egress MB per minute / 1024 * egress price.

The shares are planning assumptions, not measurements, so every result is
labelled as an estimate. The plan base fee and idle always-on replicas are not
allocated to calls: the Pro fee is returned as usage credit, and idle capacity
is a fixed cost, not a cost of serving one more call.
"""
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any

# Railway published usage pricing, checked 2026-11-02:
#   https://railway.com/pricing  (vCPU $0.00000772/s, memory $0.00000386/GB/s, egress $0.05/GB)
#   https://docs.railway.com/reference/pricing/plans  (per-minute rates below; egress
#   $0.000000047683716/KB, i.e. 1 GB = 1,048,576 KB)
# Plans: Hobby $5/month, Pro $20/month per workspace, each including the same
# amount of usage credit. Per-call shares follow PRODUCTION_SCALING_AUDIT.md: one
# vCPU worker carries 10-12 concurrent calls and 2 vCPU / 2 GB serves ~20 calls.
# Egress is the audio the server sends out: 8 kHz mu-law to the carrier
# (64 kbps = 0.48 MB/min) plus 16 kHz PCM16 to speech recognition
# (256 kbps = 1.92 MB/min). Every value can be overridden with the env var named.
RAILWAY_PRICING_SOURCE_URL = "https://railway.com/pricing"
RAILWAY_PRICING_DOCS_URL = "https://docs.railway.com/reference/pricing/plans"
RAILWAY_PRICING_CHECKED_ON = "2026-11-02"
RAILWAY_HOSTING_DEFAULTS: dict[str, tuple[str, str]] = {
    # key: (default, env override)
    "vcpuUsdPerMinute": ("0.000463", "RAILWAY_VCPU_USD_PER_MINUTE"),
    "memoryGbUsdPerMinute": ("0.000231", "RAILWAY_MEMORY_GB_USD_PER_MINUTE"),
    "egressUsdPerGb": ("0.05", "RAILWAY_EGRESS_USD_PER_GB"),
    "vcpuPerCall": ("0.1", "RAILWAY_VCPU_PER_CALL"),
    "memoryGbPerCall": ("0.1", "RAILWAY_MEMORY_GB_PER_CALL"),
    "egressMbPerCallMinute": ("2.4", "RAILWAY_EGRESS_MB_PER_CALL_MINUTE"),
}
SERVER_COST_LABEL = "Server (Railway, estimated)"


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() and number >= 0 else None


def hosting_assumptions(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Railway unit prices and per-call shares in force, with their source.

    ``overrides`` (tests, callers) win over env vars, which win over defaults.
    An unparsable or negative override is ignored rather than zeroing a cost.
    """
    values: dict[str, str] = {}
    overridden: list[str] = []
    for key, (default, env_name) in RAILWAY_HOSTING_DEFAULTS.items():
        chosen = default
        for candidate in (os.getenv(env_name), (overrides or {}).get(key)):
            if _decimal(candidate) is not None:
                chosen = str(candidate).strip()
        if chosen != default:
            overridden.append(key)
        values[key] = chosen
    return {
        "label": SERVER_COST_LABEL,
        "provider": "railway",
        "sourceUrl": RAILWAY_PRICING_SOURCE_URL,
        "docsUrl": RAILWAY_PRICING_DOCS_URL,
        "checkedOn": RAILWAY_PRICING_CHECKED_ON,
        "overridden": overridden,
        **values,
    }


def server_cost_per_minute_usd(assumptions: dict[str, Any]) -> dict[str, Decimal]:
    def value(key: str) -> Decimal:
        parsed = _decimal(assumptions.get(key))
        return parsed if parsed is not None else Decimal(RAILWAY_HOSTING_DEFAULTS[key][0])

    cpu = value("vcpuPerCall") * value("vcpuUsdPerMinute")
    memory = value("memoryGbPerCall") * value("memoryGbUsdPerMinute")
    egress = value("egressMbPerCallMinute") / Decimal(1024) * value("egressUsdPerGb")
    return {"cpu": cpu, "memory": memory, "egress": egress, "total": cpu + memory + egress}


def price_call_hosting(
    duration_sec: Any,
    *,
    fx: float | Decimal | None,
    assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Estimated Railway cost of one call's connected time, in USD and INR.

    INR is ``None`` when no FX rate is known, the same as other USD suppliers.
    """
    resolved = assumptions or hosting_assumptions()
    per_min = server_cost_per_minute_usd(resolved)
    seconds = _decimal(duration_sec) or Decimal(0)
    minutes = seconds / 60
    fx_rate = _decimal(fx)
    fx_rate = fx_rate if fx_rate is not None and fx_rate > 0 else None

    def usd(value: Decimal) -> float:
        return float(round(value, 6))

    def inr(value: Decimal, places: int = 4) -> float | None:
        return float(round(value * fx_rate, places)) if fx_rate is not None else None

    total = per_min["total"] * minutes
    return {
        "status": "estimate",
        "source": "railway_usage_estimate",
        "label": SERVER_COST_LABEL,
        "costUsd": usd(total),
        "costInr": inr(total),
        "perMinuteUsd": float(round(per_min["total"], 10)),
        "perMinuteInr": inr(per_min["total"], 6),
        "components": {
            "cpuUsd": usd(per_min["cpu"] * minutes),
            "memoryUsd": usd(per_min["memory"] * minutes),
            "egressUsd": usd(per_min["egress"] * minutes),
        },
    }
