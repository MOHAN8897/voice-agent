"""Versioned supplier tariffs and measured stage costs for composed voice only.

These tariffs never set customer wallet prices or change the Premium Live path.
"""
from __future__ import annotations

import copy
import re
import threading
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import desc, func, select

from server.db.connection import get_session_factory
from server.db.models.entities import ConfigVersion

RESOURCE_TYPE = "composed_provider_costs"
RESOURCE_ID = "platform"
UNITS = {
    "stt": {"audio_minute"},
    "llm": {"input_tokens_million", "cached_input_tokens_million", "output_tokens_million"},
    "tts": {"characters_1000", "input_tokens_million", "output_audio_tokens_million"},
}
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:\-]{0,127}$")
_FIELDS = {"id", "stage", "provider", "model", "currency", "unit", "price", "effectiveFrom", "effectiveUntil", "sourceUrl"}
_USAGE_LOCK = threading.RLock()
LLM_USAGE_COUNTERS = frozenset({"input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"})


class ProviderCostError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code, self.status_code = code, status_code


def _decimal(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError("A nonnegative decimal value is required.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("A nonnegative decimal value is required.") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("A finite nonnegative decimal value is required.")
    return number


def _text(value: Decimal) -> str:
    return format(value, "f")


def default_provider_rates() -> list[dict[str, Any]]:
    """Published PAYG tariffs verified 2026-10-22; date boundaries are UTC."""
    rates: list[dict[str, Any]] = []

    def add(stage: str, provider: str, model: str, unit: str, price: str,
            currency: str, start: str, end: str | None = None) -> None:
        rates.append({
            "id": f"{provider}-{model}-{unit}-{start}", "stage": stage,
            "provider": provider, "model": model, "currency": currency,
            "unit": unit, "price": price, "effectiveFrom": start, "effectiveUntil": end,
            "sourceUrl": "https://www.sarvam.ai/api-pricing" if provider == "sarvam"
            else ("https://cartesia.ai/pricing" if provider == "cartesia"
            else ("https://gnani.ai/pricing" if provider == "gnani" else "https://ai.google.dev/gemini-api/docs/pricing")),
        })

    add("stt", "sarvam", "saaras:v3-realtime", "audio_minute", "0.49", "INR", "2026-10-10")
    add("stt", "sarvam", "saaras:v2", "audio_minute", "0.49", "INR", "2026-10-10")
    add("stt", "sarvam", "saaras:v1", "audio_minute", "0.49", "INR", "2026-10-10")
    add("tts", "sarvam", "bulbul:v4-flash", "characters_1000", "2", "INR", "2026-10-10")
    add("tts", "sarvam", "bulbul:v3", "characters_1000", "3", "INR", "2026-10-10")
    add("tts", "sarvam", "bulbul:v2", "characters_1000", "3", "INR", "2026-10-10")
    add("tts", "cartesia", "sonic-3.5", "characters_1000", "0.075", "USD", "2026-10-10")
    add("tts", "cartesia", "sonic-3.5-2026-05-04", "characters_1000", "0.075", "USD", "2026-10-10")
    add("tts", "gnani", "timbre-v3.0", "characters_1000", "3.5", "INR", "2026-10-10")
    add("tts", "gnani", "timbre-v2.5", "characters_1000", "2.5", "INR", "2026-10-10")
    for unit, price in (("input_tokens_million", "15"), ("cached_input_tokens_million", "5"), ("output_tokens_million", "60")):
        add("llm", "sarvam", "sarvam-105b-conversations", unit, price, "INR", "2026-10-10")
        add("llm", "sarvam", "sarvam-105b", unit, price, "INR", "2026-10-10")
    for model, output in (("gemini-3.8-flash-lite-tts", "6"), ("gemini-3.8-flash-tts", "9")):
        add("tts", "gemini", model, "input_tokens_million", "0.5", "USD", "2026-10-22", "2027-01-01")
        add("tts", "gemini", model, "output_audio_tokens_million", output, "USD", "2026-10-22", "2027-01-01")
        add("tts", "gemini", model, "input_tokens_million", "1", "USD", "2027-01-01")
        add("tts", "gemini", model, "output_audio_tokens_million", str(int(output) * 2), "USD", "2027-01-01")
    return rates


def validate_provider_rates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 100:
        raise ProviderCostError("invalid_rates", "Provide between 1 and 100 supplier tariffs.")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    try:
        for row in value:
            if not isinstance(row, dict) or set(row) != _FIELDS:
                raise ValueError("Supplier tariff fields do not match the schema.")
            if any(not isinstance(row[key], str) or not _ID.fullmatch(row[key]) for key in ("id", "provider", "model")):
                raise ValueError("Use stable supplier, model and tariff identifiers.")
            if row["id"] in ids:
                raise ValueError("Tariff identifiers must be unique.")
            ids.add(row["id"])
            stage = row["stage"]
            if stage not in UNITS or row["unit"] not in UNITS[stage]:
                raise ValueError("The unit is invalid for this stage.")
            if row["currency"] not in {"INR", "USD"}:
                raise ValueError("Supplier currency must be INR or USD.")
            allowed = ((stage in {"stt", "llm"} and row["provider"] == "sarvam")
                       or (stage == "tts" and row["provider"] in {"sarvam", "gemini", "cartesia", "gnani"}))
            if not allowed or "live" in row["model"].lower():
                raise ValueError("This tariff editor supports composed suppliers only.")
            price = _decimal(row["price"])
            if price > Decimal("1000000000") or price.as_tuple().exponent < -9:
                raise ValueError("Supplier prices support at most nine decimal places.")
            start = date.fromisoformat(row["effectiveFrom"])
            end = date.fromisoformat(row["effectiveUntil"]) if row["effectiveUntil"] else None
            if end is not None and end <= start:
                raise ValueError("The end date must follow the start date (exclusive).")
            url = urlsplit(row["sourceUrl"])
            if len(row["sourceUrl"]) > 500 or url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("The tariff citation must be an HTTPS URL without credentials.")
            cleaned = {**row, "price": _text(price), "effectiveFrom": start.isoformat(), "effectiveUntil": end.isoformat() if end else None}
            key = tuple(row[k] for k in ("stage", "provider", "model", "unit"))
            for previous in result:
                if tuple(previous[k] for k in ("stage", "provider", "model", "unit")) == key:
                    if (previous["effectiveUntil"] or "9999-12-31") > cleaned["effectiveFrom"] and (cleaned["effectiveUntil"] or "9999-12-31") > previous["effectiveFrom"]:
                        raise ValueError("Effective date ranges for the same model and unit cannot overlap.")
            result.append(cleaned)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ProviderCostError("invalid_rates", str(exc)) from exc
    return result


async def load_provider_costs() -> dict[str, Any]:
    factory = get_session_factory()
    if factory is None:
        raise ProviderCostError("durable_store_unavailable", "Supplier costs require the database configuration store.", 503)
    async with factory() as db:
        result = await db.execute(select(ConfigVersion).where(
            ConfigVersion.resource_type == RESOURCE_TYPE, ConfigVersion.resource_id == RESOURCE_ID,
        ).order_by(desc(ConfigVersion.version)).limit(1))
        row = result.scalar_one_or_none()
    stored_rates = copy.deepcopy(row.payload["rates"]) if row else []
    defaults = default_provider_rates()
    if stored_rates:
        existing_ids = {r["id"] for r in stored_rates}
        for d in defaults:
            if d["id"] not in existing_ids:
                stored_rates.append(copy.deepcopy(d))
    else:
        stored_rates = defaults
    view = {
        "schemaVersion": 1, "version": int(row.version) if row else 0, "configured": row is not None,
        "updatedAt": row.created_at.isoformat() if row else None,
        "reason": (row.payload.get("reason") or "") if row else "Published supplier tariff suggestions; save to configure.",
        "editableTiers": ["low", "medium"], "premiumReadOnly": True,
        "rates": stored_rates,
    }
    from server.services.dev_runtime import effective_app_environment
    from server.services.saas.voice_stack_profiles import load_profile_records

    profiles = await load_profile_records(effective_app_environment(), ("low", "medium"))
    view["stacks"] = provider_stack_views(view, profiles)
    return view


def provider_stack_views(config: dict, profiles: dict) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).date().isoformat()
    views = []
    for tier, label in (("low", "Low"), ("medium", "Standard")):
        profile = (profiles.get(tier) or {}).get("profile") or {}
        tts = [{"provider": model.get("provider"), "model": model.get("model")}
               for engine in profile.get("engines", []) for model in engine.get("models", [])]
        stages = {"stt": {"provider": (profile.get("stt") or {}).get("provider"), "model": (profile.get("stt") or {}).get("model")},
                  "llm": {"provider": (profile.get("llm") or {}).get("provider"), "model": (profile.get("llm") or {}).get("modelId")},
                  "tts": tts[0] if tts else {"provider": None, "model": None}}
        missing, selected = [], []
        for stage, options in (("stt", [stages["stt"]]), ("llm", [stages["llm"]]), ("tts", tts or [stages["tts"]])):
            for option in options:
                units = UNITS[stage] if stage != "tts" else ({"input_tokens_million", "output_audio_tokens_million"} if option.get("provider") == "gemini" else {"characters_1000"})
                for unit in sorted(units):
                    rate = _rate(config["rates"], stage, option, unit, today)
                    if rate:
                        selected.append(rate["id"])
                    else:
                        missing.append(f"{stage}:{option.get('model') or 'unconfigured'}:{unit}")
        if not config["configured"]:
            missing.insert(0, "supplier_tariffs_not_saved")
        views.append({"tier": tier, "label": label, "stages": stages, "ttsAlternatives": tts,
                      "rateIds": list(dict.fromkeys(selected)), "costStatus": "missing_rates" if missing else "ready", "missingRates": missing})
    return views


async def save_provider_costs(*, expected_version: int, rates: Any, actor: str, reason: str) -> dict[str, Any]:
    validated = validate_provider_rates(rates)
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
        raise ProviderCostError("invalid_version", "expectedVersion must be a nonnegative integer.")
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 500:
        raise ProviderCostError("reason_required", "Provide a reason between 8 and 500 characters.")
    factory = get_session_factory()
    if factory is None:
        raise ProviderCostError("durable_store_unavailable", "Supplier costs require the database configuration store.", 503)
    async with factory() as db:
        if db.get_bind().dialect.name == "postgresql":
            await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"{RESOURCE_TYPE}:{RESOURCE_ID}"))))
        result = await db.execute(select(ConfigVersion).where(
            ConfigVersion.resource_type == RESOURCE_TYPE, ConfigVersion.resource_id == RESOURCE_ID,
        ).order_by(desc(ConfigVersion.version)).limit(1).with_for_update())
        previous = result.scalar_one_or_none()
        version = int(previous.version) if previous else 0
        if version != expected_version:
            raise ProviderCostError("version_conflict", "Supplier costs changed in another session. Reload before saving.", 409)
        db.add(ConfigVersion(id=uuid.uuid4(), resource_type=RESOURCE_TYPE, resource_id=RESOURCE_ID,
                             version=version + 1, created_at=datetime.now(timezone.utc),
                             payload={"rates": validated, "actor": actor, "reason": reason.strip()}))
        await db.commit()
    return await load_provider_costs()


