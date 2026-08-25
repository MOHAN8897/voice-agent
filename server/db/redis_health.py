"""Redis health check — optional."""
from __future__ import annotations

from typing import Any

from server.config.env import get_settings


async def check_redis_health() -> dict[str, Any]:
    settings = get_settings()
    url = settings.redis_url or __import__("os").getenv("REDIS_URL")
    if not url:
        return {"ok": False, "configured": False, "message": "REDIS_URL not set"}
    try:
        import redis

        client = redis.from_url(url, decode_responses=True)
        client.ping()
        return {"ok": True, "configured": True, "message": "connected"}
    except Exception as e:
        return {"ok": False, "configured": True, "message": str(e)[:200]}
