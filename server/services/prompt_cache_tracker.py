"""
Prompt cache tracker — diagnostics for cache hits, misses, and rewrites.

Tracks per-cache-key events to help explain OpenAI cache_write_tokens spikes.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass


@dataclass
class CacheEvent:
    cache_key: str
    session_id: str
    turn: int
    input_tokens: int
    cached_tokens: int
    cache_write_tokens: int
    request_id: str | None
    event: str  # hit | write | miss
    seconds_since_last_hit: float | None
    seconds_since_last_write: float | None
    turns_since_last_write: int | None
    global_turn: int


class PromptCacheTracker:
    """Thread-safe tracker for prompt cache behaviour across turns."""

    def __init__(self, max_events: int = 100):
        self._lock = threading.RLock()
        self._max_events = max_events
        self._events: list[CacheEvent] = []
        self._global_turn = 0
        self._per_key: dict[str, dict] = {}

    def _key_state(self, cache_key: str) -> dict:
        if cache_key not in self._per_key:
            self._per_key[cache_key] = {
                "last_hit_at": None,
                "last_write_at": None,
                "last_write_global_turn": None,
                "hits": 0,
                "writes": 0,
                "misses": 0,
            }
        return self._per_key[cache_key]

    def record(
        self,
        *,
        cache_key: str | None,
        session_id: str,
        turn: int,
        input_tokens: int,
        cached_tokens: int,
        cache_write_tokens: int,
        request_id: str | None = None,
    ) -> CacheEvent | None:
        if not cache_key:
            return None

        now = time.time()
        with self._lock:
            self._global_turn += 1
            state = self._key_state(cache_key)

            if cache_write_tokens > 0:
                event_type = "write"
                state["writes"] += 1
                turns_since = (
                    self._global_turn - state["last_write_global_turn"]
                    if state["last_write_global_turn"] is not None
                    else None
                )
                sec_since_hit = (
                    round(now - state["last_hit_at"], 2)
                    if state["last_hit_at"] is not None
                    else None
                )
                sec_since_write = (
                    round(now - state["last_write_at"], 2)
                    if state["last_write_at"] is not None
                    else None
                )
                state["last_write_at"] = now
                state["last_write_global_turn"] = self._global_turn
            elif cached_tokens > 0:
                event_type = "hit"
                state["hits"] += 1
                state["last_hit_at"] = now
                turns_since = None
                sec_since_hit = None
                sec_since_write = (
                    round(now - state["last_write_at"], 2)
                    if state["last_write_at"] is not None
                    else None
                )
            else:
                event_type = "miss"
                state["misses"] += 1
                turns_since = None
                sec_since_hit = (
                    round(now - state["last_hit_at"], 2)
                    if state["last_hit_at"] is not None
                    else None
                )
                sec_since_write = (
                    round(now - state["last_write_at"], 2)
                    if state["last_write_at"] is not None
                    else None
                )

            ev = CacheEvent(
                cache_key=cache_key,
                session_id=session_id,
                turn=turn,
                input_tokens=input_tokens,
                cached_tokens=cached_tokens,
                cache_write_tokens=cache_write_tokens,
                request_id=request_id,
                event=event_type,
                seconds_since_last_hit=sec_since_hit,
                seconds_since_last_write=sec_since_write,
                turns_since_last_write=turns_since,
                global_turn=self._global_turn,
            )
            self._events.append(ev)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events :]
            return ev

    def snapshot(self) -> dict:
        with self._lock:
            writes = [e for e in self._events if e.event == "write"]
            return {
                "global_turns": self._global_turn,
                "keys_tracked": len(self._per_key),
                "recent_writes": len(writes),
                "per_key": {
                    k: {
                        "hits": v["hits"],
                        "writes": v["writes"],
                        "misses": v["misses"],
                        "last_write_global_turn": v["last_write_global_turn"],
                    }
                    for k, v in self._per_key.items()
                },
                "recent_events": [asdict(e) for e in self._events[-20:]],
            }

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._per_key.clear()
            self._global_turn = 0


prompt_cache_tracker = PromptCacheTracker()
