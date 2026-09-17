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


def _mark_unavailable(exc: BaseException) -> None:
    global _CLIENT, _RETRY_AFTER
    _CLIENT = None
    _RETRY_AFTER = time.monotonic() + _RETRY_AFTER_SEC
    logger.warning(f"[REDIS] memory cache unavailable: {exc}")


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

            _CLIENT = redis.from_url(url, decode_responses=True,
                                     socket_connect_timeout=0.25, socket_timeout=0.25)
            _CLIENT.ping()
        except Exception as e:
            _mark_unavailable(e)
            return None
    return _CLIENT


def cache_enabled() -> bool:
    return _redis() is not None


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
