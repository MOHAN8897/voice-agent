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
        self._brain_input: deque[int] = deque(maxlen=max_samples)
        self._brain_output: deque[int] = deque(maxlen=max_samples)
        self._brain_cached: deque[int] = deque(maxlen=max_samples)
        self._brain_cache_writes: deque[int] = deque(maxlen=max_samples)
        self._brain_calls: int = 0
        self._cache_hits: int = 0
        self._cache_writes: int = 0
        self._brain_layer_totals: dict[str, int] = {
            "brain": 0,
            "history": 0,
            "summary": 0,
            "transcript": 0,
            "samples": 0,
        }
        self._brain_ttft: deque[float] = deque(maxlen=max_samples)
        self._brain_prep_ms: deque[float] = deque(maxlen=max_samples)
        self._first_turn_ttft: deque[float] = deque(maxlen=50)
        self._steady_turn_ttft: deque[float] = deque(maxlen=max_samples)
        self._recent_turns: deque[dict] = deque(maxlen=50)

    def record_brain_turn(
        self,
        *,
        call_id: str,
        turn: int,
        usage: dict,
        layers: dict | None = None,
        ttft_ms: int | None = None,
        total_ms: int | None = None,
        prep_ms: int | None = None,
        request_id: str | None = None,
        cache_key: str | None = None,
        cache_event: str | None = None,
        model: str | None = None,
    ) -> None:
        """Record one structured brain turn for dashboard / diagnostics."""
        if not usage:
            return
        inp = int(usage.get("input_tokens", 0) or 0)
        out = int(usage.get("output_tokens", 0) or 0)
        cached = int(usage.get("cached_tokens", 0) or 0)
        cache_write = int(usage.get("cache_write_tokens", 0) or 0)
        uncached = max(0, inp - cached)
        layer = layers or {}
        turn_rec = {
            "call": call_id,
            "turn": turn,
            "input_tokens": inp,
            "cached_tokens": cached,
            "uncached_tokens": uncached,
            "cache_write_tokens": cache_write,
            "output_tokens": out,
            "brain_tokens_est": int(layer.get("brain", 0) or 0),
            "history_tokens_est": int(layer.get("history", 0) or 0),
            "transcript_tokens_est": int(layer.get("transcript", 0) or 0),
            "summary_tokens_est": int(layer.get("summary", 0) or 0),
            "ttft_ms": ttft_ms,
            "total_ms": total_ms,
            "prep_ms": prep_ms,
            "request_id": request_id,
            "cache_key": cache_key,
            "cache_event": cache_event,
            "model": model,
            "cache_ratio": round(cached / inp, 4) if inp > 0 else None,
        }
        with self._lock:
            self._recent_turns.append(turn_rec)
            if ttft_ms is not None:
                self._brain_ttft.append(float(ttft_ms))
                if turn <= 1:
                    self._first_turn_ttft.append(float(ttft_ms))
                else:
                    self._steady_turn_ttft.append(float(ttft_ms))
            if prep_ms is not None:
                self._brain_prep_ms.append(float(prep_ms))

    def record_brain_tokens(self, usage: dict, *, layers: dict | None = None) -> None:
        if not usage:
            return
        with self._lock:
            self._brain_calls += 1
            inp = int(usage.get("input_tokens", 0) or 0)
            out = int(usage.get("output_tokens", 0) or 0)
            cached = int(usage.get("cached_tokens", 0) or 0)
            writes = int(usage.get("cache_write_tokens", 0) or 0)
            self._brain_input.append(inp)
            self._brain_output.append(out)
            self._brain_cached.append(cached)
            self._brain_cache_writes.append(writes)
            if cached > 0:
                self._cache_hits += 1
            if writes > 0:
                self._cache_writes += 1
            if layers:
                self._brain_layer_totals["samples"] += 1
                for key in ("brain", "history", "summary", "transcript"):
                    self._brain_layer_totals[key] += int(layers.get(key, 0) or 0)

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
            def int_stats(d: deque):
                lst = [int(x) for x in d]
                if not lst:
                    return {"count": 0, "p50": None, "p95": None, "avg": None}
                return {
                    "count": len(lst),
                    "p50": int(_percentile(lst, 50) or 0),
                    "p95": int(_percentile(lst, 95) or 0),
                    "avg": round(sum(lst) / len(lst), 1),
                }

            brain_calls = self._brain_calls
            cache_hit_rate = round(self._cache_hits / brain_calls, 3) if brain_calls else 0.0
            cache_write_rate = round(self._cache_writes / brain_calls, 3) if brain_calls else 0.0
            layer_samples = self._brain_layer_totals.get("samples", 0)
            layer_avg = {}
            if layer_samples:
                for key in ("brain", "history", "summary", "transcript"):
                    layer_avg[key] = round(self._brain_layer_totals[key] / layer_samples, 1)

            return {
                "uptime_s": round(time.time() - self._start, 1),
                "total_turns": self._total_turns,
                "stt_ms": stats(self._stt),
                "brain_ms": stats(self._brain),
                "tts_ms": stats(self._tts),
                "e2e_ms": stats(self._e2e),
                "brain_ttft_ms": stats(self._brain_ttft),
                "brain_prep_ms": stats(self._brain_prep_ms),
                "first_turn_ttft_ms": stats(self._first_turn_ttft),
                "steady_turn_ttft_ms": stats(self._steady_turn_ttft),
                "brain_tokens": {
                    "calls": brain_calls,
                    "input": int_stats(self._brain_input),
                    "output": int_stats(self._brain_output),
                    "cached": int_stats(self._brain_cached),
                    "cache_write": int_stats(self._brain_cache_writes),
                    "cache_hit_rate": cache_hit_rate,
                    "cache_write_rate": cache_write_rate,
                    "layer_avg_est": layer_avg,
                },
                "recent_brain_turns": list(self._recent_turns),
                "errors": dict(self._errors),
                "rate_limited": self._rate_limited,
            }

    def reset(self) -> None:
        with self._lock:
            self._stt.clear(); self._brain.clear(); self._tts.clear(); self._e2e.clear()
            self._errors.clear(); self._total_turns = 0; self._rate_limited = 0
            self._brain_input.clear(); self._brain_output.clear()
            self._brain_cached.clear(); self._brain_cache_writes.clear()
            self._brain_calls = 0; self._cache_hits = 0; self._cache_writes = 0
            self._brain_layer_totals = {
                "brain": 0, "history": 0, "summary": 0, "transcript": 0, "samples": 0,
            }
            self._brain_ttft.clear()
            self._brain_prep_ms.clear()
            self._first_turn_ttft.clear()
            self._steady_turn_ttft.clear()
            self._recent_turns.clear()

metrics = Metrics()
