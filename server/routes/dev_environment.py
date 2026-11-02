"""Dev Portal environment and API key overlay routes."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.rbac import ROLE_SUPER_ADMIN
from server.auth.session import SessionData
from server.services.dev_secrets_store import ALLOWED_PATCH_KEYS, dev_secrets_store
from server.services.saas.admin_audit import record_admin_action

router = APIRouter()

#: Fields holding URLs the platform calls back on: https only.
_URL_FIELDS = frozenset({"vobiz_webhook_base_url"})
#: Fields that redirect traffic or flip production behaviour: super admins only.
_SUPER_ADMIN_FIELDS = frozenset({"app_environment"}) | _URL_FIELDS


def _is_url_field(field: str) -> bool:
    return field in _URL_FIELDS or field.endswith("_url")


def _require_super_admin_for(session: SessionData, fields: set[str]) -> None:
    guarded = sorted(f for f in fields if f in _SUPER_ADMIN_FIELDS or _is_url_field(f))
    if guarded and session.role != ROLE_SUPER_ADMIN:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "super_admin_required",
                    "message": f"Only a super admin can change: {', '.join(guarded)}",
                }
            },
        )


def _validate_urls(patch: dict[str, Any]) -> None:
    for field, value in patch.items():
        if not _is_url_field(field) or value in ("", None):
            continue
        parts = urlsplit(str(value).strip())
        if parts.scheme.lower() != "https" or not parts.hostname:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "validation_error", "message": f"{field} must be an https:// URL"}},
            )


async def _audit(session: SessionData, action: str, fields: list[str]) -> None:
    # Field names only: values are API keys and tokens.
    await record_admin_action(
        actor=session.subject,
        action=action,
        resource_type="dev_environment",
        resource_id="overlay",
        payload={"fields": sorted(fields)},
    )


class EnvironmentPatch(BaseModel):
    """Partial update — only sent fields are applied to the dev overlay.

    Unknown or read-only fields are passed to the store, which returns them as
    ``rejected``. Forbidding them failed the whole save with 400 whenever the
    panel sent a field this model did not list (enable_gnani, gemini_model), so
    no key was ever stored.
    """

    model_config = ConfigDict(extra="allow")

    openai_api_key: str | None = None
    sarvam_api_key: str | None = None
    deepseek_api_key: str | None = None
    cartesia_api_key: str | None = None
    gemini_api_key: str | None = None
    gnani_api_key: str | None = None
    telnyx_api_key: str | None = None
    vobiz_auth_token: str | None = None
    enable_sarvam: bool | None = None
    enable_openai: bool | None = None
    enable_deepseek: bool | None = None
    enable_cartesia: bool | None = None
    enable_gemini: bool | None = None
    enable_gnani: bool | None = None
    enable_telnyx: bool | None = None
    enable_vobiz: bool | None = None
    enable_benchmarks: bool | None = None
    enable_prewarm_greeting: bool | None = None
    voice_agent_config_mode: str | None = None
    voice_agent_tier: str | None = None
    app_environment: str | None = None
    telephony_provider: str | None = None
    telnyx_connection_id: str | None = None
    telnyx_phone_number: str | None = None
    telnyx_outbound_voice_profile_id: str | None = None
    vobiz_auth_id: str | None = None
    vobiz_app_id: str | None = None
    vobiz_phone_number: str | None = None
    vobiz_webhook_base_url: str | None = None
    sarvam_llm_models_csv: str | None = Field(None, max_length=2000)
    gemini_tts_models_csv: str | None = Field(None, max_length=2000)


def _patch_dict(body: EnvironmentPatch) -> dict[str, Any]:
    return {**body.model_dump(exclude_none=True), **{k: v for k, v in (body.model_extra or {}).items() if v is not None}}


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
    _require_super_admin_for(session, set(patch))
    _validate_urls(patch)
    snapshot = dev_secrets_store.update(patch)
    await _audit(session, "dev_environment.update", list(snapshot.get("applied_keys") or patch.keys()))
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
    _require_super_admin_for(session, {field})
    snapshot = dev_secrets_store.remove_overlay_key(field)
    await _audit(session, "dev_environment.clear", [field])
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
    from server.services.dev_runtime import notify_dev_overlay_changed

    notify_dev_overlay_changed()
    return {"ok": True, "environment": dev_secrets_store.snapshot()}
