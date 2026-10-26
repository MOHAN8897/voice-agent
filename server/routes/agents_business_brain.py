"""Business brain routes per agent — Phase 2."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from server.auth.instructions_access import (
    InstructionsAccess,
    authorize_instruction_session,
    require_instructions_access,
)
from server.brain.business_brain_store import (
    assemble_raw_business_prompt,
    business_brain_store,
    draft_revision,
)
from server.brain.business_prompt_optimizer import optimize_business_prompt
from server.brain.compiled_brain_service import compiled_brain_service
from server.brain.semantic_validation import validate_sections
from server.services.saas.script_variables import (
    SAAS_SCRIPT_VARIABLES_TITLE as SAAS_VARIABLES_TITLE,
)
from server.services.saas.tenant_guard import (
    SubscriberPrincipal,
    load_agent_for_tenant,
    require_subscriber_permission,
    subscriber_workspace_tenant_id,
)
from server.utils.errors import AppError
from server.utils.logger import logger

router = APIRouter()
_INSTRUCTIONS_ACCESS = Depends(require_instructions_access)

#: Titles the SaaS console and the script compiler both agree on.
CALLING_SCRIPT_TITLE = "Calling script"
SAAS_VOICE_CONFIG_TITLE = "saas_voice_config"


async def _guard_agent(
    agent_id: str,
    principal: InstructionsAccess | SubscriberPrincipal | None,
    *,
    write: bool = False,
) -> None:
    from server.brain.agent_service import agent_service

    if isinstance(principal, InstructionsAccess):
        try:
            uuid.UUID(agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": "Agent not found"}}) from exc
        await authorize_instruction_session(agent_id, principal, write=write)
        return
    if principal is not None:
        await load_agent_for_tenant(agent_id, subscriber_workspace_tenant_id(principal))
        if write:
            require_subscriber_permission(principal, "app.brain.write")
        return
    # No subscriber principal (dev portal, SaaS auth off). Still confirm the agent
    # exists: brain sections are keyed by agent id, and writing them for an
    # unknown agent would either persist orphans or fail on the foreign key.
    try:
        await agent_service.get_agent(agent_id)
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Agent not found"}},
        )


class DraftSectionsBody(BaseModel):
    sections: list[dict[str, Any]]
    expected_revision: Optional[str] = Field(None)

    @field_validator("expected_revision")
    @classmethod
    def _validate_revision(cls, v: Optional[str]) -> Optional[str]:
        if not v or not str(v).strip():
            return None
        clean = str(v).strip()
        if len(clean) != 64:
            raise ValueError("expected_revision must be a 64-character SHA-256 hex string")
        return clean


class PublishBrainBody(BaseModel):
    expected_revision: Optional[str] = Field(None)

    @field_validator("expected_revision")
    @classmethod
    def _validate_revision(cls, v: Optional[str]) -> Optional[str]:
        if not v or not str(v).strip():
            return None
        clean = str(v).strip()
        if len(clean) != 64:
            raise ValueError("expected_revision must be a 64-character SHA-256 hex string")
        return clean


class PreviewSectionsBody(BaseModel):
    sections: list[dict[str, Any]] = Field(..., max_length=128)



@router.post("/api/agents/{agent_id}/business-brain/preview")
async def preview_business_brain(
    agent_id: str,
    body: PreviewSectionsBody,
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
):
    """Review the submitted draft without saving, publishing or calling an LLM."""
    await _guard_agent(agent_id, principal)
    import re

    from server.agent.brain_prompt_composer import estimate_tokens
    from server.brain.agent_script_compiler import _opening_line_is_language_compatible

    if sum(len(str(row.get("raw_text") or "")) for row in body.sections) > 100000:
        raise HTTPException(status_code=413, detail="Draft is too large to review")
    result = validate_sections(body.sections).to_dict()
    from server.prompts.agent_voice_rules import normalize_compile_language
    from server.services.saas.agent_voice_config import parse_voice_config_from_sections
    config = parse_voice_config_from_sections(body.sections)
    language = normalize_compile_language(config.get("language") or await compiled_brain_service._primary_language(agent_id))
    raw, checksum = assemble_raw_business_prompt(body.sections)
    script = "\n".join(str(row.get("raw_text") or "") for row in body.sections
                       if row.get("enabled", True) and row.get("title") == CALLING_SCRIPT_TITLE)
    for match in re.finditer(r"(?im)^---\s*CANONICAL OPENING\s*---\s*\n([\s\S]*?)(?=\n---|\Z)", script):
        if not _opening_line_is_language_compatible(match.group(1), language):
            result["issues"].append({"severity": "warning", "code": "opening_language_mismatch",
                                     "message": "The opening contains a different language script. Check it against the selected call language.", "section_ids": []})
    result["ok"] = not any(issue["severity"] == "blocking" for issue in result["issues"])
    return {**result, "language": language, "raw_checksum": checksum,
            "token_estimate": estimate_tokens(raw), "script_characters": len(script),
            "section_count": sum(row.get("enabled", True) for row in body.sections)}


@router.get("/api/agents/{agent_id}/business-brain")
async def get_business_brain(
    agent_id: str,
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
):
    await _guard_agent(agent_id, principal)
    sections = await business_brain_store.ensure_default_sections(agent_id)
    versions = await business_brain_store.get_versions(agent_id)
    raw_prompt, checksum = assemble_raw_business_prompt(sections)
    return {
        "agent_id": agent_id,
        "draft": {"sections": sections, "raw_checksum": checksum, "revision": draft_revision(sections)},
        "published": versions[0] if versions else None,
        "versions_count": len(versions),
    }


@router.put("/api/agents/{agent_id}/business-brain/draft")
async def save_business_draft(
    agent_id: str,
    body: DraftSectionsBody,
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
):
    await _guard_agent(agent_id, principal, write=True)
    try:
        saved = await business_brain_store.save_draft_sections(
            agent_id, await _carry_entity_tags_forward(agent_id, body.sections), expected_revision=body.expected_revision
        )
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc
    raw_prompt, checksum = assemble_raw_business_prompt(saved)
    return {"ok": True, "sections": saved, "raw_checksum": checksum, "revision": draft_revision(saved)}


@router.post("/api/agents/{agent_id}/business-brain/validate")
async def validate_business_brain(
    agent_id: str,
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
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
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
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
    body: PublishBrainBody,
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
):
    await _guard_agent(agent_id, principal, write=True)
    try:
        snapshot = await compiled_brain_service.publish_agent_brain(agent_id, expected_revision=body.expected_revision)
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


def _display_script(script: str | None) -> str:
    """The script as a person should read it — no machine-readable entity tags.

    The tags are an internal contract between the compiler and the runtime (PSTN
    prewarm pins the opening line and identity from them). They stay in the stored
    section and the compiled brain, but they are not part of the document the
    customer edits.
    """
    from server.brain.script_entities import strip_entity_tags_section

    return strip_entity_tags_section(script or "")


async def _carry_entity_tags_forward(agent_id: str, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-attach entity tags to a rewritten calling script.

    Any write path that replaces the `Calling script` section from customer-edited
    text would otherwise delete the tags — and with them the runtime's pinned identity
    and opening line. Preserving them here rather than in each caller means no edit
    path can silently drop them.
    """
    row = next((s for s in sections if s.get("title") == CALLING_SCRIPT_TITLE), None)
    if row is None:
        return sections
    row["raw_text"] = await _preserve_tags(agent_id, row.get("raw_text") or "")
    return sections


