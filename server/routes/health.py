"""
Health routes — server/routes/health.py
No secrets leaked.
"""
from __future__ import annotations

from fastapi import APIRouter

from server.config.constants import constants
from server.config.env import ConfigError, config_presence, get_settings

router = APIRouter()


@router.get("/api/health")
async def health():
    try:
        settings = get_settings()
        # Trigger validation without leaking values
        _ = settings.openai_api_key
        _ = settings.sarvam_api_key
        env_valid = True
        error = None
    except ConfigError as e:
        env_valid = False
        error = str(e)
    except Exception as e:
        env_valid = False
        error = str(e)[:300]

    presence = config_presence()
    return {
        "ok": env_valid,
        "envValid": env_valid,
        "version": constants.APP_VERSION,
        "presence": presence,  # booleans only
        "error": error,
        "supportedLanguages": list(constants.SUPPORTED_LANGUAGES.keys()),
    }


@router.get("/api/config-check")
async def config_check():
    presence = config_presence()
    try:
        _ = get_settings()
        valid = True
        message = "Configuration valid"
    except ConfigError as e:
        valid = False
        message = str(e)
    return {"valid": valid, "presence": presence, "message": message}
