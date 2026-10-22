"""Bounded, content-free call timelines. No network or disk I/O on the media loop."""
from __future__ import annotations

import time
from collections import OrderedDict, deque
from copy import deepcopy
from threading import RLock
from typing import Any

# Deliberately omit prompts, transcripts, URLs, numbers, credentials and raw
# exception messages. Add structured error_type/reason at failure sites instead.
SAFE_FIELDS = frozenset({
    "provider", "model", "pipeline", "direction", "reason", "event", "status",
    "error_type", "close_code", "codec", "sample_rate", "channels", "wire_codec",
    "wire_rate", "source_codec", "outbound_codec", "frames", "frames_in",
    "frames_out", "media_in", "media_out", "bytes", "wire_bytes", "rtp_frames",
    "greeting_frames", "greeting_chars", "deferred_frames", "deferred_greeting",
    "play_greeting", "queue_qsize", "queued", "grace_sec", "wait_sec",
    "retry_count", "attempt", "lag_ms", "bidirectional", "timeout_s",
})


class PstnDiagnostics:
    def __init__(self, max_calls: int = 100, max_events: int = 300) -> None:
        self.max_calls = max_calls
        self.max_events = max_events
        self._calls: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._aliases: dict[str, str] = {}
        self._seq = 0
        self._lock = RLock()

    def record(self, phase: str, *, timer_key: str | None = None, **fields: Any) -> None:
        identifiers = list(dict.fromkeys(str(v) for v in (
            fields.get("control"), fields.get("call_sid"), fields.get("call_id"), timer_key,
        ) if v))
        if not identifiers:
            return
        with self._lock:
            keys = list(dict.fromkeys(self._aliases[i] for i in identifiers if i in self._aliases))
            key = keys[0] if keys else identifiers[0]
            row = self._calls.setdefault(key, {
                "events": deque(maxlen=self.max_events), "ids": [], "started_at": time.time(),
            })
            for other in keys[1:]:
                old = self._calls.pop(other)
                row["events"] = deque(sorted(
                    [*row["events"], *old["events"]], key=lambda e: e["seq"],
                )[-self.max_events:], maxlen=self.max_events)
                row["ids"].extend(i for i in old["ids"] if i not in row["ids"])
                row["started_at"] = min(row["started_at"], old["started_at"])
            row["ids"].extend(i for i in identifiers if i not in row["ids"])
            for identifier in row["ids"]:
                self._aliases[identifier] = key
            self._seq += 1
            safe = {k: (v[:120] if isinstance(v, str) else v) for k, v in fields.items()
                    if k in SAFE_FIELDS and isinstance(v, (str, int, float, bool, type(None)))}
            row["events"].append({"seq": self._seq, "at": time.time(), "phase": phase,
                                  "fields": safe})
            self._calls.move_to_end(key)
            while len(self._calls) > self.max_calls:
                _, stale = self._calls.popitem(last=False)
                for identifier in stale["ids"]:
                    self._aliases.pop(identifier, None)

    def snapshot(self, identifier: str | None = None, *, after: int = 0,
                 limit: int = 100) -> dict[str, Any] | None:
        with self._lock:
            key = self._aliases.get(identifier or "") if identifier else next(reversed(self._calls), None)
            row = self._calls.get(key) if key else None
            if row is None:
                return None
            events = list(row["events"])
            selected = [e for e in events if e["seq"] > after][:limit]
            return deepcopy({
                "ids": row["ids"], "started_at": row["started_at"], "events": selected,
                "next_cursor": selected[-1]["seq"] if selected else after,
                "oldest_cursor": events[0]["seq"] if events else None,
                "retention": "process-local; last 100 calls, 300 events per call; cleared on restart",
            })


pstn_diagnostics = PstnDiagnostics()
