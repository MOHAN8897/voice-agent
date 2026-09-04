"""Dev Portal environment and API key overlay routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.services.dev_secrets_store import ALLOWED_PATCH_KEYS, dev_secrets_store

router = APIRouter()


class EnvironmentPatch(BaseModel):
    """Partial update — only sent fields are applied to the dev overlay."""

    model_config = ConfigDict(extra="forbid")

    openai_api_key: str | None = None
    sarvam_api_key: str | None = None
    deepseek_api_key: str | None = None
    cartesia_api_key: str | None = None
    gemini_api_key: str | None = None
    exotel_api_key: str | None = None
    exotel_api_token: str | None = None
    telnyx_api_key: str | None = None
    plivo_auth_id: str | None = None
    plivo_auth_token: str | None = None
    enable_sarvam: bool | None = None
    enable_openai: bool | None = None
    enable_deepseek: bool | None = None
    enable_cartesia: bool | None = None
    enable_gemini: bool | None = None
    enable_exotel: bool | None = None
    enable_telnyx: bool | None = None
    enable_plivo: bool | None = None
    enable_benchmarks: bool | None = None
    voice_agent_config_mode: str | None = None
    voice_agent_tier: str | None = None
    app_environment: str | None = None
    telephony_provider: str | None = None
    exotel_account_sid: str | None = None
    exotel_subdomain: str | None = None
    exotel_exophone: str | None = None
    exotel_webhook_base_url: str | None = None
    telnyx_connection_id: str | None = None
    telnyx_phone_number: str | None = None
    telnyx_outbound_voice_profile_id: str | None = None
    plivo_phone_number: str | None = None


def _patch_dict(body: EnvironmentPatch) -> dict[str, Any]:
    return body.model_dump(exclude_none=True)


@router.get("/api/dev/environment")
async def dev_environment_get(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    return {"ok": True, "environment": dev_secrets_store.snapshot()}


@router.get("/api/dev/environment/schema")
async def dev_environment_schema(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    snap = dev_secrets_store.snapshot()
    return {
        "ok": True,
        "allowed_patch_keys": snap.get("allowed_patch_keys", sorted(ALLOWED_PATCH_KEYS)),
        "overlay_keys": snap.get("overlay_keys", []),
        "persist_path": "data/dev_secrets.json",
    }


@router.put("/api/dev/environment")
async def dev_environment_put(body: EnvironmentPatch, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    patch = _patch_dict(body)
    if not patch:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "validation_error", "message": "No fields to update"}},
        )
    snapshot = dev_secrets_store.update(patch)
    return {
        "ok": True,
        "applied_keys": snapshot.get("applied_keys", []),
        "rejected": snapshot.get("rejected", []),
        "environment": snapshot,
    }


@router.patch("/api/dev/environment")
async def dev_environment_patch(body: EnvironmentPatch, session: SessionData = Depends(require_dev_session)):
    """Alias for PUT — partial overlay update."""
    return await dev_environment_put(body, session)


@router.delete("/api/dev/environment/{field}")
async def dev_environment_delete_field(field: str, session: SessionData = Depends(require_dev_session)):
    """Remove one overlay key so runtime falls back to .env."""
    require_permission(session, "dev.stack.write")
    if field not in ALLOWED_PATCH_KEYS:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "not_allowed", "message": f"Field {field} cannot be cleared via API"}},
        )
    snapshot = dev_secrets_store.remove_overlay_key(field)
    return {
        "ok": True,
        "removed": snapshot.get("removed"),
        "environment": snapshot,
    }


@router.post("/api/dev/environment/reload")
async def dev_environment_reload(session: SessionData = Depends(require_dev_session)):
    """Reload overlay file and re-init provider registry without changing values."""
    require_permission(session, "dev.stack.write")
    dev_secrets_store.reload()
    from server.config.env import get_settings
    from server.providers import init_provider_registry

    get_settings.cache_clear()
    init_provider_registry()
    return {"ok": True, "environment": dev_secrets_store.snapshot()}
