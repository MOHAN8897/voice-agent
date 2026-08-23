"""
Metrics — server/utils/metrics.py
In-memory latency & error tracking, p50/p95, thread-safe.
Industry standard: /api/metrics exposes perf without leaking PII.
"""
from __future__ import annotations

import threading
import time
from collections import Counter, deque


def _percentile(data: list[float], p: float) -> float | None:
    if not data:
        return None
    s = sorted(data)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(s):
        return float(s[-1])
    d0 = s[f] * (c - k)
    d1 = s[c] * (k - f)
    return float(d0 + d1)

class Metrics:
    def __init__(self, max_samples: int = 500):
        self._lock = threading.RLock()
        self._stt: deque[float] = deque(maxlen=max_samples)
        self._brain: deque[float] = deque(maxlen=max_samples)
        self._tts: deque[float] = deque(maxlen=max_samples)
        self._e2e: deque[float] = deque(maxlen=max_samples)
        self._errors: Counter = Counter()
        self._total_turns: int = 0
        self._rate_limited: int = 0
        self._start = time.time()

    def record_turn(self, stt_ms: int, brain_ms: int, tts_ms: int, e2e_ms: int) -> None:
        with self._lock:
            self._stt.append(float(stt_ms))
            self._brain.append(float(brain_ms))
            self._tts.append(float(tts_ms))
            self._e2e.append(float(e2e_ms))
            self._total_turns += 1

    def record_error(self, provider: str, code: str) -> None:
        with self._lock:
            self._errors[f"{provider}:{code}"] += 1

    def record_rate_limited(self) -> None:
        with self._lock:
            self._rate_limited += 1

    def snapshot(self) -> dict:
        with self._lock:
            def stats(d: deque):
                lst = list(d)
                if not lst:
                    return {"count": 0, "p50": None, "p95": None, "avg": None, "min": None, "max": None}
                return {
                    "count": len(lst),
                    "p50": round(_percentile(lst, 50) or 0, 1),
                    "p95": round(_percentile(lst, 95) or 0, 1),
                    "avg": round(sum(lst) / len(lst), 1),
                    "min": round(min(lst), 1),
                    "max": round(max(lst), 1),
                }
            return {
                "uptime_s": round(time.time() - self._start, 1),
                "total_turns": self._total_turns,
                "stt_ms": stats(self._stt),
                "brain_ms": stats(self._brain),
                "tts_ms": stats(self._tts),
                "e2e_ms": stats(self._e2e),
                "errors": dict(self._errors),
                "rate_limited": self._rate_limited,
            }

    def reset(self) -> None:
        with self._lock:
            self._stt.clear(); self._brain.clear(); self._tts.clear(); self._e2e.clear()
            self._errors.clear(); self._total_turns = 0; self._rate_limited = 0

metrics = Metrics()
