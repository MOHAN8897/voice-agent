"""Optional Redis cache for active-call working memory (reduces disk reads, multi-worker ready)."""
from __future__ import annotations

import json
import time
from typing import Any

from server.config.env import get_settings
from server.utils.logger import logger

_CLIENT = None
_RETRY_AFTER = 0.0
_PREFIX = "voice:call:memory:"
_TTL_SEC = 7200
_RETRY_AFTER_SEC = 60.0
# Reason the cache was last dropped, and whether we have already told the operator.
# Repeating the same warning every retry buries real PSTN events under a wall of
# identical lines, and "timeout connecting to server" does not say what to fix.
_LAST_FAILURE_REASON: str | None = None
_FAILURE_REPORTED = False


def _mark_unavailable(exc: BaseException) -> None:
    global _CLIENT, _RETRY_AFTER, _LAST_FAILURE_REASON, _FAILURE_REPORTED
    _CLIENT = None
    _RETRY_AFTER = time.monotonic() + _RETRY_AFTER_SEC
    reason = f"{type(exc).__name__}: {str(exc)[:120]}"
    if reason != _LAST_FAILURE_REASON:
        _LAST_FAILURE_REASON = reason
        _FAILURE_REPORTED = False
    if not _FAILURE_REPORTED:
        _FAILURE_REPORTED = True
        url = get_settings().redis_url
        logger.warning(
            "[REDIS] memory cache disabled — %s. Configured REDIS_URL=%s; "
            "calls fall back to Postgres, so nothing is lost, but every cache "
            "read pays a %.1fs connect timeout. Start Redis or unset REDIS_URL. "
            "Further identical failures are suppressed for %ds.",
            reason,
            url or "(unset)",
            1.0,
            int(_RETRY_AFTER_SEC),
        )
    else:
        logger.debug("[REDIS] memory cache still unavailable: %s", reason)


def _redis():
    global _CLIENT, _RETRY_AFTER
    settings = get_settings()
    url = settings.redis_url
    if not url:
        return None
    if time.monotonic() < _RETRY_AFTER:
        return None
    if _CLIENT is None:
        try:
            import redis

            _CLIENT = redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=0.75,
            )
            _CLIENT.ping()
        except Exception as e:
            _mark_unavailable(e)
            return None
    return _CLIENT


def cache_enabled() -> bool:
    return _redis() is not None


def cache_diagnostic() -> dict[str, Any]:
    """Why the cache is off, for diagnostics surfaces that should not guess."""
    return {
        "enabled": _redis() is not None,
        "configured": bool(get_settings().redis_url),
        "lastFailure": _LAST_FAILURE_REASON,
    }


def get_snapshot(call_id: str) -> dict[str, Any] | None:
    client = _redis()
    if not client:
        return None
    try:
        raw = client.get(f"{_PREFIX}{call_id}")
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning(f"[REDIS] get memory {call_id[:8]}: {e}")
        _mark_unavailable(e)
    return None


def set_snapshot(call_id: str, snapshot: dict[str, Any]) -> None:
    client = _redis()
    if not client:
        return
    try:
        client.setex(f"{_PREFIX}{call_id}", _TTL_SEC, json.dumps(snapshot))
    except Exception as e:
        logger.warning(f"[REDIS] set memory {call_id[:8]}: {e}")
        _mark_unavailable(e)


def delete_snapshot(call_id: str) -> None:
    client = _redis()
    if not client:
        return
    try:
        client.delete(f"{_PREFIX}{call_id}")
    except Exception:
        pass
