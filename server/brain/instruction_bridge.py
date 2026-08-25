"""
Bridge legacy /api/instructions to versioned business brain draft (Phase 2).
"""
from __future__ import annotations

from server.brain.agent_service import agent_service
from server.brain.business_brain_store import business_brain_store


async def sync_legacy_instructions_to_business_brain(
    *,
    behaviour: str = "",
    business: str = "",
) -> None:
    agent_id = await agent_service.resolve_default_agent_id()
    sections = await business_brain_store.ensure_default_sections(agent_id)
    updated = []
    for s in sections:
        row = dict(s)
        if row.get("type") == "identity_purpose" and behaviour.strip():
            row["raw_text"] = behaviour.strip()
        if row.get("type") == "facts" and business.strip():
            row["raw_text"] = business.strip()
        updated.append(row)
    await business_brain_store.save_draft_sections(agent_id, updated)
