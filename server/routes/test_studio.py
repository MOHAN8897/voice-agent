"""Test Studio session preferences — stack UI state persisted across restarts."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from server.services.cartesia_voices import (
    fetch_cartesia_voices,
    voices_for_catalog,
    voices_grouped_for_ui,
)
from server.services.session_persist import session_persist

router = APIRouter()


class TestStudioUiPrefs(BaseModel):
    sessionId: str = Field("test-studio", max_length=100)
    stackMode: str | None = None
    tier: str | None = None
    channel: str | None = None
    language: str | None = None
    stack: dict | None = None
    fineTuneTab: str | None = None


@router.get("/api/test-studio/prefs")
async def get_test_studio_prefs(sessionId: str = "test-studio"):
    return {"sessionId": sessionId, "prefs": session_persist.get_ui(sessionId)}


@router.post("/api/test-studio/prefs")
async def save_test_studio_prefs(body: TestStudioUiPrefs):
    patch = {
        k: v
        for k, v in body.model_dump().items()
        if k != "sessionId" and v is not None
    }
    existing = session_persist.get_ui(body.sessionId)
    existing.update(patch)
    session_persist.set_ui(body.sessionId, existing)
    return {"ok": True, "sessionId": body.sessionId, "prefs": existing}


@router.get("/api/settings/cartesia-voices")
async def list_cartesia_voices(refresh: bool = False):
    await fetch_cartesia_voices(force=refresh)
    groups = voices_grouped_for_ui()
    voices = voices_for_catalog()
    return {
        "voices": voices,
        "groups": groups,
        "count": len(voices),
        "source": groups.get("source", "static"),
    }
