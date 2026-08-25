"""Dev Portal environment and API key overlay routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.services.dev_secrets_store import dev_secrets_store

router = APIRouter()


class EnvironmentPatch(BaseModel):
    openai_api_key: str | None = None
    sarvam_api_key: str | None = None
    deepseek_api_key: str | None = None
    cartesia_api_key: str | None = None
    gemini_api_key: str | None = None
    plivo_auth_id: str | None = None
    plivo_auth_token: str | None = None
    enable_sarvam: bool | None = None
    enable_openai: bool | None = None
    enable_deepseek: bool | None = None
    enable_cartesia: bool | None = None
    enable_gemini: bool | None = None
    enable_plivo: bool | None = None
    voice_agent_config_mode: str | None = None
    voice_agent_tier: str | None = None
    app_environment: str | None = None


@router.get("/api/dev/environment")
async def dev_environment(session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.read")
    return {"ok": True, "environment": dev_secrets_store.snapshot()}


@router.put("/api/dev/environment")
async def dev_environment_update(body: EnvironmentPatch, session: SessionData = Depends(require_dev_session)):
    require_permission(session, "dev.stack.write")
    patch: dict[str, Any] = body.model_dump(exclude_none=True)
    snapshot = dev_secrets_store.update(patch)
    return {"ok": True, "environment": snapshot}
