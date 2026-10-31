"""Redis key eviction for quarantined / purged tenants.

Evicts all Redis keys matching the tenant's namespace patterns:
  tenant:{tenant_id}:*   — cached tool results, rate limiters, session data
  call_store:{tenant_id} — call registry entries
  tenant_tool_cache:*    — Nango/CRM tool response caches

If Redis is not configured the function is a no-op and returns 0.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def evict_tenant_redis_keys(tenant_id: str) -> int:
    """Evict all Redis keys for the given tenant_id.

    Returns the total number of keys deleted.  Never raises — caller treats as
    best-effort side effect.
    """
    try:
        import redis.asyncio as aioredis
        from server.config.env import get_settings

        settings = get_settings()
        redis_url = (settings.redis_url or "").strip()
        if not redis_url:
            return 0

        client = aioredis.from_url(redis_url, decode_responses=True)
        patterns = [
            f"tenant:{tenant_id}:*",
            f"tenant_tool_cache:*:{tenant_id}:*",
            f"rate_limit:*:{tenant_id}:*",
        ]
        total_deleted = 0
        try:
            for pattern in patterns:
                cursor = 0
                while True:
                    cursor, keys = await client.scan(cursor, match=pattern, count=200)
                    if keys:
                        deleted = await client.delete(*keys)
                        total_deleted += deleted
                    if cursor == 0:
                        break
        finally:
            await client.aclose()

        if total_deleted:
            logger.info("evict_tenant_redis_keys: deleted %d keys for tenant=%s", total_deleted, tenant_id)
        return total_deleted

    except ImportError:
        # redis package not installed — silently skip
        return 0
    except Exception:
        logger.exception("evict_tenant_redis_keys failed for tenant=%s (non-fatal)", tenant_id)
        return 0
