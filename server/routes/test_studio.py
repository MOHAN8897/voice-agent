"""Test Studio session preferences — stack UI state persisted across restarts."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from server.services.cartesia_voices import fetch_cartesia_voices
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
    studioTab: str | None = None
    saveConfig: bool = False
    stackOverride: dict | None = None


@router.get("/api/test-studio/prefs")
async def get_test_studio_prefs(sessionId: str = "test-studio"):
    return {"sessionId": sessionId, "prefs": session_persist.get_ui(sessionId)}


@router.post("/api/test-studio/prefs")
async def save_test_studio_prefs(body: TestStudioUiPrefs):
    patch = {
        k: v
        for k, v in body.model_dump().items()
        if k not in {"sessionId", "saveConfig", "stackOverride"} and v is not None
    }
    existing = session_persist.get_ui(body.sessionId)
    existing.update(patch)
    runtime_patch = {}
    if body.saveConfig:
        from server.services.runtime_settings import runtime_settings, SettingsValidationError
        from fastapi import HTTPException

        form = body.stack or {}
        pipeline = ""
        if isinstance(body.stackOverride, dict):
            pipeline = str(body.stackOverride.get("pipeline") or "").strip()
        if pipeline == "realtime_voice":
            runtime_patch = {}
            llm_model = str(form.get("llmModel") or "").strip()
            if not llm_model.startswith("gpt-realtime"):
                llm_model = "gpt-realtime-2.1-mini"
            runtime_patch["openaiModel"] = llm_model
        else:
            runtime_patch = {key: form[field] for field, key in (
                ("ttsVoiceId", "ttsSpeaker"), ("ttsModel", "ttsModel"),
                ("sttModel", "sttModel"), ("sttMode", "sttMode"),
                ("sttStreamType", "sttStreamType"),
            ) if form.get(field)}
        try:
            if runtime_patch:
                runtime_settings.update(body.sessionId, runtime_patch)
        except SettingsValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        existing["callConfig"] = {
            "tier": body.tier,
            "language": body.language,
            "stack_override": body.stackOverride,
        }
    session_persist.set_ui(body.sessionId, existing)
    return {"ok": True, "sessionId": body.sessionId, "prefs": existing, "runtimePatch": runtime_patch}


@router.get("/api/settings/cartesia-voices")
async def list_cartesia_voices(refresh: bool = False):
    await fetch_cartesia_voices(force=refresh)
    from server.config.constants import constants
    from server.services import cartesia_voices as cv

    groups = cv.voices_grouped_for_ui()
    voices = cv.voices_for_catalog()
    return {
        "voices": voices,
        "groups": groups,
        "count": len(voices),
        "source": groups.get("source", "static"),
        "defaultVoiceId": constants.CARTESIA_DEFAULT_VOICE_ID,
    }
