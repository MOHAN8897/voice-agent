"""
Rate limiter — server/utils/rate_limiter.py
Sliding window per key. Shared through Redis when REDIS_URL is set, so every worker
and every server counts against the same limit and a restart does not reset it; falls
back to a bounded in-process window when Redis is unreachable (and under tests, where
RATE_LIMIT_BACKEND=memory), so a Redis outage never takes sign-in down with it.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid
import weakref
from collections import deque

# Atomic sliding window: drop entries older than the window, count, admit or report
# how long until the oldest entry slides out. Times are wall-clock milliseconds so
# every process agrees.
_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
if redis.call('ZCARD', key) < limit then
  redis.call('ZADD', key, now, ARGV[4])
  redis.call('PEXPIRE', key, window)
  return {1, 0}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
return {0, math.ceil((tonumber(oldest[2]) + window - now) / 1000)}
"""

_redis_lock = threading.Lock()
_redis_state: dict = {"client": None, "script": None, "retry_at": 0.0, "connecting": False}
_REDIS_RETRY_S = 30.0
_names: dict[str, int] = {}
#: Every limiter, so tests can give each one a fresh window (reset_all).
_instances: "weakref.WeakSet[RateLimiter]" = weakref.WeakSet()


def _connect() -> None:
    state = _redis_state
    try:
        from server.config.env import get_settings

        url = get_settings().redis_url or os.getenv("REDIS_URL")
        if not url:
            return
        import redis

        client = redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.1)
        client.ping()
        state["script"] = client.register_script(_SLIDING_WINDOW)
        state["client"] = client
    except Exception:
        pass
    finally:
        state["connecting"] = False


def _redis():
    """The shared client, or None: not configured, under tests, or down. Connecting (and
    reconnecting, every 30s while down) happens on a background thread, so a request
    never waits on it; until then limits count in-process."""
    if os.getenv("RATE_LIMIT_BACKEND", "").lower() == "memory":
        return None
    state = _redis_state
    if state["client"] is not None:
        return state
    now = time.monotonic()
    if now >= state["retry_at"] and not state["connecting"]:
        with _redis_lock:
            if not state["connecting"] and now >= state["retry_at"]:
                state["connecting"] = True
                state["retry_at"] = now + _REDIS_RETRY_S
                threading.Thread(target=_connect, name="rate-limit-redis", daemon=True).start()
    return None


def _redis_failed() -> None:
    _redis_state.update(client=None, script=None, retry_at=time.monotonic() + _REDIS_RETRY_S)


class RateLimiter:
    def __init__(self, max_requests: int = 60, window_s: int = 60, max_keys: int = 10000, name: str | None = None):
        self.max_requests = max_requests
        self.window_s = window_s
        self.max_keys = max_keys
        if name is None:
            # Stable across processes: the defining module, the limits, and its order there.
            module = sys._getframe(1).f_globals.get("__name__", "app")
            base = f"{module}:{max_requests}/{window_s}"
            _names[base] = _names.get(base, 0) + 1
            name = f"{base}#{_names[base]}"
        self.name = name
        _instances.add(self)
        self._last_prune = 0.0
        self._store: dict[str, deque[float]] = {}
        self._lock = threading.RLock()

    def allow(self, key: str) -> tuple[bool, int]:
        """
        Returns (allowed, retry_after_seconds)
        """
        shared = _redis()
        if shared is not None:
            try:
                now_ms = int(time.time() * 1000)
                allowed, retry = shared["script"](
                    keys=[f"rl:{self.name}:{key}"],
                    args=[now_ms, self.window_s * 1000, self.max_requests, f"{now_ms}-{uuid.uuid4().hex[:8]}"],
                )
                return bool(int(allowed)), max(int(retry), 0 if int(allowed) else 1)
            except Exception:
                _redis_failed()
        return self._allow_local(key)

    def _allow_local(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            if now - self._last_prune >= min(self.window_s, 30):
                self._store = {k: q for k, q in self._store.items() if q and now - q[-1] < self.window_s}
                self._last_prune = now
            if key not in self._store and len(self._store) >= self.max_keys:
                # Full: forget the oldest key rather than refuse every newcomer, or anyone
                # able to mint 10,000 keys (rotating emails or IPv6 addresses) locks
                # everybody out.
                self._store.pop(next(iter(self._store)))
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
        shared = _redis()
        if shared is not None:
            try:
                for stale in shared["client"].scan_iter(match=f"rl:{self.name}:*", count=500):
                    shared["client"].delete(stale)
            except Exception:
                _redis_failed()

def reset_all() -> None:
    """Fresh windows for every limiter (tests)."""
    for limiter in list(_instances):
        limiter.reset()


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
