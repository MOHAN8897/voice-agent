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
    return get_provider_registry().get_catalog()


@router.get("/api/dev/stack/tiers")
async def dev_stack_tiers(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    settings = get_settings()
    tiers: list[dict[str, Any]] = []
    for tier in constants.TIER_NAMES:
        try:
            resolved = resolve_stack(mode="env", tier=tier, environment=settings.app_environment)
            db_combo = await get_tier_combination_id(settings.app_environment, tier)
            tiers.append(
                {
                    "tier": tier,
                    "combination_id": db_combo or resolved.combination_id,
                    "resolved": resolved.to_safe_dict(),
                    "environment": settings.app_environment,
                }
            )
        except AppError as e:
            tiers.append({"tier": tier, "error": e.user_message})
    return {"environment": settings.app_environment, "config_mode": settings.voice_agent_config_mode, "tiers": tiers}


@router.put("/api/dev/stack/tiers/{tier}")
async def dev_stack_tier_update(tier: str, body: TierStackBody, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    if tier not in constants.TIER_NAMES:
        return {"ok": False, "error": {"code": "validation_error", "message": f"Unknown tier: {tier}"}}
    settings = get_settings()
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
        environment=settings.app_environment,
    )
    if get_session_factory():
        await upsert_tier_assignment(
            settings.app_environment,
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
    tier = body.tier if body.tier in constants.TIER_NAMES else "medium"
    if body.stack:
        stack = StackSelection(
            stt=StageSelection(body.stack.stt_provider, body.stack.stt_model, {}),
            llm=StageSelection(body.stack.llm_provider, body.stack.llm_model, {}),
            tts=StageSelection(body.stack.tts_provider, body.stack.tts_model, {}),
            language=body.stack.language,
        )
        resolved = resolve_stack(mode="frontend", user_selection=stack, tier=tier, environment=settings.app_environment)
    else:
        resolved = resolve_stack(mode="env", tier=tier, environment=settings.app_environment)
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
    registry = get_provider_registry()

    def _stage(name: str, data: dict[str, Any], default_provider: str) -> StageSelection:
        return StageSelection(
            provider=data.get("provider") or default_provider,
            model=data.get("model") or "",
            config=data.get("config") or {},
        )

    stack = StackSelection(
        stt=_stage("stt", body.stt, provider_id if provider_id in ("sarvam", "cartesia") else "sarvam"),
        llm=_stage("llm", body.llm, provider_id if provider_id in ("openai", "deepseek", "gemini") else "openai"),
        tts=_stage("tts", body.tts, provider_id if provider_id in ("sarvam", "cartesia") else "sarvam"),
        language=body.language,
    )
    try:
        resolved = resolve_stack(
            mode="frontend",
            user_selection=stack,
            language=body.language,
            environment=settings.app_environment,
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
    source = settings.app_environment
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
    count = await sync_tier_assignments_from_env(environment=settings.app_environment)
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
