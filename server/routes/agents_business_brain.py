"""Business brain routes per agent — Phase 2."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from server.auth.subscriber_dependencies import require_subscriber_jwt_if_enabled
from server.brain.business_brain_store import assemble_raw_business_prompt, business_brain_store
from server.services.saas.tenant_guard import SubscriberPrincipal, load_agent_for_tenant, require_subscriber_permission
from server.brain.business_prompt_optimizer import optimize_business_prompt
from server.brain.compiled_brain_service import compiled_brain_service
from server.brain.semantic_validation import validate_sections
from server.utils.errors import AppError

router = APIRouter()


async def _guard_agent(
    agent_id: str,
    principal: SubscriberPrincipal | None,
    *,
    write: bool = False,
) -> None:
    if principal is None:
        return
    await load_agent_for_tenant(agent_id, principal.tenant_id)
    if write:
        require_subscriber_permission(principal, "app.brain.write")


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