async def seed_default_provider_costs(*, actor: str, reason: str) -> dict[str, Any]:
    current = await load_provider_costs()
    if current["configured"]:
        return current
    try:
        return await save_provider_costs(expected_version=0, rates=current["rates"], actor=actor, reason=reason)
    except ProviderCostError as exc:
        if exc.code != "version_conflict":
            raise
        return await load_provider_costs()


def _rate(rates: list[dict], stage: str, selection: dict, unit: str, as_of: str) -> dict | None:
    matched = [r for r in rates if r["stage"] == stage and r["provider"] == selection.get("provider")
               and r["model"] == selection.get("model") and r["unit"] == unit
               and r["effectiveFrom"] <= as_of and (r["effectiveUntil"] is None or as_of < r["effectiveUntil"])]
    if not matched:
        defaults = default_provider_rates()
        matched = [r for r in defaults if r["stage"] == stage and r["provider"] == selection.get("provider")
                   and r["model"] == selection.get("model") and r["unit"] == unit
                   and r["effectiveFrom"] <= as_of and (r["effectiveUntil"] is None or as_of < r["effectiveUntil"])]
    return matched[0] if len(matched) >= 1 else None


def build_cost_snapshot(config: dict, stack: dict, *, fx_rate_inr: Any, captured_at: datetime | None = None) -> dict[str, Any]:
    at = captured_at or datetime.now(timezone.utc)
    fx = _decimal(fx_rate_inr)
    if fx == 0:
        raise ProviderCostError("invalid_fx", "A positive pinned INR per USD exchange rate is required.")
    return {"schemaVersion": 1, "version": config["version"], "configured": config["configured"],
            "capturedAt": at.astimezone(timezone.utc).isoformat(), "fxRateInr": _text(fx),
            "tier": stack.get("tier"), "stages": {key: {name: (stack.get(key) or {}).get(name) for name in ("provider", "model")} for key in UNITS},
            "rates": copy.deepcopy(config["rates"]) if config["configured"] else []}


