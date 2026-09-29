"""Business brain routes per agent — Phase 2."""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from server.auth.subscriber_dependencies import require_subscriber_jwt_if_enabled
from server.brain.business_brain_store import assemble_raw_business_prompt, business_brain_store
from server.services.saas.script_variables import (
    SAAS_SCRIPT_VARIABLES_TITLE as SAAS_VARIABLES_TITLE,
)
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    load_agent_for_tenant,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)
from server.brain.business_prompt_optimizer import optimize_business_prompt
from server.brain.compiled_brain_service import compiled_brain_service
from server.brain.semantic_validation import validate_sections
from server.utils.errors import AppError

router = APIRouter()

#: Titles the SaaS console and the script compiler both agree on.
CALLING_SCRIPT_TITLE = "Calling script"
SAAS_VOICE_CONFIG_TITLE = "saas_voice_config"


async def _guard_agent(
    agent_id: str,
    principal: SubscriberPrincipal | None,
    *,
    write: bool = False,
) -> None:
    if principal is not None:
        await load_agent_for_tenant(agent_id, subscriber_workspace_tenant_id(principal))
        if write:
            require_subscriber_permission(principal, "app.brain.write")
        return
    # No subscriber principal (dev portal, SaaS auth off). Still confirm the agent
    # exists: brain sections are keyed by agent id, and writing them for an
    # unknown agent would either persist orphans or fail on the foreign key.
    from server.brain.agent_service import agent_service

    try:
        await agent_service.get_agent(agent_id)
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Agent not found"}},
        )


class DraftSectionsBody(BaseModel):
    sections: list[dict[str, Any]]


