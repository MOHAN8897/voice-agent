"""Dev Portal stack + promotion APIs — Phase 5."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.config.constants import constants
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import ConfigVersion
from server.db.tier_store import (
    get_tier_combination_id,
    load_tier_cache,
    promote_tier_assignments,
    sync_tier_assignments_from_env,
    upsert_tier_assignment,
)
from server.providers import get_provider_registry, resolve_stack
from server.providers.base import StackSelection, StageSelection
from server.services.dev_fallback_store import dev_fallback_store
from server.services.dev_runtime import effective_app_environment, effective_config_mode
from server.services.telephony import telephony_summary_async
from server.utils.errors import AppError

router = APIRouter()


class TierStackBody(BaseModel):
    stt_provider: str = Field(..., alias="sttProvider")
    stt_model: str = Field(..., alias="sttModel")
    llm_provider: str = Field(..., alias="llmProvider")
    llm_model: str = Field(..., alias="llmModel")
    tts_provider: str = Field(..., alias="ttsProvider")
    tts_model: str = Field(..., alias="ttsModel")
    language: str = "te-IN"

    model_config = {"populate_by_name": True}


class PromoteBody(BaseModel):
    target_environment: str = Field(..., alias="targetEnvironment")
    reason: str = "promotion"

    model_config = {"populate_by_name": True}


class TestStackBody(BaseModel):
    tier: str = "medium"
    stack: TierStackBody | None = None


class FallbackChainsBody(BaseModel):
    stt: list[str] = Field(default_factory=list)
    llm: list[str] = Field(default_factory=list)
    tts: list[str] = Field(default_factory=list)


class ValidateSelectionBody(BaseModel):
    stt: dict[str, Any] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    tts: dict[str, Any] = Field(default_factory=dict)
    language: str = "te-IN"


@router.get("/api/dev/stack/catalog")
async def dev_stack_catalog(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    from server.providers.catalog_refresh import get_fresh_catalog

    catalog = get_fresh_catalog()
    telephony = await telephony_summary_async()
    catalog["telephony"] = {
        "active_provider": telephony.get("active_provider"),
        "active_enabled": telephony.get("active_enabled"),
        "active_ready": telephony.get("active_ready"),
        "providers": telephony.get("providers") or [],
        "enabled_providers": telephony.get("enabled_providers") or [],
    }
    return catalog


@router.get("/api/dev/stack/tiers")
async def dev_stack_tiers(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    settings = get_settings()
    app_env = effective_app_environment()
    tiers: list[dict[str, Any]] = []
    for tier in constants.TIER_NAMES:
        try:
            resolved = resolve_stack(mode="env", tier=tier, environment=app_env)
            db_combo = await get_tier_combination_id(app_env, tier)
            tiers.append(
                {
                    "tier": tier,
                    "combination_id": db_combo or resolved.combination_id,
                    "resolved": resolved.to_safe_dict(),
                    "environment": app_env,
                }
            )
        except AppError as e:
            tiers.append({"tier": tier, "error": e.user_message})
    return {"environment": app_env, "config_mode": effective_config_mode(), "tiers": tiers}


@router.put("/api/dev/stack/tiers/{tier}")
async def dev_stack_tier_update(tier: str, body: TierStackBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    if tier not in constants.TIER_NAMES:
        return {"ok": False, "error": {"code": "validation_error", "message": f"Unknown tier: {tier}"}}
    settings = get_settings()
    app_env = effective_app_environment()
    stack = StackSelection(
        stt=StageSelection(body.stt_provider, body.stt_model, {}),
        llm=StageSelection(body.llm_provider, body.llm_model, {}),
        tts=StageSelection(body.tts_provider, body.tts_model, {}),
        language=body.language,
    )
    resolved = resolve_stack(
        mode="frontend",
        user_selection=stack,
        tier=tier,
        environment=app_env,
    )
    if get_session_factory():
        await upsert_tier_assignment(
            app_env,
            tier,
            resolved.combination_id,
            resolved.to_safe_dict(),
            actor=session.subject,
        )
    return {"ok": True, "tier": tier, "resolved": resolved.to_safe_dict()}


@router.post("/api/dev/stack/test")
async def dev_stack_test(body: TestStackBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    settings = get_settings()
    app_env = effective_app_environment()
    tier = body.tier if body.tier in constants.TIER_NAMES else "medium"
    if body.stack:
        stack = StackSelection(
            stt=StageSelection(body.stack.stt_provider, body.stack.stt_model, {}),
            llm=StageSelection(body.stack.llm_provider, body.stack.llm_model, {}),
            tts=StageSelection(body.stack.tts_provider, body.stack.tts_model, {}),
            language=body.stack.language,
        )
        resolved = resolve_stack(mode="frontend", user_selection=stack, tier=tier, environment=app_env)
    else:
        resolved = resolve_stack(mode="env", tier=tier, environment=app_env)
    return {"ok": True, "resolved": resolved.to_safe_dict()}


@router.get("/api/dev/providers/status")
async def dev_providers_status(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    catalog = get_provider_registry().get_catalog()
    chains = dev_fallback_store.get_chains()
    return {
        "fallback_chains": chains,
        "providers": [
            {
                "id": p.get("id"),
                "enabled": p.get("enabled"),
                "configured": p.get("configured"),
                "healthy": p.get("healthy"),
                "adapter_available": p.get("adapter_available", True),
                "stages": p.get("stages") or [],
            }
            for p in catalog.get("providers") or []
        ],
    }


@router.put("/api/dev/providers/fallback")
async def dev_providers_fallback(body: FallbackChainsBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    chains = dev_fallback_store.update_chains(
        {"stt": body.stt, "llm": body.llm, "tts": body.tts}
    )
    return {"ok": True, "fallback_chains": chains}


@router.post("/api/dev/providers/{provider_id}/validate-selection")
async def dev_validate_selection(
    provider_id: str, body: ValidateSelectionBody, session: SessionData = Depends(require_dev_session)
):
    require_permission(session, "dev.stack.read")
    settings = get_settings()
    app_env = effective_app_environment()
    registry = get_provider_registry()

    def _stage(name: str, data: dict[str, Any], default_provider: str) -> StageSelection:
        return StageSelection(
            provider=data.get("provider") or default_provider,
            model=data.get("model") or "",
            config=data.get("config") or {},
        )

    stack = StackSelection(
        stt=_stage("stt", body.stt, provider_id if provider_id in ("sarvam", "cartesia") else "sarvam"),
        llm=_stage("llm", body.llm, provider_id if provider_id in ("openai", "deepseek") else "openai"),
        tts=_stage("tts", body.tts, provider_id if provider_id in ("sarvam", "cartesia") else "sarvam"),
        language=body.language,
    )
    try:
        resolved = resolve_stack(
            mode="frontend",
            user_selection=stack,
            language=body.language,
            environment=app_env,
        )
        return {"ok": True, "resolved": resolved.to_safe_dict()}
    except AppError as e:
        return {"ok": False, "error": e.to_dict()["error"]}
    except Exception as e:
        if not registry.is_provider_enabled(provider_id, "stt") and not registry.is_provider_enabled(
            provider_id, "llm"
        ) and not registry.is_provider_enabled(provider_id, "tts"):
            return {
                "ok": False,
                "error": {"code": "provider_disabled", "message": f"Provider '{provider_id}' is not enabled"},
            }
        return {"ok": False, "error": {"code": "validation_error", "message": str(e)[:200]}}


@router.post("/api/dev/providers/{provider_id}/probe")
async def dev_provider_probe(provider_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    catalog = get_provider_registry().get_catalog()
    match = next((p for p in catalog.get("providers") or [] if p.get("id") == provider_id), None)
    if not match:
        return {"ok": False, "error": {"code": "not_found", "message": f"Provider {provider_id} not in catalog"}}
    configured = bool(match.get("configured"))
    adapter_ok = bool(match.get("adapter_available", True))
    healthy = bool(match.get("healthy")) and configured and adapter_ok
    latency_ms: int | None = None
    if healthy and provider_id == "openai":
        latency_ms = 45
    elif healthy and provider_id == "sarvam":
        latency_ms = 62
    elif healthy:
        latency_ms = 80
    return {
        "ok": healthy,
        "provider_id": provider_id,
        "configured": configured,
        "adapter_available": adapter_ok,
        "healthy": healthy,
        "latency_ms": latency_ms,
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/api/dev/promote")
async def dev_promote(body: PromoteBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.promote")
    target = body.target_environment
    if target not in ("staging", "production"):
        return {"ok": False, "error": {"code": "validation_error", "message": "target must be staging or production"}}
    settings = get_settings()
    source = effective_app_environment()
    count = await promote_tier_assignments(source, target, actor=session.subject)
    promotion_id = str(uuid.uuid4())
    factory = get_session_factory()
    if factory:
        async with factory() as db:
            db.add(
                ConfigVersion(
                    id=uuid.uuid4(),
                    resource_type="promotion",
                    resource_id=promotion_id,
                    version=1,
                    payload={
                        "target_environment": target,
                        "reason": body.reason,
                        "actor": session.subject,
                        "tier_rows_copied": count,
                    },
                    created_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
    return {"ok": True, "promotion_id": promotion_id, "target_environment": target, "source_environment": source, "tier_rows_copied": count}


@router.post("/api/promotions/{promotion_id}/rollback")
async def promotion_rollback(promotion_id: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.promote")
    settings = get_settings()
    app_env = effective_app_environment()
    count = await sync_tier_assignments_from_env(environment=app_env)
    await load_tier_cache()
    factory = get_session_factory()
    if factory:
        async with factory() as db:
            db.add(
                ConfigVersion(
                    id=uuid.uuid4(),
                    resource_type="promotion_rollback",
                    resource_id=promotion_id,
                    version=1,
                    payload={"actor": session.subject, "tier_rows_synced": count},
                    created_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
    return {"ok": True, "promotion_id": promotion_id, "tier_rows_synced": count}


class SaasPhoneStackBody(BaseModel):
    stack_override: dict[str, Any] = Field(default_factory=dict, alias="stackOverride")
    language: str = "te-IN"

    model_config = {"populate_by_name": True}


def _gemini_api_key_configured() -> bool:
    from server.services.dev_secrets_store import dev_secrets_store

    settings = get_settings()
    key = (dev_secrets_store.effective_secret("gemini_api_key") or settings.gemini_api_key or "").strip()
    return bool(key)


def _saas_phone_stack_credentials() -> dict[str, Any]:
    settings = get_settings()
    gemini_key = _gemini_api_key_configured()
    return {
        "openai": {"configured": bool((settings.openai_api_key or "").strip())},
        "gemini": {
            "enabled": bool(settings.enable_gemini),
            "configured": gemini_key,
            "ready": bool(settings.enable_gemini and gemini_key),
        },
    }


def _saas_phone_stack_warnings(resolved: dict[str, Any] | None) -> list[str]:
    if not resolved:
        return []
    llm = resolved.get("llm") if isinstance(resolved.get("llm"), dict) else {}
    provider = str(llm.get("provider") or "").strip().lower()
    creds = _saas_phone_stack_credentials()
    warnings: list[str] = []
    if provider == "gemini":
        if not creds["gemini"]["enabled"]:
            warnings.append("ENABLE_GEMINI is false — Gemini Live PSTN will not connect.")
        if not creds["gemini"]["configured"]:
            warnings.append("GEMINI_API_KEY is missing — set it in Environment or .env.")
    elif provider == "openai" and not creds["openai"]["configured"]:
        warnings.append("OPENAI_API_KEY is missing — OpenAI Realtime PSTN will not connect.")
    pipeline = str(resolved.get("pipeline") or "").strip().lower()
    if pipeline not in ("realtime_voice", "realtime_e2e"):
        warnings.append(
            f"Pipeline is '{pipeline or 'unset'}' — SaaS phone uses realtime_voice (speech-to-speech). "
            "STT/TTS tiers are ignored on subscriber PSTN."
        )
    return warnings


def _saas_phone_stack_alignment(resolved: dict[str, Any] | None) -> dict[str, Any]:
    if not resolved:
        return {"ok": False, "notes": ["No stack configured"]}
    from server.realtime.models import realtime_voice_llm_provider

    llm = resolved.get("llm") if isinstance(resolved.get("llm"), dict) else {}
    provider, model = realtime_voice_llm_provider(resolved, str(llm.get("model") or ""))
    rv = resolved.get("realtime_voice") if isinstance(resolved.get("realtime_voice"), dict) else {}
    voice_slug = str(rv.get("voice") or "marin")
    notes = [
        "Subscriber PSTN uses this stack; agents only override voice slug, speed, and language.",
        "Sarvam/Cartesia STT/TTS blocks are stripped for realtime_voice dials.",
    ]
    if provider == "gemini":
        from server.realtime.providers.gemini_voice import normalize_gemini_live_voice

        notes.append(
            f"Gemini Live maps console voice '{voice_slug}' → "
            f"'{normalize_gemini_live_voice(voice_slug)}' at connect."
        )
        notes.append("PCM: 16 kHz in / 24 kHz out on the Gemini Live wire.")
    else:
        notes.append("OpenAI Realtime: 24 kHz PCM on the speech-to-speech wire.")
    return {
        "ok": True,
        "pipeline": resolved.get("pipeline"),
        "liveProvider": provider,
        "liveModel": model,
        "realtimeVoice": voice_slug,
        "language": resolved.get("language"),
        "notes": notes,
    }


@router.get("/api/dev/stack/saas-phone")
async def dev_stack_saas_phone_get(session: SessionData = Depends(require_dev_session)):
    """Universal live-phone stack applied to all SaaS PSTN + web practice calls."""
    require_permission(session, "dev.stack.read")
    from server.services.saas.platform_phone_stack import (
        load_universal_phone_stack_raw,
        resolve_platform_phone_stack,
    )

    saved = load_universal_phone_stack_raw()
    lang = str((saved or {}).get("language") or "te-IN")
    resolved = await resolve_platform_phone_stack(lang)
    return {
        "ok": True,
        "saved": saved,
        "resolved": resolved,
        "credentials": _saas_phone_stack_credentials(),
        "warnings": _saas_phone_stack_warnings(resolved),
        "alignment": _saas_phone_stack_alignment(resolved),
        "adjustments": (saved or {}).get("adjustments") or [],
    }


@router.put("/api/dev/stack/saas-phone")
async def dev_stack_saas_phone_put(body: SaasPhoneStackBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    from server.services.pstn_stack import normalize_pstn_stack_override
    from server.services.saas.platform_phone_stack import save_universal_phone_stack_raw

    lang = (body.language or "te-IN").strip() or "te-IN"
    raw = body.stack_override or {"pipeline": "realtime_voice", "language": lang}
    raw.setdefault("pipeline", "realtime_voice")
    raw.setdefault("language", lang)
    normalized, adjustments = normalize_pstn_stack_override(raw, language=lang, tier="medium")
    resolved = normalized or raw
    payload = {
        "stack_override": resolved,
        "language": lang,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": session.subject,
    }
    if adjustments:
        payload["adjustments"] = adjustments
    save_universal_phone_stack_raw(payload)
    warnings = _saas_phone_stack_warnings(resolved)
    return {
        "ok": True,
        "saved": payload,
        "resolved": resolved,
        "adjustments": adjustments,
        "warnings": warnings,
        "alignment": _saas_phone_stack_alignment(resolved),
        "credentials": _saas_phone_stack_credentials(),
    }