async def _preserve_tags(agent_id: str, script: str) -> str:
    """Keep the tags the stored script already has when its body is replaced."""
    import re

    from server.brain.script_entities import (
        parse_entity_tags,
        strip_entity_tags_section,
        with_entity_tags_section,
    )
    from server.services.pstn_text_chunker import _parse_agent_identity

    stored = await business_brain_store.get_sections(agent_id)
    previous = next((s for s in stored if s.get("title") == CALLING_SCRIPT_TITLE), None)
    explicit_entities = parse_entity_tags(script)
    entities = explicit_entities or parse_entity_tags((previous or {}).get("raw_text") or "") or {}
    # The console hides machine tags. A visible identity edit must update the
    # hidden identity used by prewarm and Gemini instead of pinning the old name.
    if not explicit_entities:
        name, company = _parse_agent_identity(strip_entity_tags_section(script))
        if name:
            entities["agent_name"] = name
            entities["company_name"] = company
    primary_lang = await compiled_brain_service._primary_language(agent_id)
    if entities:
        entities["language"] = primary_lang
    from server.brain.script_entities import patch_calling_script_language_markers
    from server.brain.compiled_brain_artifact import sanitize_closing_instructions
    script = sanitize_closing_instructions(patch_calling_script_language_markers(script, primary_lang))

    # Extract opening line from script's CANONICAL OPENING and update @opening_line
    canonical_match = re.search(
        r"(?:^|\n)(?:---|##)\s*CANONICAL OPENING\s*(?:---|##)?\s*\n+([\s\S]*?)(?=(?:\n+---|(?:\n+##)|\Z))",
        script,
        re.IGNORECASE,
    )
    if canonical_match:
        body = canonical_match.group(1).strip()
        lead_match = re.search(
            r"^(?:After the callee speaks, say once:|When you answer, say once:|Say once:|Say:|Example opening:)\s*\n*([\s\S]+)",
            body,
            re.IGNORECASE,
        )
        opening_line = (lead_match.group(1).strip() if lead_match else body).split("\n")[0].strip()
        if opening_line:
            entities["opening_line"] = opening_line

    return with_entity_tags_section(script, entities) if entities else script


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
    base_revision = draft_revision(sections)
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
    try:
        await compiled_brain_service.publish_agent_brain(agent_id, sections=sections, expected_revision=base_revision)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.put("/api/agents/{agent_id}/business-brain/calling-script")
