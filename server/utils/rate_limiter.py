"""
Rate limiter — server/utils/rate_limiter.py
Simple sliding-window per IP, thread-safe, no extra deps.
Process-local limits with bounded state; shared deployments also need edge limits.
"""
from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_requests: int = 60, window_s: int = 60, max_keys: int = 10000):
        self.max_requests = max_requests
        self.window_s = window_s
        self.max_keys = max_keys
        self._last_prune = 0.0
        self._store: dict[str, deque[float]] = {}
        self._lock = threading.RLock()

    def allow(self, key: str) -> tuple[bool, int]:
        """
        Returns (allowed, retry_after_seconds)
        """
        now = time.monotonic()
        with self._lock:
            if now - self._last_prune >= min(self.window_s, 30):
                self._store = {k: q for k, q in self._store.items() if q and now - q[-1] < self.window_s}
                self._last_prune = now
            if key not in self._store and len(self._store) >= self.max_keys:
                return False, max(1, self.window_s)
            q = self._store.setdefault(key, deque())
            # Evict old
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) < self.max_requests:
                q.append(now)
                return True, 0
            # need to wait until oldest slides out
            oldest = q[0]
            retry_after = int(oldest + self.window_s - now) + 1
            return False, max(retry_after, 1)

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
            self._last_prune = 0.0

# Global limiter: 60 req/min per IP (generous for voice turns ~ 10-15 per minute, protects TTS/Brain bursts)
rate_limiter = RateLimiter(max_requests=60, window_s=60)
# Stricter for TTS/voice: 20/min
tts_limiter = RateLimiter(max_requests=20, window_s=60)


def raise_rate_limited(retry_after: int, message: str = "Too many requests") -> None:
    from fastapi import HTTPException

    retry = max(1, int(retry_after or 1))
    raise HTTPException(
        status_code=429,
        detail={
            "error": {
                "code": "rate_limit",
                "message": message,
                "retry_after": retry,
            }
        },
        headers={"Retry-After": str(retry)},
    )
