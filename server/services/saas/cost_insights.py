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


def call_cost(row: dict, meta: dict, fallback_fx: float) -> dict | None:
    from server.services.usage_pricing import cost_telnyx_call_breakdown, cost_vobiz_call_breakdown

    usage = meta.get("usage") or {}
    if not isinstance(usage, dict):
        return None
    api_usd, model_source = model_cost(usage)
    if api_usd is None:
        return None
    api_usd += amount(usage.get("post_call_analysis_usd")) or Decimal(0)
    fx = amount(usage.get("fx_rate_inr")) or Decimal(str(fallback_fx))
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
    api_inr = api_usd * fx
    transcript_inr = transcript_usd * fx
    return {"callId": row["call_id"], "tenantId": row["tenant_id"], "channel": row["channel"],
        "seconds": seconds, "modelUsd": api_usd, "modelInr": api_inr, "carrierUsd": carrier_usd, "carrierInr": carrier_inr,
        "transcriptUsd": transcript_usd, "transcriptInr": transcript_inr,
        "costUsd": api_usd + carrier_usd + transcript_usd, "costInr": api_inr + carrier_inr + transcript_inr,
        "model": usage.get("llm_model") or "unknown", "modelSource": model_source, "carrierSource": carrier_source}


def build_insights(rows: list[dict], rates: dict, *, since: datetime, now: datetime, capped: bool = False,
                   ledger=None, overhead_rows: list[dict] | None = None) -> dict:
    from server.call.call_ledger import call_ledger
    ledger = ledger or call_ledger
    fx = float(rates["fx_rate_inr"])
    eligible, missing = [], {"pstn": 0, "browser": 0}
    for row in rows:
        try:
            meta = ledger.read_meta(row["call_id"])
            # Call attribution is checked against the authoritative database row.
            item = call_cost(row, meta, fx) if isinstance(meta, dict) and str(meta.get("tenant_id") or "") == str(row["tenant_id"]) else None
        except (OSError, ValueError, TypeError, AttributeError, ArithmeticError):
            item = None  # Corrupt/incomplete records reduce coverage, never the divisor.
        if item is None:
            missing[row["channel"]] += 1
        else:
            eligible.append(item)
    # Full-window overhead would inflate a truncated call cohort's unit cost.
    overhead = [] if capped else (overhead_rows if overhead_rows is not None else read_unused_prewarm(since, now))
    channels = []
    for channel, label in (("pstn", "PSTN calls"), ("browser", "Web agent test calls")):
        records = [item for item in eligible if item["channel"] == channel]
        seconds = sum((item["seconds"] for item in records), Decimal(0))
        minutes = seconds / 60
        setup_usd = sum((amount(item.get("cost_usd")) or Decimal(0) for item in overhead), Decimal(0)) if channel == "pstn" else Decimal(0)
        setup_inr = sum((amount(item.get("cost_inr")) or Decimal(0) for item in overhead), Decimal(0)) if channel == "pstn" else Decimal(0)
        usd = sum((item["costUsd"] for item in records), setup_usd)
        inr = sum((item["costInr"] for item in records), setup_inr)
        call_count = len(records)
        current_key = "pstn" if channel == "pstn" else "web_agent"
        channels.append({"channel": channel, "label": label, "costUsd": number(usd), "costInr": number(inr),
            "connectedMinutes": number(minutes), "calls": call_count, "tenants": len({r["tenantId"] for r in records}),
            "missingCostCalls": missing[channel], "coveragePercent": round(call_count * 100 / (call_count + missing[channel]), 1) if call_count + missing[channel] else None,
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
            "unconnectedPrewarmUsd": number(setup_usd), "unconnectedPrewarmInr": number(setup_inr),
            "unconnectedPrewarmRecords": len(overhead) if channel == "pstn" else 0,
            "carrierCdrCalls": sum(r["carrierSource"] == "vobiz_cdr" for r in records),
            "carrierEstimatedCalls": sum(r["carrierSource"] == "tariff_estimate" for r in records),
            "reconstructedCalls": sum(r["modelSource"] == "reconstructed_responses" for r in records),
            "currentPriceUsdPerMin": rates[f"{current_key}_rate_usd_micros_per_min"] / 1_000_000,
            "currentPriceInrPerMin": rates[f"{current_key}_rate_inr_paise_per_min"] / 100,
            "models": sorted({r["model"] for r in records})})
    sample = random.SystemRandom().sample(eligible, min(8, len(eligible)))
    return {"asOf": now.isoformat(), "since": since.isoformat(), "method": "duration_weighted", "windowCapped": capped,
        "callsReviewed": len(rows), "fxRateInr": fx, "channels": channels,
        "samples": [{"callId": r["callId"], "tenant": "Tenant " + r["tenantId"][:8], "channel": r["channel"],
            "durationSec": number(r["seconds"]), "costUsd": number(r["costUsd"]), "costInr": number(r["costInr"]),
            "model": r["model"], "carrierSource": r["carrierSource"]} for r in sample],
        "notes": ["Average = known supplier costs / connected minutes; each minute has equal weight.",
            "API costs use reported tokens at published rates. Carrier CDR totals are used when available; tariffs are estimates.",
            "Known unused prewarm spend is included in PSTN costs. Older unrecorded setup/summary spend, hosting, taxes and negotiated discounts are not included.",
            "Records without usable cost attribution are excluded and shown in coverage. This is pricing guidance, not a supplier invoice."]}


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
        result = await db.execute(select(Call.call_id, Call.tenant_id, Call.channel, Call.direction, Call.duration_sec, Call.session_id)
            .join(Tenant, Tenant.tenant_id == Call.tenant_id)
            .where(Tenant.deleted_at.is_(None), Call.ended_at.is_not(None), Call.ended_at >= since, Call.channel.in_(["pstn", "browser"]))
            .order_by(desc(Call.ended_at)).limit(MAX_CALLS + 1))
        rows = [{**dict(row._mapping), "call_id": str(row.call_id), "tenant_id": str(row.tenant_id)} for row in result]
    rates = await load_current_rates()
    return await asyncio.to_thread(build_insights, rows[:MAX_CALLS], rates, since=since, now=now, capped=len(rows) > MAX_CALLS)