async def snapshot_provider_costs(stack: dict, *, fx_rate_inr: Any) -> dict[str, Any]:
    try:
        config = await load_provider_costs()
    except ProviderCostError as exc:
        if exc.status_code != 503:
            raise
        config = {"version": 0, "configured": False, "rates": []}
    return build_cost_snapshot(config, stack, fx_rate_inr=fx_rate_inr)


def composed_llm_usage(usage: dict[str, Any]) -> dict[str, int]:
    """Project provider telemetry onto the native counters the ledger accepts.

    Adapter telemetry also contains totals/cache-write diagnostics. Those must
    not reach the strict stage recorder or prevent an opening from playing.
    """
    return {key: value for key, value in usage.items()
            if key in LLM_USAGE_COUNTERS and isinstance(value, int) and not isinstance(value, bool)}


def record_composed_stage_usage(call_id: str, stage: str, values: dict[str, Any], *, accumulate: bool = True) -> None:
    """Persist native counters off the audio hot path; never modifies Premium."""
    if not call_id or stage not in UNITS or not isinstance(values, dict):
        return
    allowed = {"stt": {"audio_seconds"}, "llm": LLM_USAGE_COUNTERS,
               "tts": {"input_characters"}}
    allowed_stage = allowed.get(stage, set())
    filtered = {key: value for key, value in values.items() if key in allowed_stage}
    if not filtered:
        return
    validated: dict[str, Decimal] = {}
    for key, value in filtered.items():
        try:
            num = _decimal(value)
            if key != "audio_seconds" and num != num.to_integral_value():
                continue
            validated[key] = num
        except (ValueError, TypeError, InvalidOperation):
            continue
    if not validated:
        return
    from server.call.call_ledger import call_ledger

    with _USAGE_LOCK:
        meta = call_ledger.read_meta(call_id)
        if meta.get("pipeline") != "composed_voice":
            return
        stages = meta.get("stage_usage") if isinstance(meta.get("stage_usage"), dict) else {}
        current = stages.get(stage) if isinstance(stages.get(stage), dict) else {}
        for key, number in validated.items():
            total = number + (_decimal(current.get(key, 0)) if accumulate else Decimal(0))
            current[key] = float(total) if key == "audio_seconds" else int(total)
        stages[stage] = current
        meta["stage_usage"] = stages
        call_ledger.write_meta(call_id, meta)
        _restamp_ended_composed(call_id, meta)


