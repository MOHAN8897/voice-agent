"""Dev portal compiled brain preview with layer precedence."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from server.auth.dependencies import require_dev_session, require_permission
from server.auth.session import SessionData
from server.brain.compiled_brain_service import compiled_brain_service
from server.brain.platform_brain_store import platform_brain_store

router = APIRouter()


@router.get("/api/dev/compiled-preview")
async def dev_compiled_preview(
    agent_id: str = Query(..., min_length=1),
    redacted: bool = Query(True),
    session: SessionData = Depends(require_dev_session),
):
    require_permission(session, "dev.platform_brain")
    try:
        snap = await compiled_brain_service.get_active_for_agent(agent_id)
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": str(e)[:200]}},
        ) from e

    platform_active = await platform_brain_store.get_active()
    text = snap["compiled_text"]
    layers: list[dict[str, Any]] = [
        {
            "layer": "platform",
            "version_id": platform_active["version_id"],
            "precedence": 1,
            "description": "Platform rules — highest precedence for safety and output contract",
        },
        {
            "layer": "business",
            "version_id": snap.get("business_version"),
            "precedence": 2,
            "description": "Business brain optimized prompt",
        },
        {
            "layer": "static",
            "version_id": snap.get("static_rules_version"),
            "precedence": 3,
            "description": "Static runtime rules and voice defaults",
        },
    ]
    if redacted:
        text = compiled_brain_service.redacted_preview(text)
    return {
        "agent_id": agent_id,
        "compiled_version": snap["compiled_version"],
        "checksum": snap["checksum"],
        "token_estimate": snap.get("token_estimate"),
        "layers": layers,
        "preview": text,
    }
