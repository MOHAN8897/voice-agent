"""Campaign dialer worker — Redis queue consumer scaffold."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_QUEUE_KEY = "voice_agent:campaign_jobs"
_redis_client: Any = None


def _redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis

        _redis_client = redis.from_url(url, decode_responses=True)
        return _redis_client
    except Exception as e:
        logger.warning("redis unavailable: %s", e)
        return None


def enqueue_campaign_run(campaign_id: str, run_id: str) -> bool:
    r = _redis()
    if r is None:
        logger.info("campaign run queued (no redis): %s %s", campaign_id, run_id)
        return False
    payload = json.dumps({"campaign_id": campaign_id, "run_id": run_id, "ts": time.time()})
    r.lpush(_QUEUE_KEY, payload)
    return True


def pop_job(timeout: int = 5) -> dict[str, Any] | None:
    r = _redis()
    if r is None:
        return None
    item = r.brpop(_QUEUE_KEY, timeout=timeout)
    if not item:
        return None
    _, raw = item
    return json.loads(raw)


def process_job(job: dict[str, Any]) -> None:
    campaign_id = job.get("campaign_id")
    run_id = job.get("run_id")
    logger.info("processing campaign job campaign_id=%s run_id=%s", campaign_id, run_id)
    # Exotel outbound dial would be initiated here via ExotelClient.connect_two_numbers


def run_loop() -> None:
    logger.info("worker dialer started")
    while True:
        job = pop_job(timeout=10)
        if job:
            try:
                process_job(job)
            except Exception as e:
                logger.exception("job failed: %s", e)
        else:
            time.sleep(1)
