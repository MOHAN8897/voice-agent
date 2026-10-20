"""Bind campaign recipients to a published script and keep that version for calls."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from server.brain.compiled_brain_service import compiled_brain_service
from server.db.connection import get_session_factory
from server.db.models.phase5_models import Campaign


async def published_campaign_script(version: str | None) -> tuple[str, str]:
    if not version:
        raise HTTPException(409, "Publish this agent's script before preparing campaign calls.")
    try:
        snapshot = await compiled_brain_service.get_snapshot(version)
    except KeyError as exc:
        raise HTTPException(409, "The campaign script is unavailable. Publish and validate the agent again.") from exc
    text = str(snapshot.get("compiled_text") or "")
    if not text.strip():
        raise HTTPException(409, "The published campaign script is empty.")
    return version, text


async def campaign_call_script(agent: dict[str, Any], contact: dict[str, Any] | None) -> tuple[str, str] | None:
    """Look up the snapshot through an owned campaign, never a client-supplied version ID."""
    campaign_id = (contact or {}).get("campaign_id")
    if not campaign_id:
        return None
    try:
        cid, aid, tid = UUID(str(campaign_id)), UUID(str(agent["agent_id"])), UUID(str(agent["tenant_id"]))
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, "Campaign context is unavailable.") from exc
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(503, "Campaign storage is unavailable.")
    async with factory() as db:
        campaign = (await db.execute(select(Campaign).where(
            Campaign.campaign_id == cid, Campaign.agent_id == aid, Campaign.tenant_id == tid,
        ))).scalar_one_or_none()
        if campaign is None:
            raise HTTPException(404, "Campaign not found")
        version = (campaign.schedule or {}).get("script_version")
    # Existing campaigns created before version binding still use their published agent.
    return await published_campaign_script(version or agent.get("active_compiled_brain_version"))


def require_campaign_variables(script: str, contacts: list[dict[str, Any]]) -> dict[str, Any]:
    from server.services.saas.contact_import_service import derive_names, validate_agent_variables_against_contacts

    report = validate_agent_variables_against_contacts([script], [derive_names(c) for c in contacts])
    if report["invalid_placeholders"]:
        raise HTTPException(422, detail={"error": {
            "code": "script_variables_invalid", "message": "The script contains unsupported or unclosed placeholders. Insert variables from the script editor, publish, and recheck contacts.",
        }})
    if not report["valid"]:
        raise HTTPException(422, detail={"error": {
            "code": "script_variables_missing",
            "message": "Some recipients are missing required script fields. Map the columns, add script fallbacks, or skip those recipients.",
            "missingFields": report["missing_breakdown"],
        }})
    return report
