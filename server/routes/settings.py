"""
Settings routes — server/routes/settings.py
Fine-tune console backend: catalog + per-session runtime overrides.
Keys never settable from UI (stay in .env server-side) — industry standard.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from server.config.constants import constants
from server.config.env import get_settings
from server.services.runtime_settings import runtime_settings, SettingsValidationError

router = APIRouter()


@router.get("/api/settings/catalog")
async def catalog():
    """Everything the console needs to render selects/sliders."""
    try:
        s = get_settings()
        allowed_models = s.allowed_openai_models
        current_openai = s.openai_model
    except Exception:
        allowed_models, current_openai = [], "unknown"
    return {
        "stt": {
            "models": [{"id": k, "label": v["label"], "modes": v["modes"]} for k, v in constants.STT_MODELS.items()],
            "modes": constants.STT_MODES,
            "streamTypes": constants.STT_STREAM_TYPES,
            "languages": list(constants.SUPPORTED_LANGUAGES.keys()) + ["unknown"],
            "vad": {"silenceMs": [100, 2000], "threshold": [0.0, 1.0]},
        },
        "tts": {
            "models": [{"id": k, "label": v["label"], "pace": v["pace"], "temperature": v["temperature"]} for k, v in constants.TTS_MODELS.items()],
            "speakersV3": constants.TTS_SPEAKERS_V3,
            "speakersV2": constants.TTS_SPEAKERS_V2,
            "codecs": constants.TTS_CODECS,
            "bitrates": constants.TTS_BITRATES,
            "sampleRates": constants.TTS_SAMPLE_RATES,
        },
        "openai": {
            "allowedModels": allowed_models,
            "currentModel": current_openai,
            "temperature": [0.0, 2.0],
            "maxTokens": [50, 4000],
            "note": "API keys stay server-side in .env — never enter them in the browser.",
        },
    }


class RuntimePatch(BaseModel):
    model_config = {"extra": "forbid"}  # reject unknown settings loudly (industry: fail closed)

    sessionId: str = Field("default", max_length=100)
    sttModel: Optional[str] = None
    sttMode: Optional[str] = None
    sttLanguage: Optional[str] = None
    sttStreamType: Optional[str] = None
    sttSilenceMs: Optional[int] = None
    sttThreshold: Optional[float] = None
    ttsModel: Optional[str] = None
    ttsSpeaker: Optional[str] = None
    ttsPace: Optional[float] = None
    ttsTemperature: Optional[float] = None
    ttsCodec: Optional[str] = None
    ttsBitrate: Optional[str] = None
    ttsSampleRate: Optional[int] = None
    ttsMinBuffer: Optional[int] = None
    ttsMaxChunk: Optional[int] = None
    openaiModel: Optional[str] = None
    openaiTemperature: Optional[float] = None
    openaiMaxTokens: Optional[int] = None


@router.get("/api/settings/runtime")
async def get_runtime(sessionId: str = Query("default")):
    values = runtime_settings.get(sessionId)
    try:
        defaults = {
            "sttModel": get_settings().sarvam_stt_model,
            "ttsModel": get_settings().sarvam_tts_model,
            "ttsSpeaker": get_settings().sarvam_tts_speaker_te,
            "ttsPace": get_settings().sarvam_tts_pace,
            "openaiModel": get_settings().openai_model,
            "openaiMaxTokens": get_settings().max_response_length,
        }
    except Exception:
        defaults = {}
    return {"sessionId": sessionId, "values": values, "defaults": defaults}


@router.post("/api/settings/runtime")
async def post_runtime(body: RuntimePatch):
    patch = {k: v for k, v in body.model_dump().items() if k != "sessionId"}
    if not patch:
        raise HTTPException(status_code=400, detail={"error": {"code": "validation_error", "message": "No settings provided"}})
    try:
        values = runtime_settings.update(body.sessionId, patch)
    except SettingsValidationError as e:
        raise HTTPException(status_code=400, detail={"error": {"code": "validation_error", "message": str(e)}}) from e
    except Exception as e:
        # e.g., get_settings() ConfigError inside openaiModel validation
        raise HTTPException(status_code=500, detail={"error": {"code": "config_error", "message": str(e)[:300]}}) from e
    return {"ok": True, "sessionId": body.sessionId, "values": values}


@router.delete("/api/settings/runtime")
async def delete_runtime(sessionId: str = Query("default")):
    runtime_settings.clear(sessionId)
    return {"ok": True, "sessionId": sessionId, "cleared": True}