def _restamp_ended_composed(call_id: str, meta: dict) -> None:
    if meta.get("pipeline") == "composed_voice" and meta.get("ended_at"):
        from server.call.call_ledger import call_ledger

        duration = meta.get("duration_sec", (meta.get("usage") or {}).get("duration_sec"))
        call_ledger.stamp_ended_usage(call_id, reason=str(meta.get("end_reason") or "user_stop"), duration_sec=duration)


def merge_composed_tts_usage(call_id: str, counters: dict[str, Any], *, prewarm: bool = False) -> None:
    """Serialize TTS counters with late STT/LLM writes and refresh ended analytics."""
    from server.call.call_ledger import call_ledger

    prefix = "prewarm_" if prewarm else ""
    with _USAGE_LOCK:
        meta = call_ledger.read_meta(call_id)
        # The caller has already verified its composed session. Older ledger
        # fixtures have no pipeline marker; an explicit Premium marker is denied.
        if meta.get("pipeline") not in (None, "", "composed_voice"):
            return
        stages = meta.get("stage_usage") if isinstance(meta.get("stage_usage"), dict) else {}
        current = stages.get("tts") if isinstance(stages.get("tts"), dict) else {}
        native_key = f"{prefix}native_usage"
        native = dict(current.get(native_key) or {})
        for key, value in (counters.get("native_usage") or {}).items():
            quantity = _decimal(value)
            if quantity != quantity.to_integral_value():
                raise ValueError("Native token counters must be integers.")
            native[key] = int(_decimal(native.get(key, 0)) + quantity)
        for key in ("input_characters", "output_audio_seconds", "output_audio_samples"):
            name = f"{prefix}{key}"
            quantity = _decimal(current.get(name, 0)) + _decimal(counters.get(key, 0))
            current[name] = round(float(quantity), 6) if key == "output_audio_seconds" else int(quantity)
        current[native_key] = native
        stages["tts"] = current
        meta["stage_usage"] = stages
        call_ledger.write_meta(call_id, meta)
        _restamp_ended_composed(call_id, meta)


