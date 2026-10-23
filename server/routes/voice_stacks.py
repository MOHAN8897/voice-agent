"""Tenant-safe catalog for explicitly enabled composed PSTN voice stacks."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from server.auth.subscriber_dependencies import require_subscriber_jwt_if_enabled
from server.config.constants import normalize_supported_language
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.services.saas.voice_stack_profiles import (
    COMPOSED_TIERS,
    _load_rates_without_fallback,
    _native_tier_retail_rate,
    load_profile_records,
    public_catalog_profile,
)

router = APIRouter()


@router.get("/api/voice-stacks/catalog")
async def voice_stack_catalog(
    language: str = Query(default="en-US", min_length=2, max_length=16),
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    """Return only enabled choices mapped to opaque public aliases and safe labels."""
    # Catalog data is shared platform configuration; the explicit auth dependency
    # still enforces the app's subscriber or portal-session policy.
    del principal
    try:
        normalized_language = normalize_supported_language(language)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"error": {"code": "unsupported_language", "message": "Choose a supported agent language."}}) from exc

    from server.services.dev_runtime import effective_app_environment

    environment = effective_app_environment()
    records = await load_profile_records(environment, None)
    rates = await _load_rates_without_fallback()

    standard_tiers = ["low", "medium"]
    custom_tiers = [t for t in sorted(records.keys()) if t not in ("low", "medium", "premium")]
    ordered_tiers = [t for t in standard_tiers if t in records or t in ("low", "medium")] + custom_tiers

    profiles = [
        public_catalog_profile(tier, records.get(tier), rates)
        for tier in ordered_tiers
    ]

    premium_rate = _native_tier_retail_rate(rates, "premium")
    if not premium_rate and rates:
        pstn_usd = rates.get("pstn_rate_usd_micros_per_min")
        pstn_inr = rates.get("pstn_rate_inr_paise_per_min")
        ver = rates.get("version") or 1
        if isinstance(pstn_usd, int) and pstn_usd > 0 and isinstance(pstn_inr, int) and pstn_inr > 0:
            premium_rate = {
                "usdMicrosPerMin": pstn_usd,
                "inrPaisePerMin": pstn_inr,
                "version": int(ver),
                "fxRateInr": float(rates.get("fx_rate_inr") or 95.64),
                "complete": True,
            }

    premium_record = records.get("premium")
    if premium_record and isinstance(premium_record.get("profile"), dict) and premium_record["profile"].get("engines"):
        premium_profile = public_catalog_profile("premium", premium_record, rates)
    else:
        prem_p = (premium_record or {}).get("profile") if premium_record else None
        prem_enabled = prem_p.get("enabled", True) if isinstance(prem_p, dict) else True
        prem_label = (prem_p.get("label") if isinstance(prem_p, dict) else None) or "Flagship Live"
        ready_flag = bool(prem_enabled and premium_rate and premium_rate.get("complete"))
        blockers = []
        if not (premium_rate and premium_rate.get("complete")):
            blockers.append({"code": "tier_native_rate_missing", "message": "An approved native retail rate for Flagship Live has not been configured."})
        if not prem_enabled:
            blockers.append({"code": "profile_not_available", "message": "This voice option is not currently available."})
        premium_profile = {
            "tier": "premium",
            "label": prem_label,
            "ready": ready_flag,
            "profileRevision": int((premium_record or {}).get("revision") or 1),
            "retailRate": premium_rate,
            "engines": [],
            "blockers": blockers,
        }
    profiles.append(premium_profile)

    for profile in profiles:
        for engine in profile.get("engines", []):
            for model in engine.get("models", []):
                model["voices"] = [
                    voice for voice in model.get("voices", [])
                    if normalized_language in voice.get("languages", [])
                ]
            engine["models"] = [model for model in engine.get("models", []) if model.get("voices")]
        profile["engines"] = [engine for engine in profile.get("engines", []) if engine.get("models")]
        if not profile["engines"] and profile.get("ready") and profile.get("tier") != "premium":
            profile["ready"] = False
            profile["blockers"].append({"code": "language_voice_unavailable", "message": "No approved voice is available for this language."})
    active_profiles = [
        p for p in profiles
        if p.get("ready") is True
        and not any(b.get("code") == "profile_not_available" for b in p.get("blockers", []))
    ]

    return {"language": normalized_language, "profiles": active_profiles}

