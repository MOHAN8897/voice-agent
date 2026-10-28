"""Tenant-safe catalog for explicitly enabled composed PSTN voice stacks."""
from __future__ import annotations

import asyncio
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from server.auth.subscriber_dependencies import require_subscriber_jwt_if_enabled
from server.config.constants import normalize_supported_language
from server.services.saas.tenant_guard import SubscriberPrincipal
from server.services.saas.voice_stack_profiles import (
    COMPOSED_TIERS,
    _load_rates_without_fallback,
    _native_tier_retail_rate,
    load_profile_records,
    ordered_stack_tier_ids,
    public_catalog_profile,
)

router = APIRouter()


@router.get("/api/voice-stacks/catalog")
async def voice_stack_catalog(
    language: str = Query(default="en-US", min_length=2, max_length=16),
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
    # FastAPI injects this; the default keeps direct route calls in tests working.
    background: BackgroundTasks = None,
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
    records, rates = await asyncio.gather(
        load_profile_records(environment, None), _load_rates_without_fallback(),
    )

    import copy
    from server.services.saas.voice_stack_defaults import recommended_composed_profile

    # Premium is appended below so an older record can borrow the recommended profile.
    ordered_tiers = [tier for tier in ordered_stack_tier_ids(records) if tier != "premium"]

    active_ordered_tiers = [
        tier for tier in ordered_tiers
        if bool((records.get(tier) or {}).get("profile", {}).get("enabled", False))
    ]

    profiles = [
        public_catalog_profile(tier, records.get(tier), rates)
        for tier in active_ordered_tiers
    ]

    premium_record = records.get("premium")
    prem_p = (premium_record or {}).get("profile") if premium_record else None
    prem_enabled = bool(prem_p.get("enabled", False)) if isinstance(prem_p, dict) else False

    if prem_enabled:
        if premium_record and isinstance(premium_record.get("profile"), dict) and premium_record["profile"].get("engines"):
            premium_profile = public_catalog_profile("premium", premium_record, rates)
        else:
            prem_rec = copy.deepcopy(premium_record) if premium_record else {"profile": {}}
            default_prem = recommended_composed_profile("premium", allow_premium=True)
            if not prem_rec.get("profile"):
                prem_rec["profile"] = default_prem
            else:
                for k, v in default_prem.items():
                    if k not in prem_rec["profile"] or not prem_rec["profile"][k]:
                        prem_rec["profile"][k] = v
            premium_profile = public_catalog_profile("premium", prem_rec, rates)
        profiles.append(premium_profile)

    warm_targets: list[tuple[str, str, str]] = []
    for profile in profiles:
        # Counts describe the complete approved inventory, before the active
        # language filter. Tenants can distinguish a short native roster from
        # a truncated catalogue without seeing internal provider identifiers.
        all_voices = [voice for engine in profile.get("engines", [])
            for model in engine.get("models", []) for voice in model.get("voices", [])]
        language_counts: dict[str, int] = {}
        for voice in all_voices:
            for code in set(voice.get("languages") or []):
                language_counts[code] = language_counts.get(code, 0) + 1
        profile["voiceInventory"] = {"totalVoices": len(all_voices), "voicesByLanguage": language_counts}
        for engine in profile.get("engines", []):
            for model in engine.get("models", []):
                model["voices"] = [
                    voice for voice in model.get("voices", [])
                    if normalized_language in voice.get("languages", [])
                ]
                for voice in model["voices"]:
                    if str(voice.get("id") or "").startswith("voc_"):
                        voice["previewUrl"] = "/api/telephony/voice-preview/catalog?" + urlencode(
                            {"voiceId": voice["id"], "language": normalized_language}
                        )
                        warm_targets.append(("catalog", voice["id"], normalized_language))
            engine["models"] = [model for model in engine.get("models", []) if model.get("voices")]
        profile["engines"] = [engine for engine in profile.get("engines", []) if engine.get("models")]
        if not profile["engines"] and profile.get("ready"):
            profile["ready"] = False
            if not any(b.get("code") == "language_voice_unavailable" for b in profile.get("blockers", [])):
                profile["blockers"].append({"code": "language_voice_unavailable", "message": "No approved voice is available for this language."})
    if background is not None and warm_targets:
        from server.services.saas.voice_preview import schedule_preview_warm

        background.add_task(schedule_preview_warm, warm_targets)
    active_profiles = [
        p for p in profiles
        if p.get("ready") is True
        and not any(b.get("code") == "profile_not_available" for b in p.get("blockers", []))
    ]

    return {"language": normalized_language, "profiles": active_profiles}

