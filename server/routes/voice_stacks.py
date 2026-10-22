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
    records = await load_profile_records(environment, COMPOSED_TIERS)
    rates = await _load_rates_without_fallback()
    profiles = [
        public_catalog_profile(tier, records.get(tier), rates)
        for tier in COMPOSED_TIERS
    ]
    for profile in profiles:
        for engine in profile["engines"]:
            for model in engine["models"]:
                model["voices"] = [
                    voice for voice in model["voices"]
                    if normalized_language in voice.get("languages", [])
                ]
            engine["models"] = [model for model in engine["models"] if model["voices"]]
        profile["engines"] = [engine for engine in profile["engines"] if engine["models"]]
        if not profile["engines"] and profile["ready"]:
            profile["ready"] = False
            profile["blockers"].append({"code": "language_voice_unavailable", "message": "No approved voice is available for this language."})

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

    premium_profile = {
        "tier": "premium",
        "label": "Flagship Live",
        "ready": bool(premium_rate and premium_rate.get("complete")),
        "profileRevision": 1,
        "retailRate": premium_rate,
        "engines": [],
        "blockers": [] if (premium_rate and premium_rate.get("complete")) else [
            {"code": "tier_native_rate_missing", "message": "An approved native retail rate for Flagship Live has not been configured."}
        ],
    }
    profiles.append(premium_profile)
    return {"language": normalized_language, "profiles": profiles}
