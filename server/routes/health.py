"""
Health routes — server/routes/health.py
No secrets leaked.
"""
from __future__ import annotations

from fastapi import APIRouter

from server.config.constants import constants
from server.config.env import ConfigError, config_presence, get_settings
from server.db.connection import check_db_health
from server.db.redis_health import check_redis_health

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
    db_status: dict = {"ok": False, "configured": False, "message": "skipped"}
    redis_status: dict = {"ok": False, "configured": False, "message": "skipped"}
    if env_valid:
        try:
            db_status = await check_db_health()
        except Exception as e:
            db_status = {"ok": False, "configured": False, "message": str(e)[:200]}
        try:
            redis_status = await check_redis_health()
        except Exception as e:
            redis_status = {"ok": False, "configured": False, "message": str(e)[:200]}
    # Email delivery is invisible until someone needs a reset link, which is exactly
    # when it matters. Surface the deliverability verdict (booleans only) on health so
    # a broken sender domain shows up on a monitor instead of in a support ticket.
    try:
        from server.services.saas.email_service import email_provider_status

        # Probed, not just cached-read: the 5-minute TTL in email_service keeps this to
        # one Resend call per window no matter how often health is polled.
        email_status = await email_provider_status()
    except Exception as e:
        email_status = {
            "provider": "resend",
            "configured": False,
            "deliverable": False,
            "reason": "probe_error",
            "detail": str(e)[:200],
        }
    try:
        from server.services.r2_storage import r2_storage

        r2_configured = r2_storage.is_configured()
        r2_status = {
            "configured": r2_configured,
            "bucket": settings.r2_bucket_name if r2_configured else None,
        }
    except Exception as e:
        r2_status = {"configured": False, "error": str(e)[:120]}
    return {
        "ok": env_valid and (not db_status.get("configured") or db_status.get("ok")),
        "envValid": env_valid,
        "version": constants.APP_VERSION,
        "presence": presence,  # booleans only
        "database": db_status,
        "redis": redis_status,
        "r2": r2_status,
        "email": email_status,
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
