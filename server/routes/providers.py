"""
Provider + tier routes — server/routes/providers.py
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.config.constants import constants
from server.config.env import get_settings
from server.services.dev_runtime import effective_app_environment, effective_config_mode, effective_voice_tier
from server.providers import get_provider_registry, resolve_stack
from server.providers.base import StackSelection, StageSelection
from server.utils.errors import AppError

router = APIRouter()


def _catalog_handler() -> dict[str, Any]:
    from server.providers.catalog_refresh import get_fresh_catalog

    return get_fresh_catalog()


@router.get("/api/providers/catalog")
async def providers_catalog():
    return _catalog_handler()


@router.get("/api/providers/status")
async def providers_status():
    from server.services.dev_fallback_store import dev_fallback_store

    catalog = _catalog_handler()
    return {
        "fallback_chains": dev_fallback_store.get_chains(),
        "providers": [
            {
                "id": p.get("id"),
                "enabled": p.get("enabled"),
                "configured": p.get("configured"),
                "healthy": p.get("healthy"),
                "stages": p.get("stages") or [],
            }
            for p in catalog.get("providers") or []
        ],
    }


@router.get("/api/tiers")
async def list_tiers():
    app_env = effective_app_environment()
    tiers = []
    for tier in constants.TIER_NAMES:
        try:
            resolved = resolve_stack(mode="env", tier=tier, environment=app_env)
            tiers.append({"tier": tier, "combination_id": resolved.combination_id, "preview": resolved.to_safe_dict()})
        except AppError as e:
            tiers.append({"tier": tier, "error": e.user_message, "code": e.code.value})
    return {
        "config_mode": effective_config_mode(),
        "active_tier": effective_voice_tier(),
        "environment": app_env,
        "tiers": tiers,
    }


@router.get("/api/tiers/{tier}/resolved")
async def tier_resolved(tier: str):
    if tier not in constants.TIER_NAMES:
        raise HTTPException(status_code=404, detail={"error": {"code": "validation_error", "message": f"Unknown tier: {tier}"}})
    app_env = effective_app_environment()
    resolved = resolve_stack(mode="env", tier=tier, environment=app_env)  # type: ignore[arg-type]
    return resolved.to_safe_dict()


class ValidateSelectionBody(BaseModel):
    stt: dict[str, Any] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    tts: dict[str, Any] = Field(default_factory=dict)
    language: str = "te-IN"


@router.post("/api/providers/{provider_id}/validate-selection")
async def validate_selection(provider_id: str, body: ValidateSelectionBody):
    """Pre-flight compatibility check for a stack selection."""
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
        if not registry.is_provider_enabled(provider_id, "stt") and not registry.is_provider_enabled(provider_id, "llm") and not registry.is_provider_enabled(provider_id, "tts"):
            return {"ok": False, "error": {"code": "provider_disabled", "message": f"Provider '{provider_id}' is not enabled"}}
        raise HTTPException(status_code=400, detail=str(e)[:200]) from e
