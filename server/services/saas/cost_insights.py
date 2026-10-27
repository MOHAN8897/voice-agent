"""Privileged, read-only supplier cost analysis for the platform wallet page."""
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import desc, select

MAX_CALLS = 5000


def amount(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def number(value: Decimal | None) -> float | None:
    return float(round(value, 8)) if value is not None else None


def model_cost(usage: dict) -> tuple[Decimal | None, str]:
    if usage.get("cost_accounting_version") == 3:
        return (amount(usage.get("model_cost_usd")) if usage.get("supplier_cost_status") == "ready" else None), "measured_stages"
    if str(usage.get("llm_model") or "").lower() in {"", "unknown"}:
        return None, "missing_model_usage"
    if usage.get("cost_accounting_version") == 2:
        return amount(usage.get("model_cost_usd")), "reported_tokens"
    from server.realtime.models import is_gemini_live_voice_model
    if is_gemini_live_voice_model(usage.get("llm_model")):
        snapshots = usage.get("response_usage") or {}
        if not isinstance(snapshots, dict):
            return None, "invalid_response_usage"
        costs = [amount(row.get("cost_usd")) for row in snapshots.values() if isinstance(row, dict)]
        if not costs or any(cost is None for cost in costs):
            return None, "missing_response_usage"
        # Older calls kept response snapshots but incorrectly retained only the
        # last session total. Reconstruct for analysis without altering wallets.
        total = sum(costs, Decimal(0))
        prewarm = amount(usage.get("prewarm_cost_usd")) or Decimal(0)
        prewarm_in = int(usage.get("prewarm_input_tokens") or 0)
        prewarm_out = int(usage.get("prewarm_output_tokens") or 0)
        already_present = any(
            row.get("prewarm") or (row.get("input_tokens") == prewarm_in and row.get("output_tokens") == prewarm_out)
            for row in snapshots.values() if isinstance(row, dict)
        )
        return total + (Decimal(0) if already_present else prewarm), "reconstructed_responses"
    return amount(usage.get("model_cost_usd")), "stored_model_cost"


def _catalog_retail(row: dict, rates: dict, tier_records: dict | None) -> tuple[Any, Any] | None:
    from server.services.saas.voice_stack_profiles import (
        _native_tier_retail_rate,
        _web_tier_retail_rate,
    )

    if str(row.get("channel") or "") == "browser":
        tier = str(row.get("tier") or "medium").lower()
        resolved = _web_tier_retail_rate(rates, tier, record=(tier_records or {}).get(tier))
        return (resolved["inrPaisePerMin"], resolved["usdMicrosPerMin"]) if resolved else None
    tier = str(row.get("tier") or "premium").lower()
    record = (tier_records or {}).get(tier)
    resolved = _native_tier_retail_rate(rates, tier, record=record)
    return (resolved["inrPaisePerMin"], resolved["usdMicrosPerMin"]) if resolved else None


def call_retail(row: dict, meta: dict, *, rates: dict, tier_records: dict | None, fallback_fx: float) -> dict | None:
    """Customer price actually pinned to this call; never inferred from another tier."""
    seconds = amount(meta.get("carrier_billable_duration_sec", row.get("duration_sec")))
    if seconds is None:
        return None
    snapshot = meta.get("rate_snapshot") if isinstance(meta.get("rate_snapshot"), dict) else {}
    supplier_snapshot = meta.get("provider_cost_snapshot") if isinstance(meta.get("provider_cost_snapshot"), dict) else {}
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    fx = (
        amount(row.get("applied_fx_rate_inr"))
        or amount(snapshot.get("fxRateInr"))
        or amount(supplier_snapshot.get("fxRateInr"))
        or amount(usage.get("fx_rate_inr"))
        or Decimal(str(fallback_fx))
    )
    candidates = [
        (row.get("applied_rate_inr_paise_per_min"), row.get("applied_rate_usd_micros_per_min"), "applied"),
        (snapshot.get("inrPaisePerMin"), snapshot.get("usdMicrosPerMin"), "rate_snapshot"),
    ]
    catalog = _catalog_retail(row, rates, tier_records)
    if catalog:
        candidates.append((catalog[0], catalog[1], "catalog"))
    minutes = seconds / 60
    for inr_paise, usd_micros, source in candidates:
        inr_rate = amount(inr_paise)
        usd_rate = amount(usd_micros)
        if inr_rate is None and usd_rate is None:
            continue
        inr_per_min = inr_rate / 100 if inr_rate is not None else usd_rate * fx / 1_000_000
        usd_per_min = usd_rate / 1_000_000 if usd_rate is not None else inr_rate / fx / 100
        return {
            "source": source,
            "retailInr": inr_per_min * minutes,
            "retailUsd": usd_per_min * minutes,
            "fx": fx,
        }
    return None


def call_cost(row: dict, meta: dict, fallback_fx: float) -> dict | None:
    from server.services.usage_pricing import cost_telnyx_call_breakdown, cost_vobiz_call_breakdown

    usage = meta.get("usage") or {}
    if not isinstance(usage, dict):
        return None
    pipeline = str(meta.get("pipeline") or usage.get("pipeline") or "")
    snapshot = meta.get("provider_cost_snapshot")
    measured_inr = None
    if pipeline == "composed_voice" and isinstance(snapshot, dict):
        # The pinned snapshot and measured counters are the source of truth;
        # stored usage totals can be stale after concurrent metadata writes.
        from server.services.saas.composed_costing import price_composed_usage

        try:
            measured = price_composed_usage(snapshot, meta.get("stage_usage"))
        except (ValueError, KeyError, TypeError, ArithmeticError):
            measured = {"status": "incomplete"}
        if measured.get("status") != "ready":
            return None
        api_usd, model_source = amount(measured.get("totalUsd")), "pinned_snapshot"
        measured_inr = amount(measured.get("totalInr"))
    else:
        api_usd, model_source = model_cost(usage)
    if api_usd is None:
        return None
    analysis_usd = amount(usage.get("post_call_analysis_usd")) or Decimal(0)
    api_usd += analysis_usd
    snapshot_fx = amount(snapshot.get("fxRateInr")) if isinstance(snapshot, dict) else None
    fx = snapshot_fx or amount(usage.get("fx_rate_inr")) or Decimal(str(fallback_fx))
    seconds = amount(meta.get("carrier_billable_duration_sec", row.get("duration_sec")))
    if seconds is None:
        return None
    carrier_usd = carrier_inr = Decimal(0)
    carrier_source = "not_applicable"
    if row["channel"] == "pstn":
        billed = meta.get("carrier_billing") or {}
        actual = amount(billed.get("amount"))
        currency = billed.get("currency")
        if billed.get("source") == "vobiz_cdr" and actual is not None and currency in {"USD", "INR"}:
            carrier_usd = actual if currency == "USD" else actual / fx
            carrier_inr = actual if currency == "INR" else actual * fx
            carrier_source = "vobiz_cdr"
        else:
            provider = str(meta.get("telephony_provider") or usage.get("telephony_provider") or "")
            if provider == "vobiz" or meta.get("vobiz_call_uuid") or "vobiz" in str(row.get("session_id") or ""):
                estimate = cost_vobiz_call_breakdown(duration_sec=float(seconds), direction=row.get("direction"),
                    call_recording=bool(meta.get("recording_enabled")), call_transcription=bool(meta.get("transcription_enabled")), fx_rate_inr=float(fx))
                carrier_usd = Decimal(str(estimate["total_usd"]))
                carrier_inr = Decimal(str(estimate["total_inr"]))
            elif provider == "telnyx" or "telnyx" in str(row.get("session_id") or ""):
                from server.services.usage_pricing import telnyx_destination_country_from_e164
                estimate = cost_telnyx_call_breakdown(duration_sec=float(seconds), direction=row.get("direction"), media_streaming=True,
                    call_recording=bool(meta.get("recording_enabled")), destination_country=telnyx_destination_country_from_e164(meta.get("callee_e164")))
                carrier_usd = Decimal(str(estimate["total_usd"]))
                carrier_inr = carrier_usd * fx
            else:
                return None
            carrier_source = "tariff_estimate"
    transcript_usd = sum((amount(usage.get(key)) or Decimal(0) for key in ("live_transcript_usd", "post_call_transcript_usd")), Decimal(0))
    api_inr = (measured_inr if measured_inr is not None else api_usd * fx)
    if measured_inr is not None:
        api_inr += analysis_usd * fx
    transcript_inr = transcript_usd * fx
    call_tier = str(row.get("tier") or "premium").lower()
    return {
        "callId": row["call_id"],
        "tenantId": row["tenant_id"],
        "channel": row["channel"],
        "tier": call_tier,
        "seconds": seconds,
        "modelUsd": api_usd,
        "modelInr": api_inr,
        "carrierUsd": carrier_usd,
        "carrierInr": carrier_inr,
        "transcriptUsd": transcript_usd,
        "transcriptInr": transcript_inr,
        "costUsd": api_usd + carrier_usd + transcript_usd,
        "costInr": api_inr + carrier_inr + transcript_inr,
        "model": usage.get("llm_model") or "unknown",
        "modelSource": model_source,
        "carrierSource": carrier_source,
    }


def _price_per_min(rates: dict, key: str, fallback_key: str | None = None, *, micros: bool) -> float | None:
    value = amount(rates.get(key))
    if value is None and fallback_key:
        value = amount(rates.get(fallback_key))
    if value is None:
        return None
    return float(value / (1_000_000 if micros else 100))


def build_insights(rows: list[dict], rates: dict, *, since: datetime, now: datetime, capped: bool = False,
                   ledger=None, overhead_rows: list[dict] | None = None,
                   tier_records: dict | None = None) -> dict:
    from server.call.call_ledger import call_ledger
    ledger = ledger or call_ledger
    fx = float(rates["fx_rate_inr"])
    eligible = []
    for row in rows:
        try:
            meta = ledger.read_meta(row["call_id"])
            # Call attribution is checked against the authoritative database row.
            item = call_cost(row, meta, fx) if isinstance(meta, dict) and str(meta.get("tenant_id") or "") == str(row["tenant_id"]) else None
            retail = call_retail(row, meta, rates=rates, tier_records=tier_records, fallback_fx=fx) if item is not None else None
        except (OSError, ValueError, TypeError, AttributeError, ArithmeticError):
            item = None  # Corrupt/incomplete records reduce coverage, never the divisor.
            retail = None
        if item is not None:
            if retail is not None:
                item["retailInr"] = retail["retailInr"]
                item["retailUsd"] = retail["retailUsd"]
                item["retailSource"] = retail["source"]
                item["marginInr"] = retail["retailInr"] - item["costInr"]
                item["marginUsd"] = retail["retailUsd"] - item["costUsd"]
            eligible.append(item)
    # Full-window overhead would inflate a truncated call cohort's unit cost.
    overhead = [] if capped else (overhead_rows if overhead_rows is not None else read_unused_prewarm(since, now))
    
    from server.services.saas.voice_stack_profiles import _native_tier_retail_rate

    tier_configs = [("pstn_premium", "Flagship Live PSTN", "premium", True)]
    custom_tiers = sorted(tier for tier in (tier_records or {}) if tier not in {"premium", "medium", "low"})
    for tier_name in ("medium", "low", *custom_tiers):
        profile = ((tier_records or {}).get(tier_name) or {}).get("profile") or {}
        label = str(profile.get("label") or "").strip() or {
            "medium": "Standard Regional PSTN",
            "low": "Economical PSTN",
        }.get(tier_name, f"{tier_name.replace('_', ' ').title()} PSTN")
        tier_configs.append((f"pstn_{tier_name}", label, tier_name, False))
    tier_configs.append(("browser", "Web Agent Test Calls", None, False))
    channels = []
    for ch_key, label, tier_val, has_prewarm in tier_configs:
        if tier_val is not None:
            records = [item for item in eligible if item["channel"] == "pstn" and item.get("tier") == tier_val]
            missing_count = sum(1 for r in rows if r.get("channel") == "pstn" and str(r.get("tier") or "premium").lower() == tier_val and r["call_id"] not in {it["callId"] for it in eligible})
        else:
            records = [item for item in eligible if item["channel"] == "browser"]
            missing_count = sum(1 for r in rows if r.get("channel") == "browser" and r["call_id"] not in {it["callId"] for it in eligible})

        seconds = sum((item["seconds"] for item in records), Decimal(0))
        minutes = seconds / 60
        setup_usd = sum((amount(item.get("cost_usd")) or Decimal(0) for item in overhead), Decimal(0)) if has_prewarm else Decimal(0)
        setup_inr = sum((amount(item.get("cost_inr")) or Decimal(0) for item in overhead), Decimal(0)) if has_prewarm else Decimal(0)
        usd = sum((item["costUsd"] for item in records), setup_usd)
        inr = sum((item["costInr"] for item in records), setup_inr)
        call_count = len(records)

        if tier_val is None:
            current_price_usd = _price_per_min(rates, "web_agent_rate_usd_micros_per_min", micros=True)
            current_price_inr = _price_per_min(rates, "web_agent_rate_inr_paise_per_min", micros=False)
        else:
            resolved_price = _native_tier_retail_rate(
                rates, tier_val, record=(tier_records or {}).get(tier_val)
            )
            current_price_usd = float(resolved_price["usdMicrosPerMin"]) / 1_000_000 if resolved_price else None
            current_price_inr = float(resolved_price["inrPaisePerMin"]) / 100 if resolved_price else None

        priced = [item for item in records if item.get("retailInr") is not None]
        retail_inr = sum((item["retailInr"] for item in priced), Decimal(0))
        retail_usd = sum((item["retailUsd"] for item in priced), Decimal(0))
        margin_inr = sum((item["marginInr"] for item in priced), Decimal(0))
        margin_usd = sum((item["marginUsd"] for item in priced), Decimal(0))

        channels.append({
            "channel": ch_key,
            "label": label,
            "costUsd": number(usd),
            "costInr": number(inr),
            "retailUsd": number(retail_usd) if priced else None,
            "retailInr": number(retail_inr) if priced else None,
            "marginUsd": number(margin_usd) if priced else None,
            "marginInr": number(margin_inr) if priced else None,
            "marginPercent": round(float(margin_inr * 100 / retail_inr), 1) if retail_inr > 0 else None,
            "retailPricedCalls": len(priced),
            "retailCoveragePercent": round(len(priced) * 100 / call_count, 1) if call_count else None,
            "connectedMinutes": number(minutes),
            "calls": call_count,
            "tenants": len({r["tenantId"] for r in records}),
            "missingCostCalls": missing_count,
            "coveragePercent": round(call_count * 100 / (call_count + missing_count), 1) if call_count + missing_count else None,
            "averageUsdPerMin": number(usd / minutes) if minutes else None,
            "averageInrPerMin": number(inr / minutes) if minutes else None,
            "carrierPerMinUsd": number(sum((r["carrierUsd"] for r in records), Decimal(0)) / minutes) if minutes else 0.0,
            "carrierPerMinInr": number(sum((r["carrierInr"] for r in records), Decimal(0)) / minutes) if minutes else 0.0,
            "apiPerMinUsd": number(sum((r["modelUsd"] for r in records), Decimal(0)) / minutes) if minutes else 0.0,
            "apiPerMinInr": number(sum((r["modelInr"] for r in records), Decimal(0)) / minutes) if minutes else 0.0,
            "transcriptionPerMinUsd": number(sum((r["transcriptUsd"] for r in records), Decimal(0)) / minutes) if minutes else 0.0,
            "transcriptionPerMinInr": number(sum((r["transcriptInr"] for r in records), Decimal(0)) / minutes) if minutes else 0.0,
            "apiUsd": number(sum((r["modelUsd"] for r in records), Decimal(0))),
            "apiInr": number(sum((r["modelInr"] for r in records), Decimal(0))),
            "carrierUsd": number(sum((r["carrierUsd"] for r in records), Decimal(0))),
            "carrierInr": number(sum((r["carrierInr"] for r in records), Decimal(0))),
            "transcriptionUsd": number(sum((r["transcriptUsd"] for r in records), Decimal(0))),
            "transcriptionInr": number(sum((r["transcriptInr"] for r in records), Decimal(0))),
            "unconnectedPrewarmUsd": number(setup_usd),
            "unconnectedPrewarmInr": number(setup_inr),
            "prewarmPerMinUsd": number(setup_usd / minutes) if minutes else 0.0,
            "prewarmPerMinInr": number(setup_inr / minutes) if minutes else 0.0,
            "unconnectedPrewarmRecords": len(overhead) if has_prewarm else 0,
            "carrierCdrCalls": sum(r["carrierSource"] == "vobiz_cdr" for r in records),
            "carrierEstimatedCalls": sum(r["carrierSource"] == "tariff_estimate" for r in records),
            "reconstructedCalls": sum(r["modelSource"] == "reconstructed_responses" for r in records),
            "currentPriceUsdPerMin": current_price_usd,
            "currentPriceInrPerMin": current_price_inr,
            "models": sorted({r["model"] for r in records}),
        })

    sample = random.SystemRandom().sample(eligible, min(8, len(eligible)))
    return {
        "asOf": now.isoformat(),
        "since": since.isoformat(),
        "method": "duration_weighted",
        "windowCapped": capped,
        "callsReviewed": len(rows),
        "fxRateInr": fx,
        "channels": channels,
        "samples": [
            {
                "callId": r["callId"],
                "tenant": "Tenant " + r["tenantId"][:8],
                "channel": r["channel"],
                "tier": r.get("tier"),
                "durationSec": number(r["seconds"]),
                "costUsd": number(r["costUsd"]),
                "costInr": number(r["costInr"]),
                "retailUsd": number(r["retailUsd"]) if r.get("retailUsd") is not None else None,
                "retailInr": number(r["retailInr"]) if r.get("retailInr") is not None else None,
                "marginUsd": number(r["marginUsd"]) if r.get("marginUsd") is not None else None,
                "marginInr": number(r["marginInr"]) if r.get("marginInr") is not None else None,
                "retailSource": r.get("retailSource"),
                "model": r["model"],
                "carrierSource": r["carrierSource"],
            }
            for r in sample
        ],
        "notes": [
            "Average = known supplier costs / connected minutes; each minute has equal weight.",
            "API costs use reported tokens at published rates. Carrier CDR totals are used when available; tariffs are estimates.",
            "Margin uses the retail rate pinned to each call; calls without a pinned price are excluded from margin and shown in retail coverage.",
            "Known unused prewarm spend is included in Flagship PSTN costs. Older unrecorded setup/summary spend, hosting, taxes and negotiated discounts are not included.",
            "Records without usable cost attribution are excluded and shown in coverage. This is pricing guidance, not a supplier invoice.",
        ],
    }


def read_unused_prewarm(since: datetime, now: datetime) -> list[dict]:
    from server.services.saas.prewarm_cost_records import record_directory
    records = []
    root = record_directory()
    paths = list(root.glob("*.json"))  # Compatibility with early flat records.
    day = since.date()
    while day <= now.date():
        paths.extend((root / day.isoformat()).glob("*.json"))
        day += timedelta(days=1)
    for path in paths:
        try:
            if path.stat().st_size > 20_000:
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(value["created_at"])
            if not since <= created <= now or value.get("call_id"):
                continue
            if value.get("status") == "unused" or (now - created).total_seconds() > 300:
                if amount(value.get("cost_usd")) is not None and value.get("tenant_id"):
                    records.append(value)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return records


async def load_cost_insights(days: int = 30) -> dict:
    """Called only after the platform billing permission gate; crosses tenants."""
    from server.db.connection import get_session_factory
    from server.db.models.entities import Call, Tenant
    from server.services.saas.billing_rates import load_current_rates
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    async with get_session_factory()() as db:
        result = await db.execute(
            select(
                Call.call_id,
                Call.tenant_id,
                Call.channel,
                Call.direction,
                Call.duration_sec,
                Call.session_id,
                Call.tier,
                Call.applied_rate_inr_paise_per_min,
                Call.applied_rate_usd_micros_per_min,
                Call.applied_fx_rate_inr,
            )
            .join(Tenant, Tenant.tenant_id == Call.tenant_id)
            .where(Tenant.deleted_at.is_(None), Call.ended_at.is_not(None), Call.ended_at >= since, Call.channel.in_(["pstn", "browser"]))
            .order_by(desc(Call.ended_at))
            .limit(MAX_CALLS + 1)
        )
        rows = [
            {
                **dict(row._mapping),
                "call_id": str(row.call_id),
                "tenant_id": str(row.tenant_id),
                "tier": str(getattr(row, "tier", None) or "premium").lower(),
            }
            for row in result
        ]
    rates = await load_current_rates()
    from server.services.dev_runtime import effective_app_environment
    from server.services.saas.voice_stack_profiles import load_profile_records

    tier_records = await load_profile_records(effective_app_environment(), None)
    return await asyncio.to_thread(
        build_insights,
        rows[:MAX_CALLS],
        rates,
        since=since,
        now=now,
        capped=len(rows) > MAX_CALLS,
        tier_records=tier_records,
    )
