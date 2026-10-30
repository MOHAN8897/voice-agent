"""Dev Portal stack + promotion APIs — Phase 5."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.config.constants import constants
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import ConfigVersion
from server.db.tier_store import (
    get_cached_tier_stack,
    get_tier_combination_id,
    promote_tier_assignments,
)
from server.providers import get_provider_registry, resolve_stack
from server.utils.logger import logger
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


class ComposedVoiceProfileBody(BaseModel):
    expected_revision: int = Field(..., alias="expectedRevision", ge=0)
    composed_profile: dict[str, Any] = Field(..., alias="composedProfile")
    # Required when the change would take an enabled tier offline.
    confirm_take_offline: bool = Field(False, alias="confirmTakeOffline")

    model_config = {"populate_by_name": True}


class ComposedVoiceActivationBody(BaseModel):
    expected_revision: int = Field(..., alias="expectedRevision", ge=0)
    enabled: bool

    model_config = {"populate_by_name": True}


class ComposedVoiceVerificationBody(BaseModel):
    expected_revision: int = Field(..., alias="expectedRevision", ge=0)
    model_config = {"populate_by_name": True}


class ComposedVoiceDuplicateBody(BaseModel):
    source_tier: str = Field(..., alias="sourceTier")
    target_label: str | None = Field(None, alias="targetLabel")
    target_tier: str | None = Field(None, alias="targetTier")

    model_config = {"populate_by_name": True}


class DevVoicePreviewBody(BaseModel):
    provider: str
    model: str | None = None
    voice_id: str = Field(..., alias="voiceId")
    text: str | None = None
    language: str | None = "te-IN"
    speed: float | None = 1.0
    pitch: float | None = None
    temperature: float | None = None
    emotion: str | None = None
    volume: float | None = None

    model_config = {"populate_by_name": True}


def _voice_profile_http_error(exc) -> HTTPException:
    detail = {"error": {"code": exc.code, "message": str(exc), **(exc.details or {})}}
    return HTTPException(status_code=exc.status_code, detail=detail)


@router.get("/api/dev/stack/catalog")
async def dev_stack_catalog(session: SessionData = Depends(require_dev_session), refreshVoices: bool = False):
    require_permission(session, "dev.stack.read")
    from server.providers.catalog_refresh import get_fresh_catalog

    try:
        import copy
        from server.providers.voice_inventory import inventory, profile_voice_rows, refresh_inventory
        from server.config.constants import constants
        from server.services.tts_voice_direction import tts_knob_specs

        if refreshVoices:
            refresh_result = await refresh_inventory()
        else:
            refresh_result = {"checkedAt": inventory().get("checkedAt"), "errors": []}
        catalog = copy.deepcopy(get_fresh_catalog())
        for provider in catalog.get("providers", []):
            models = provider.get("models") or {}
            # Native audio has a single model for conversation and speech.
            native = [row for row in models.get("llm", []) if row.get("realtime") and provider["id"] == "gemini"]
            tts_models = models.setdefault("tts", [])
            for row in native:
                if not any(item["id"] == row["id"] for item in tts_models):
                    tts_models.append({**row, "api_mode": "websocket", "api_modes": ["websocket"]})
            for row in tts_models:
                row["voices"] = profile_voice_rows(provider["id"], row["id"], list(constants.SUPPORTED_LANGUAGES), include_unavailable=True)
                row["knobs"] = tts_knob_specs(provider["id"], row["id"])
        catalog["voiceInventory"] = refresh_result
    except Exception as exc:
        logger.warning(f"[VOICE] Catalog fetch failed: {exc}")
        catalog = {"providers": [], "fx_rate_inr": 94.0}

    try:
        telephony = await telephony_summary_async()
    except Exception as exc:
        logger.warning(f"[VOICE] Telephony summary failed: {exc}")
        telephony = {"active_provider": "vobiz", "active_enabled": True, "active_ready": False, "providers": []}

    catalog["telephony"] = {
        "active_provider": telephony.get("active_provider"),
        "active_enabled": telephony.get("active_enabled"),
        "active_ready": telephony.get("active_ready"),
        "providers": telephony.get("providers") or [],
        "enabled_providers": telephony.get("enabled_providers") or [],
    }
    return catalog


@router.get("/api/dev/stack/voice-profiles")
async def dev_composed_voice_profiles(session: SessionData = Depends(require_dev_session)):
    """Admin-only view of durable composed profile revisions and release blockers."""
    require_permission(session, "dev.stack.read")
    from server.services.saas.voice_stack_profiles import TIER_LABELS, profile_view
    from server.db.connection import get_session_factory
    from server.db.models.entities import TierAssignment
    from sqlalchemy import select

    app_env = effective_app_environment()
    base_tiers = ["low", "medium", "premium"]
    all_tiers: list[str] = list(base_tiers)

    factory = get_session_factory()
    if factory:
        try:
            async with factory() as db_session:
                rows = await db_session.execute(
                    select(TierAssignment.tier).where(TierAssignment.environment == app_env)
                )
                db_tiers = [str(r[0]) for r in rows.all()]
                for t in db_tiers:
                    if t not in all_tiers:
                        all_tiers.append(t)
        except Exception as exc:
            logger.warning("[VOICE] Could not query db tiers: %s", exc)

    profiles = []
    for tier in all_tiers:
        try:
            profiles.append(await profile_view(tier, app_env, include_internal=True))
        except Exception as exc:
            logger.warning("[VOICE] Error loading profile for tier %s: %s", tier, exc)
            profiles.append({
                "tier": tier,
                "label": TIER_LABELS.get(tier, tier.replace("_", " ").title()),
                "profileRevision": 0,
                "composedProfile": None,
                "readiness": {"ready": False, "enabled": False, "blockers": [{"code": "tier_load_error", "message": str(exc)}]},
                "retailRate": None,
                "readOnly": False,
            })
    return {"environment": app_env, "profiles": profiles}


@router.post("/api/dev/stack/voice-profiles/duplicate")
async def dev_composed_voice_profile_duplicate(
    body: ComposedVoiceDuplicateBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.write")
    from server.services.saas.voice_stack_profiles import (
        VoiceProfileError,
        canonical_voice_tier,
        load_profile_records,
        profile_view,
        save_composed_profile,
    )
    from server.services.saas.voice_stack_defaults import recommended_composed_profile
    from server.db.connection import get_session_factory
    from server.db.models.entities import TierAssignment
    from sqlalchemy import select
    import copy
    import re

    app_env = effective_app_environment()
    try:
        source_tier = canonical_voice_tier(body.source_tier)
    except VoiceProfileError:
        source_tier = str(body.source_tier).strip().lower()

    existing_tiers: set[str] = set()
    factory = get_session_factory()
    if factory:
        try:
            async with factory() as db_session:
                rows = await db_session.execute(
                    select(TierAssignment.tier).where(TierAssignment.environment == app_env)
                )
                existing_tiers = {str(r[0]).lower() for r in rows.all()}
        except Exception:
            pass

    target_tier = (body.target_tier or "").strip().lower()
    if not target_tier or target_tier in existing_tiers or not re.match(r"^[a-z0-9_]{1,20}$", target_tier):
        base_prefix = source_tier[:10].replace("-", "_")
        idx = 1
        candidate = f"{base_prefix}_copy_{idx}"[:20]
        while candidate in existing_tiers:
            idx += 1
            candidate = f"{base_prefix}_copy_{idx}"[:20]
        target_tier = candidate

    source_record = (await load_profile_records(app_env, (source_tier,))).get(source_tier)
    if source_record and isinstance(source_record.get("profile"), dict):
        cloned_profile = copy.deepcopy(source_record["profile"])
    else:
        cloned_profile = recommended_composed_profile(source_tier, allow_premium=True)

    source_label = cloned_profile.get("label") or source_tier.replace("_", " ").title()
    target_label = (body.target_label or "").strip() or f"{source_label} (Copy)"
    cloned_profile["label"] = target_label[:100]
    cloned_profile["enabled"] = False

    try:
        return await save_composed_profile(
            environment=app_env,
            tier=target_tier,
            expected_revision=0,
            payload=cloned_profile,
            actor=session.subject,
            allow_premium=True,
        )
    except VoiceProfileError as exc:
        raise _voice_profile_http_error(exc) from exc


@router.get("/api/dev/stack/voice-profiles/{tier}/template")
async def dev_composed_voice_template(tier: str, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    from server.services.saas.voice_stack_defaults import recommended_composed_profile
    from server.services.saas.voice_stack_profiles import VoiceProfileError

    try:
        return {"tier": tier, "composedProfile": recommended_composed_profile(tier, allow_premium=True)}
    except VoiceProfileError as exc:
        raise _voice_profile_http_error(exc) from exc


@router.put("/api/dev/stack/voice-profiles/{tier}")
async def dev_composed_voice_profile_update(
    tier: str,
    body: ComposedVoiceProfileBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.write")
    from server.services.saas.voice_stack_profiles import VoiceProfileError, save_composed_profile

    try:
        return await save_composed_profile(
            environment=effective_app_environment(),
            tier=tier,
            expected_revision=body.expected_revision,
            payload=body.composed_profile,
            actor=session.subject,
            allow_premium=True,
            confirm_take_offline=body.confirm_take_offline,
        )
    except VoiceProfileError as exc:
        raise _voice_profile_http_error(exc) from exc


@router.get("/api/dev/stack/voice-profiles/usage")
async def dev_composed_voice_profile_usage(session: SessionData = Depends(require_dev_session)):
    """How many agents use each tier, so the admin sees the blast radius of a change."""
    require_permission(session, "dev.stack.read")
    from sqlalchemy import func, select

    from server.db.models.entities import Agent
    from server.services.saas.voice_stack_profiles import VoiceProfileError, canonical_voice_tier

    app_env = effective_app_environment()
    counts: dict[str, int] = {}
    factory = get_session_factory()
    if factory is None:
        return {"environment": app_env, "agentsByTier": counts, "available": False}
    try:
        async with factory() as db:
            rows = await db.execute(
                select(Agent.default_tier, func.count())
                .where(Agent.environment == app_env, Agent.status != "deleted")
                .group_by(Agent.default_tier)
            )
            for raw_tier, count in rows.all():
                try:
                    tier = canonical_voice_tier(raw_tier or "medium")
                except VoiceProfileError:
                    tier = str(raw_tier or "")
                counts[tier] = counts.get(tier, 0) + int(count or 0)
    except Exception as exc:
        logger.warning("[VOICE] Could not count agents per tier: %s", exc)
        return {"environment": app_env, "agentsByTier": {}, "available": False}
    return {"environment": app_env, "agentsByTier": counts, "available": True}


@router.put("/api/dev/stack/voice-profiles/{tier}/activation")
async def dev_composed_voice_profile_activation(
    tier: str,
    body: ComposedVoiceActivationBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.write")
    from server.services.saas.voice_stack_profiles import VoiceProfileError, set_profile_enabled

    try:
        return await set_profile_enabled(
            environment=effective_app_environment(),
            tier=tier,
            expected_revision=body.expected_revision,
            enabled=body.enabled,
            actor=session.subject,
            allow_premium=True,
        )
    except VoiceProfileError as exc:
        raise _voice_profile_http_error(exc) from exc


@router.post("/api/dev/stack/voice-profiles/{tier}/verify")
async def dev_composed_voice_profile_verify(
    tier: str,
    body: ComposedVoiceVerificationBody,
    session: Annotated[SessionData, Depends(require_dev_session)],
):
    require_permission(session, "dev.stack.write")
    from server.services.saas.voice_profile_verification import verify_saved_profile
    from server.services.saas.voice_stack_profiles import VoiceProfileError

    try:
        return await verify_saved_profile(environment=effective_app_environment(), tier=tier,
            expected_revision=body.expected_revision, actor=session.subject)
    except VoiceProfileError as exc:
        raise _voice_profile_http_error(exc) from exc


@router.delete("/api/dev/stack/voice-profiles/{tier}")
async def dev_composed_voice_profile_delete(
    tier: str,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.write")
    from server.services.saas.voice_stack_profiles import VoiceProfileError, delete_composed_profile

    try:
        return await delete_composed_profile(
            environment=effective_app_environment(),
            tier=tier,
            actor=session.subject,
        )
    except VoiceProfileError as exc:
        raise _voice_profile_http_error(exc) from exc



@router.post("/api/dev/stack/voice-preview")
async def dev_composed_voice_preview(
    body: DevVoicePreviewBody,
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.stack.read")
    import base64
    from server.services.saas.voice_preview import synthesize_preview

    sample_text = (body.text or "").strip()
    if not sample_text:
        sample_text = "నమస్కారం! నేను మీకు ఎలా సహాయం చేయగలను?" if (body.language or "").startswith("te") else "Hello! How can I help you today?"

    try:
        result = await synthesize_preview(
            sample_text,
            voice_id=body.voice_id,
            language=body.language or "te-IN",
            speed=body.speed or 1.0,
            pitch=body.pitch,
            temperature=body.temperature,
            emotion=body.emotion,
            volume=body.volume,
            provider=body.provider,
            model=body.model,
        )
        audio = result.get("audio") or b""
        return {
            "voice": result.get("voice"),
            "label": result.get("label"),
            "audio_base64": base64.b64encode(audio).decode("ascii") if isinstance(audio, bytes) else str(audio),
            "content_type": "audio/wav",
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/dev/stack/tiers")
async def dev_stack_tiers(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    settings = get_settings()
    app_env = effective_app_environment()
    tiers: list[dict[str, Any]] = []
    for tier in constants.TIER_NAMES:
        try:
            cached = get_cached_tier_stack(app_env, tier)
            db_combo = await get_tier_combination_id(app_env, tier)
            if cached is not None:
                resolved = resolve_stack(mode="frontend", user_selection=cached, tier=tier, environment=app_env)
            else:
                resolved = resolve_stack(mode="env", tier=tier, environment=app_env)
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
    if source == target:
        return {"ok": False, "error": {"code": "validation_error", "message": "Source and target environments are the same."}}
    previous_rows: list[dict[str, Any]] = []
    count = await promote_tier_assignments(source, target, actor=session.subject, snapshot=previous_rows)
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
                        "source_environment": source,
                        "target_environment": target,
                        "reason": body.reason,
                        "actor": session.subject,
                        "tier_rows_copied": count,
                        # Exact prior target state, so rollback restores it.
                        "previous_rows": previous_rows,
                    },
                    created_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
    return {"ok": True, "promotion_id": promotion_id, "target_environment": target, "source_environment": source, "tier_rows_copied": count}


@router.post("/api/promotions/{promotion_id}/rollback")
async def promotion_rollback(promotion_id: str, session: SessionData = Depends(require_dev_session)):
    """Restore the target environment's tier rows to their state before the promotion."""
    require_permission(session, "dev.promote")
    from sqlalchemy import select

    from server.db.tier_store import restore_tier_assignments

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"error": {"code": "durable_store_unavailable", "message": "Rollback requires the configuration store."}})
    async with factory() as db:
        promotion = (await db.execute(
            select(ConfigVersion).where(
                ConfigVersion.resource_type == "promotion",
                ConfigVersion.resource_id == promotion_id,
            ).limit(1)
        )).scalar_one_or_none()
    payload = promotion.payload if promotion is not None and isinstance(promotion.payload, dict) else None
    if payload is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "promotion_not_found", "message": "Promotion not found."}})
    previous_rows = payload.get("previous_rows")
    target = str(payload.get("target_environment") or "")
    if not isinstance(previous_rows, list) or not target:
        raise HTTPException(status_code=409, detail={"error": {
            "code": "rollback_unavailable",
            "message": "This promotion was recorded without a snapshot and cannot be rolled back automatically.",
        }})
    count = await restore_tier_assignments(target, previous_rows, actor=session.subject)
    async with factory() as db:
        db.add(
            ConfigVersion(
                id=uuid.uuid4(),
                resource_type="promotion_rollback",
                resource_id=promotion_id,
                version=1,
                payload={"actor": session.subject, "target_environment": target, "tier_rows_restored": count},
                created_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
    return {"ok": True, "promotion_id": promotion_id, "target_environment": target,
            "tier_rows_restored": count, "tier_rows_synced": count}


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
    from server.services.live_caller_transcription import live_api_key
    return {
        "openai": {"configured": bool(live_api_key("gpt-transcribe"))},
        "sarvam": {"configured": bool(live_api_key("saaras:v3-realtime"))},
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
    from server.services.live_caller_transcription import validate_live_transcription
    try:
        validate_live_transcription(resolved)
    except ValueError:
        warnings.append("Selected live transcription credentials are missing. Configure them before placing calls.")
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
    from server.services.saas.voice_catalog import phone_voice_catalog

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
        "voices": phone_voice_catalog(),
    }


@router.put("/api/dev/stack/saas-phone")
async def dev_stack_saas_phone_put(body: SaasPhoneStackBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    from server.services.pstn_stack import normalize_pstn_stack_override
    from server.services.saas.platform_phone_stack import (
        mirror_universal_phone_stack_to_db,
        save_universal_phone_stack_raw,
    )

    lang = (body.language or "te-IN").strip() or "te-IN"
    raw = body.stack_override or {"pipeline": "realtime_voice", "language": lang}
    raw.setdefault("pipeline", "realtime_voice")
    raw.setdefault("language", lang)
    try:
        normalized, adjustments = normalize_pstn_stack_override(
            raw, language=lang, tier="medium", default_provider="gemini"
        )
    except ValueError as exc:
        raise HTTPException(422, detail={"error": {"code": "invalid_phone_stack", "message": str(exc)}}) from exc
    resolved = normalized or raw
    payload = {
        "stack_override": resolved,
        "language": lang,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": session.subject,
    }
    if adjustments:
        payload["adjustments"] = adjustments
    database_persisted = await mirror_universal_phone_stack_to_db(payload)
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
        "databasePersisted": database_persisted,
    }


class PrewarmGreetingBody(BaseModel):
    enabled: bool


@router.get("/api/dev/stack/prewarm-greeting")
async def dev_get_prewarm_greeting(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    from server.services.pstn_prewarm import is_prewarm_greeting_enabled

    return {"ok": True, "enabled": is_prewarm_greeting_enabled()}


@router.patch("/api/dev/stack/prewarm-greeting")
async def dev_patch_prewarm_greeting(body: PrewarmGreetingBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    from server.services.dev_secrets_store import dev_secrets_store

    dev_secrets_store.update({"enable_prewarm_greeting": body.enabled})
    return {"ok": True, "enabled": body.enabled}
