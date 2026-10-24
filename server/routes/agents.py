"""Agent workspace routes — Phase 2."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt_if_enabled
from server.auth.tenant_context import tenant_id_from_request
from server.brain.agent_service import AgentVoiceRevisionConflict, agent_service
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)

router = APIRouter()


DEFAULT_RECORDING_DISCLOSURE = "This call may be recorded for quality and training purposes."


class CreateAgentBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255)
    tenantId: Optional[str] = None
    languages: Optional[list[str]] = None
    recordingDisclosureEnabled: Optional[bool] = None
    recordingDisclosureText: Optional[str] = Field(default=None, max_length=255)


def _disclosure_text(enabled: bool, text: str | None) -> str:
    cleaned = (text or "").strip()
    if enabled and not cleaned:
        return DEFAULT_RECORDING_DISCLOSURE
    return cleaned


class PatchAgentBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    status: Optional[str] = None
    defaultTier: Optional[str] = None
    expectedVoiceRevision: Optional[int] = Field(default=None, ge=0)
    expected_voice_revision: Optional[int] = Field(default=None, ge=0)
    languages: Optional[list[str]] = None
    memorySchema: Optional[str] = None
    voiceSettings: Optional[dict[str, Any]] = None
    voice_settings: Optional[dict[str, Any]] = None
    recordingDisclosureEnabled: Optional[bool] = None
    recordingDisclosureText: Optional[str] = Field(default=None, max_length=255)
    technicalFallbackPromiseCallback: Optional[bool] = None
    technicalFallbackText: Optional[str] = Field(default=None, max_length=255)


def _tenant_id(request: Request, principal: SubscriberPrincipal | None) -> str | None:
    if principal:
        return str(subscriber_workspace_tenant_id(principal))
    return tenant_id_from_request(request)


@router.get("/api/agents")
async def list_agents(
    request: Request,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    agents = await agent_service.list_agents(tenant_id=_tenant_id(request, principal))
    return {"agents": agents}


@router.post("/api/agents")
async def create_agent(
    request: Request,
    body: CreateAgentBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    tenant_id = _tenant_id(request, principal) or body.tenantId
    if principal and body.tenantId and body.tenantId != str(principal.tenant_id):
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_tenant", "message": "Invalid tenant"}})
    disclosure_enabled = bool(body.recordingDisclosureEnabled)
    agent = await agent_service.create_agent(
        name=body.name,
        tenant_id=tenant_id,
        languages=body.languages,
        recording_disclosure_enabled=disclosure_enabled,
        recording_disclosure_text=_disclosure_text(disclosure_enabled, body.recordingDisclosureText),
    )
    return {"ok": True, "agent": agent}


@router.get("/api/agents/{agent_id}")
async def get_agent(
    request: Request,
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    try:
        return {"agent": await agent_service.get_agent(agent_id, tenant_id=_tenant_id(request, principal))}
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})


@router.patch("/api/agents/{agent_id}")
async def patch_agent(
    request: Request,
    agent_id: str,
    body: PatchAgentBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    patch: dict[str, Any] = {}
    if body.name is not None:
        patch["name"] = body.name
    if body.status is not None:
        patch["status"] = body.status
    if body.defaultTier is not None:
        from server.services.saas.voice_stack_profiles import (
            VoiceProfileError,
            canonical_voice_tier,
        )

        try:
            patch["default_tier"] = canonical_voice_tier(body.defaultTier)
        except VoiceProfileError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"error": {"code": exc.code, "message": str(exc)}},
            ) from exc
    if body.languages is not None:
        patch["languages"] = body.languages
    if body.memorySchema is not None:
        patch["memory_schema"] = body.memorySchema
    vs = body.voiceSettings if body.voiceSettings is not None else body.voice_settings
    if vs is not None:
        patch["voice_settings"] = vs
    if body.recordingDisclosureEnabled is not None:
        patch["recording_disclosure_enabled"] = body.recordingDisclosureEnabled
    if body.recordingDisclosureText is not None:
        cleaned = body.recordingDisclosureText.strip()
        if not cleaned and body.recordingDisclosureEnabled is not False:
            cleaned = DEFAULT_RECORDING_DISCLOSURE
        patch["recording_disclosure_text"] = cleaned
    if body.technicalFallbackPromiseCallback is not None:
        patch["technical_fallback_promise_callback"] = body.technicalFallbackPromiseCallback
    if body.technicalFallbackText is not None:
        patch["technical_fallback_text"] = body.technicalFallbackText.strip()
    expected_rev = body.expectedVoiceRevision if body.expectedVoiceRevision is not None else body.expected_voice_revision
    try:
        agent = await agent_service.patch_agent(
            agent_id,
            patch,
            tenant_id=_tenant_id(request, principal),
            expected_voice_revision=expected_rev,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except AgentVoiceRevisionConflict as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": str(exc), **exc.details}},
        ) from exc
    return {"ok": True, "agent": agent}


@router.put("/api/agents/{agent_id}")
async def put_agent(
    request: Request,
    agent_id: str,
    body: PatchAgentBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    return await patch_agent(request, agent_id, body, principal)


@router.delete("/api/agents/{agent_id}")
async def delete_agent(
    request: Request,
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    try:
        return await agent_service.delete_agent(agent_id, tenant_id=_tenant_id(request, principal))
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except ValueError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})


def _clip_error(exc: Exception) -> HTTPException:
    from server.services.fallback_clip_store import FallbackClipError

    if isinstance(exc, FallbackClipError):
        return HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": str(exc)}},
        )
    return HTTPException(
        status_code=503,
        detail={"error": {"code": "fallback_store_unavailable", "message": "Fallback clips are unavailable."}},
    )


@router.get("/api/agents/{agent_id}/fallback-clips")
async def list_fallback_clips(
    request: Request,
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    from server.services import fallback_clip_store

    try:
        clips = await fallback_clip_store.list_clips(
            tenant_id=_tenant_id(request, principal),
            agent_id=agent_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except Exception as exc:
        raise _clip_error(exc)
    return {
        "clips": clips,
        "variants": list(fallback_clip_store.CLIP_VARIANTS),
        "languages": sorted({clip["language"] for clip in clips}),
    }


@router.put("/api/agents/{agent_id}/fallback-clips/{language}/{variant}")
async def upload_fallback_clip(
    request: Request,
    agent_id: str,
    language: str,
    variant: str,
    file: UploadFile = File(..., description="16-bit PCM WAV, mono or stereo, ≤2 MB, ≤30 s"),
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    from server.services import fallback_clip_store

    try:
        raw = await file.read(fallback_clip_store.MAX_UPLOAD_BYTES + 1)
        clip = await fallback_clip_store.upsert_clip(
            tenant_id=_tenant_id(request, principal),
            agent_id=agent_id,
            language=language,
            variant=variant,
            raw=raw,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}})
    except Exception as exc:
        raise _clip_error(exc)
    return {"ok": True, "clip": clip}


@router.delete("/api/agents/{agent_id}/fallback-clips/{language}/{variant}")
async def delete_fallback_clip(
    request: Request,
    agent_id: str,
    language: str,
    variant: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    if principal:
        require_subscriber_permission(principal, "app.agents.write")
    from server.services import fallback_clip_store

    try:
        await fallback_clip_store.delete_clip(
            tenant_id=_tenant_id(request, principal),
            agent_id=agent_id,
            language=language,
            variant=variant,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Clip not found"}})
    except Exception as exc:
        raise _clip_error(exc)
    return {"ok": True}