@router.get("/api/agents/{agent_id}/business-brain")
async def get_business_brain(
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    await _guard_agent(agent_id, principal)
    sections = await business_brain_store.ensure_default_sections(agent_id)
    versions = await business_brain_store.get_versions(agent_id)
    raw_prompt, checksum = assemble_raw_business_prompt(sections)
    return {
        "agent_id": agent_id,
        "draft": {"sections": sections, "raw_checksum": checksum},
        "published": versions[0] if versions else None,
        "versions_count": len(versions),
    }


@router.put("/api/agents/{agent_id}/business-brain/draft")
async def save_business_draft(
    agent_id: str,
    body: DraftSectionsBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    await _guard_agent(agent_id, principal, write=True)
    saved = await business_brain_store.save_draft_sections(agent_id, body.sections)
    raw_prompt, checksum = assemble_raw_business_prompt(saved)
    return {"ok": True, "sections": saved, "raw_checksum": checksum}


@router.post("/api/agents/{agent_id}/business-brain/validate")
async def validate_business_brain(
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    await _guard_agent(agent_id, principal)
    sections = await business_brain_store.get_sections(agent_id)
    if not sections:
        sections = await business_brain_store.ensure_default_sections(agent_id)
    result = validate_sections(sections)
    return result.to_dict()


@router.post("/api/agents/{agent_id}/business-brain/optimize")
async def optimize_business_brain(
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    await _guard_agent(agent_id, principal, write=True)
    sections = await business_brain_store.ensure_default_sections(agent_id)
    raw_prompt, checksum = assemble_raw_business_prompt(sections)
    previous = await business_brain_store.get_latest_published(agent_id)
    opt = await optimize_business_prompt(
        raw_prompt,
        source_checksum=checksum,
        previous_optimized=previous["optimized_prompt"] if previous else None,
    )
    return {"ok": True, "optimizer": opt.to_dict(), "raw_checksum": checksum}


@router.post("/api/agents/{agent_id}/business-brain/publish")
async def publish_business_brain(
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    await _guard_agent(agent_id, principal, write=True)
    try:
        snapshot = await compiled_brain_service.publish_agent_brain(agent_id)
    except AppError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict()) from e
    return {"ok": True, "compiled_version": snapshot["compiled_version"], "checksum": snapshot["checksum"]}


class CallingScriptBody(BaseModel):
    """The user-editable calling script.

    Persisted on its own so a console user can reword the script without
    re-running the compiler, which would overwrite their wording.
    """

    script: str = Field(..., min_length=1, max_length=60000)

    @field_validator("script")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("script must not be blank")
        return value


class VoiceConfigBody(BaseModel):
    """Voice selection for the live voice pipeline."""

    voiceId: str = Field("", max_length=120)
    speed: float = Field(1.0, ge=0.25, le=2.0)
    language: str = Field("en-IN", max_length=32)
    realtimeVoice: str | None = Field(None, max_length=120)
    turnDetection: str | None = Field(None, max_length=60)
    noiseReduction: str | None = Field(None, max_length=60)


async def _replace_section(
    agent_id: str,
    *,
    section_type: str,
    title: str,
    raw_text: str,
    enabled: bool = True,
    order: int = 20,
) -> None:
    """Create or update one named section, leaving every other section intact."""
    sections = await business_brain_store.get_sections(agent_id)
    if not sections:
        sections = await business_brain_store.ensure_default_sections(agent_id)
    match = next((s for s in sections if s.get("title") == title), None)
    if match is None:
        sections = [
            *sections,
            {
                "type": section_type,
                "title": title,
                "order": order,
                "raw_text": raw_text,
                "enabled": enabled,
            },
        ]
    else:
        match = {**match, "raw_text": raw_text, "enabled": enabled, "order": order}
        sections = [match if s.get("title") == title else s for s in sections]
    await business_brain_store.save_draft_sections(agent_id, sections)
    _raw, checksum = assemble_raw_business_prompt(sections)
    await business_brain_store.save_published_version(
        agent_id,
        optimized_prompt=_raw,
        source_checksum=checksum,
        optimizer_report={"source": "console", "section": title},
    )
    await compiled_brain_service.compile_for_agent(agent_id)


@router.put("/api/agents/{agent_id}/business-brain/calling-script")
async def save_calling_script(
    agent_id: str,
    body: CallingScriptBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    await _guard_agent(agent_id, principal, write=True)
    await _replace_section(
        agent_id,
        section_type="facts",
        title=CALLING_SCRIPT_TITLE,
        raw_text=body.script.strip(),
    )
    return {"ok": True, "compiled_version": await _active_version(agent_id)}


@router.put("/api/agents/{agent_id}/business-brain/voice")
async def save_voice_config(
    agent_id: str,
    body: VoiceConfigBody,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    """Voice config is stored disabled: the runtime reads it, the LLM must not."""
    await _guard_agent(agent_id, principal, write=True)
    payload = {
        "realtimeVoice": body.realtimeVoice or body.voiceId or "marin",
        "voiceId": body.voiceId,
        "speed": body.speed,
        "language": body.language,
        "turnDetection": body.turnDetection or "semantic_vad",
        "noiseReduction": body.noiseReduction or "far_field",
    }
    await _replace_section(
        agent_id,
        section_type="custom",
        title=SAAS_VOICE_CONFIG_TITLE,
        raw_text=json.dumps(payload, indent=2),
        enabled=False,
        order=2,
    )
    return {"ok": True, "voice": payload, "compiled_version": await _active_version(agent_id)}


@router.get("/api/agents/{agent_id}/business-brain/calling-script")
async def read_calling_script(
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    await _guard_agent(agent_id, principal)
    sections = await business_brain_store.get_sections(agent_id)
    if not sections:
        sections = await business_brain_store.ensure_default_sections(agent_id)
    script_section = next((s for s in sections if s.get("title") == CALLING_SCRIPT_TITLE), None)
    variables_section = next((s for s in sections if s.get("title") == SAAS_VARIABLES_TITLE), None)
    return {
        "agent_id": agent_id,
        "callingScript": (script_section or {}).get("raw_text", ""),
        "variables": _parse_variables(variables_section),
    }


async def _active_version(agent_id: str) -> str | None:
    try:
        snapshot = await compiled_brain_service.get_active_for_agent(agent_id)
    except KeyError:
        return None
    return snapshot.get("compiled_version")


def _parse_variables(section: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not section or not section.get("raw_text"):
        return []
    try:
        parsed = json.loads(section["raw_text"])
    except (TypeError, ValueError):
        return []
    variables = parsed.get("variables") if isinstance(parsed, dict) else None
    return variables if isinstance(variables, list) else []


@router.get("/api/agents/{agent_id}/business-brain/versions")
async def list_business_versions(
    agent_id: str,
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    await _guard_agent(agent_id, principal)
    versions = await business_brain_store.get_versions(agent_id)
    return {"agent_id": agent_id, "versions": versions}


@router.get("/api/agents/{agent_id}/brain/compiled-preview")
async def compiled_preview(
    agent_id: str,
    version: Optional[str] = Query(None),
    redacted: bool = Query(True),
    principal: SubscriberPrincipal | None = Depends(require_subscriber_jwt_if_enabled),
):
    await _guard_agent(agent_id, principal)
    try:
        snap = (
            await compiled_brain_service.get_snapshot(version)
            if version
            else await compiled_brain_service.get_active_for_agent(agent_id)
        )
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Compiled brain not found"}})
    text = snap["compiled_text"]
    if redacted:
        text = compiled_brain_service.redacted_preview(text)
    return {
        "agent_id": agent_id,
        "compiled_version": snap["compiled_version"],
        "platform_version": snap["platform_version"],
        "business_version": snap["business_version"],
        "token_estimate": snap["token_estimate"],
        "preview": text,
    }