async def save_calling_script(
    agent_id: str,
    body: CallingScriptBody,
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
):
    await _guard_agent(agent_id, principal, write=True)
    await _replace_section(
        agent_id,
        section_type="facts",
        title=CALLING_SCRIPT_TITLE,
        raw_text=await _preserve_tags(agent_id, body.script.strip()),
    )
    return {"ok": True, "compiled_version": await _active_version(agent_id)}


@router.put("/api/agents/{agent_id}/business-brain/voice")
async def save_voice_config(
    agent_id: str,
    body: VoiceConfigBody,
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
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
    try:
        from server.brain.agent_service import agent_service
        await agent_service.patch_agent(agent_id, {"voice_settings": payload})
    except Exception as exc:
        logger.debug("Failed to sync voice_settings to agent record: %s", type(exc).__name__)
    return {"ok": True, "voice": payload, "compiled_version": await _active_version(agent_id)}


@router.get("/api/agents/{agent_id}/business-brain/calling-script")
async def read_calling_script(
    agent_id: str,
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
):
    await _guard_agent(agent_id, principal)
    sections = await business_brain_store.get_sections(agent_id)
    if not sections:
        sections = await business_brain_store.ensure_default_sections(agent_id)
    script_section = next((s for s in sections if s.get("title") == CALLING_SCRIPT_TITLE), None)
    variables_section = next((s for s in sections if s.get("title") == SAAS_VARIABLES_TITLE), None)
    return {
        "agent_id": agent_id,
        "callingScript": _display_script((script_section or {}).get("raw_text", "")),
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
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
):
    await _guard_agent(agent_id, principal)
    versions = await business_brain_store.get_versions(agent_id)
    return {"agent_id": agent_id, "versions": versions}


@router.get("/api/agents/{agent_id}/brain/compiled-preview")
async def compiled_preview(
    agent_id: str,
    version: Optional[str] = Query(None),
    redacted: bool = Query(True),
    principal: InstructionsAccess | SubscriberPrincipal | None = _INSTRUCTIONS_ACCESS,
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
    if version and not any(row["version_id"] == snap["business_version"] for row in await business_brain_store.get_versions(agent_id)):
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
