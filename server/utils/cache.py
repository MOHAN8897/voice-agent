"""
Read-through JSON cache in Redis — server/utils/cache.py

For hot, rarely changing reads (the public price catalog): ``cached_json(key, ttl,
produce)`` returns the cached value or computes, stores and returns it. Writers call
``invalidate(key)`` after saving so readers see the change at once. Redis is optional:
when it is not configured or not reachable, every call simply computes (and Redis is
not retried for 30s), so an outage costs speed, never correctness.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

_RETRY_S = 30.0

#: The public price catalog (/api/billing/catalog). Saving rates, tax settings, pricing
#: tags or a tier's price clears it.
BILLING_CATALOG_KEY = "billing:catalog:v1"
_state: dict[str, Any] = {"client": None, "down_until": 0.0}


async def _client():
    if os.getenv("CACHE_BACKEND", os.getenv("RATE_LIMIT_BACKEND", "")).lower() == "memory":
        return None
    if _state["client"] is not None:
        return _state["client"]
    if time.monotonic() < _state["down_until"]:
        return None
    try:
        from server.config.env import get_settings

        url = get_settings().redis_url or os.getenv("REDIS_URL")
        if not url:
            _state["down_until"] = float("inf")
            return None
        import redis.asyncio as aioredis

        client = aioredis.from_url(url, socket_connect_timeout=0.3, socket_timeout=0.2)
        await asyncio.wait_for(client.ping(), timeout=0.4)
        _state["client"] = client
        return client
    except Exception:
        _state["down_until"] = time.monotonic() + _RETRY_S
        return None


def _down() -> None:
    _state.update(client=None, down_until=time.monotonic() + _RETRY_S)


async def cached_json(key: str, ttl_s: int, produce: Callable[[], Awaitable[Any]]) -> Any:
    client = await _client()
    if client is not None:
        try:
            raw = await client.get(f"cache:{key}")
            if raw is not None:
                return json.loads(raw)
        except Exception:
            _down()
            client = None
    value = await produce()
    if client is not None:
        try:
            await client.set(f"cache:{key}", json.dumps(value, default=str), ex=ttl_s)
        except Exception:
            _down()
    return value


async def invalidate(*keys: str) -> None:
    client = await _client()
    if client is None:
        return
    try:
        await client.delete(*[f"cache:{key}" for key in keys])
    except Exception:
        logger.warning("cache invalidation failed for %s", keys)
        _down()
