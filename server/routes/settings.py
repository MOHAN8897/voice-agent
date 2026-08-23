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
from server.utils.log_config import get_log_flags
from server.prompts.voice_defaults import (
    DEFAULT_BEHAVIOUR_INSTRUCTIONS,
    DEFAULT_BUSINESS_INSTRUCTIONS,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_RESPONSE_STYLE,
    OPENAI_MODEL_CATALOG,
    OPENAI_MODEL_IDS,
)
from server.services.runtime_settings import runtime_settings, SettingsValidationError
from server.services.tts_config import resolve_tts_config

router = APIRouter()


@router.get("/api/settings/catalog")
async def catalog():
    """Everything the console needs to render selects/sliders."""
    try:
        s = get_settings()
        allowed_models = [m for m in s.allowed_openai_models if m in OPENAI_MODEL_IDS] or OPENAI_MODEL_IDS
        current_openai = s.openai_model if s.openai_model in allowed_models else allowed_models[0]
        log_flags = get_log_flags()
        voice_cfg = {
            "httpTtsFallback": s.voice_http_tts_fallback,
            "persistentTtsWs": True,
        }
    except Exception:
        allowed_models, current_openai = OPENAI_MODEL_IDS, OPENAI_MODEL_IDS[0]
        log_flags = {"enabled": True, "client": True, "perf": True}
        voice_cfg = {"httpTtsFallback": False, "persistentTtsWs": True}
    model_labels = {m["id"]: m["label"] for m in OPENAI_MODEL_CATALOG}
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
            "modelLabels": model_labels,
            "currentModel": current_openai,
            "defaultModel": DEFAULT_OPENAI_MODEL,
            "temperature": [0.0, 2.0],
            "maxTokens": [50, 800],
            "modelGroups": [
                {"label": "GPT-5 family (voice-tuned)", "models": allowed_models},
            ],
            "defaults": {
                "openaiModel": "gpt-5.6-luna",
                "openaiMaxTokens": 320,
                "openaiTemperature": 0.7,
                "responseStyle": DEFAULT_RESPONSE_STYLE,
                "behaviourInstructions": DEFAULT_BEHAVIOUR_INSTRUCTIONS,
                "businessInstructions": DEFAULT_BUSINESS_INSTRUCTIONS,
                "ttsMinBuffer": 30,
                "ttsMaxChunk": 80,
                "ttsPace": 1.08,
                "ttsTemperature": 0.4,
            },
            "note": "API keys stay server-side in .env. GPT-5.6 Luna = fastest for live voice; GPT-5.5 = highest quality.",
        },
        "voice": voice_cfg,
        "logging": log_flags,
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
    crmEnabled: Optional[bool] = None
    crmProvider: Optional[str] = None
    crmWebhook: Optional[str] = None
    crmFields: Optional[str] = None
    crmNotes: Optional[str] = None
    crmAutoSync: Optional[bool] = None


@router.get("/api/settings/runtime")
async def get_runtime(sessionId: str = Query("default")):
    values = runtime_settings.get(sessionId)
    try:
        s = get_settings()
        defaults = {
            "sttModel": s.sarvam_stt_model,
            "ttsModel": s.sarvam_tts_model,
            "ttsSpeaker": s.sarvam_tts_speaker_te,
            "ttsPace": s.sarvam_tts_pace,
            "openaiModel": s.openai_model,
            "openaiMaxTokens": s.max_response_length,
        }
    except Exception:
        defaults = {}
    return {"sessionId": sessionId, "values": values, "defaults": defaults}


@router.get("/api/settings/tts-config")
async def get_tts_config(sessionId: str = Query("default"), language_code: str = Query("te-IN")):
    """Resolved canonical TTS config for a session — same object used by REST + WS + voice turn."""
    try:
        cfg = resolve_tts_config(sessionId, language_code=language_code)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": {"code": "validation_error", "message": str(e)}}) from e
    return {"sessionId": sessionId, "ttsConfig": cfg}


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
