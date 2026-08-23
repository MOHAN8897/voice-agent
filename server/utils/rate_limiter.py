"""
Rate limiter — server/utils/rate_limiter.py
Simple sliding-window per IP, thread-safe, no extra deps.
Industry standard: fail open on error, 429 with Retry-After.
"""
from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_requests: int = 60, window_s: int = 60):
        self.max_requests = max_requests
        self.window_s = window_s
        self._store: dict[str, deque[float]] = {}
        self._lock = threading.RLock()

    def allow(self, key: str) -> tuple[bool, int]:
        """
        Returns (allowed, retry_after_seconds)
        """
        now = time.time()
        with self._lock:
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

# Global limiter: 60 req/min per IP (generous for voice turns ~ 10-15 per minute, protects TTS/Brain bursts)
rate_limiter = RateLimiter(max_requests=60, window_s=60)
# Stricter for TTS/voice: 20/min
tts_limiter = RateLimiter(max_requests=20, window_s=60)
