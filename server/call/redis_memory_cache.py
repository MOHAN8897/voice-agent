"""Optional Redis cache for active-call working memory (reduces disk reads, multi-worker ready)."""
from __future__ import annotations

import json
from typing import Any

from server.config.env import get_settings
from server.utils.logger import logger

_CLIENT = None
_PREFIX = "voice:call:memory:"
_TTL_SEC = 7200


def _redis():
    global _CLIENT
    settings = get_settings()
    url = settings.redis_url
    if not url:
        return None
    if _CLIENT is None:
        try:
            import redis

            _CLIENT = redis.from_url(url, decode_responses=True)
            _CLIENT.ping()
        except Exception as e:
            logger.warning(f"[REDIS] memory cache unavailable: {e}")
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
    return None


def set_snapshot(call_id: str, snapshot: dict[str, Any]) -> None:
    client = _redis()
    if not client:
        return
    try:
        client.setex(f"{_PREFIX}{call_id}", _TTL_SEC, json.dumps(snapshot))
    except Exception as e:
        logger.warning(f"[REDIS] set memory {call_id[:8]}: {e}")


def delete_snapshot(call_id: str) -> None:
    client = _redis()
    if not client:
        return
    try:
        client.delete(f"{_PREFIX}{call_id}")
    except Exception:
        pass