def price_composed_usage(snapshot: Any, stage_usage: Any) -> dict[str, Any]:
    """Price only measured quantities. Missing counters never become a zero bill."""
    if not isinstance(snapshot, dict) or not snapshot.get("configured"):
        return {"status": "incomplete", "missing": ["provider_cost_snapshot"], "stages": {}, "totalUsd": None, "totalInr": None}
    stages: dict[str, Any] = {}
    missing: list[str] = []
    fx = _decimal(snapshot["fxRateInr"])
    if fx == 0:
        raise ValueError("Pinned exchange rate must be positive.")
    as_of = snapshot["capturedAt"][:10]
    measured = stage_usage if isinstance(stage_usage, dict) else {}
    for stage in UNITS:
        selection = snapshot["stages"].get(stage) or {}
        data = measured.get(stage) if isinstance(measured.get(stage), dict) else {}
        native = data.get("native_usage") if isinstance(data.get("native_usage"), dict) else data
        if stage == "tts":
            native = dict(native)
            for key, value in (data.get("prewarm_native_usage") or {}).items():
                native[key] = _text(_decimal(native.get(key, 0)) + _decimal(value))
        quantities: dict[str, Decimal] = {}
        errors: list[str] = []
        try:
            if stage == "stt":
                quantities["audio_minute"] = _decimal(data.get("audio_seconds")) / 60
            elif stage == "llm":
                input_tokens = _decimal(native.get("input_tokens"))
                cached = _decimal(native.get("cached_tokens", 0))
                if cached > input_tokens:
                    raise ValueError("Cached tokens exceed input tokens.")
                quantities = {"input_tokens_million": (input_tokens - cached) / 1_000_000,
                              "cached_input_tokens_million": cached / 1_000_000,
                              "output_tokens_million": _decimal(native.get("output_tokens")) / 1_000_000}
            elif selection.get("provider") in {"sarvam", "cartesia", "gnani"}:
                chars = data.get("input_characters", data.get("prewarm_input_characters"))
                if "input_characters" in data:
                    chars = _decimal(chars) + _decimal(data.get("prewarm_input_characters", 0))
                quantities["characters_1000"] = _decimal(chars) / 1000
            elif selection.get("provider") == "gemini":
                quantities = {"input_tokens_million": _decimal(native.get("input_tokens")) / 1_000_000,
                              "output_audio_tokens_million": _decimal(native.get("output_audio_tokens")) / 1_000_000}
            else:
                errors.append(f"{stage}.unsupported_supplier")
        except ValueError:
            errors.append(f"{stage}.measured_usage")
        usd, inr = Decimal(0), Decimal(0)
        components = []
        for unit, quantity in quantities.items():
            rate = _rate(snapshot["rates"], stage, selection, unit, as_of)
            if rate is None:
                errors.append(f"{stage}.{unit}.rate")
                continue
            native_cost = quantity * _decimal(rate["price"])
            component_usd = native_cost if rate["currency"] == "USD" else native_cost / fx
            component_inr = native_cost if rate["currency"] == "INR" else native_cost * fx
            usd += component_usd
            inr += component_inr
            components.append({"rateId": rate["id"], "unit": unit, "quantity": _text(quantity), "currency": rate["currency"],
                               "nativeCost": _text(native_cost), "costUsd": _text(component_usd), "costInr": _text(component_inr)})
        missing.extend(errors)
        stages[stage] = {"status": "incomplete" if errors else "ready", "components": components,
                         "costUsd": None if errors else _text(usd), "costInr": None if errors else _text(inr)}
    return {"status": "incomplete" if missing else "ready", "version": snapshot["version"], "missing": missing, "stages": stages,
            "totalUsd": None if missing else _text(sum((_decimal(s["costUsd"]) for s in stages.values()), Decimal(0))),
            "totalInr": None if missing else _text(sum((_decimal(s["costInr"]) for s in stages.values()), Decimal(0)))}
