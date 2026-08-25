"""Object B — full internal memory. Sole writer of memory_events.jsonl and memory_snapshot.json."""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from typing import Any
from server.call.paths import call_dir
from server.config.env import get_settings
from server.utils.logger import logger

ALLOWED_OPS = frozenset({"set_fact", "set_preference", "append_context", "update_summary"})
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

EMPTY_SNAPSHOT: dict[str, Any] = {
    "facts": {},
    "preferences": {},
    "important_context": "",
    "summary": "",
}

_MAX_FACTS = 32
_MAX_PREFERENCES = 16
_VALUE_MAX = 200
_CONTEXT_LINE_MAX = 240


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def empty_snapshot() -> dict[str, Any]:
    return {
        "facts": {},
        "preferences": {},
        "important_context": "",
        "summary": "",
    }


def _copy_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "facts": dict(snapshot.get("facts") or {}),
        "preferences": dict(snapshot.get("preferences") or {}),
        "important_context": str(snapshot.get("important_context") or ""),
        "summary": str(snapshot.get("summary") or ""),
    }


class MemoryManager:
    """Only module that mutates object B."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}

    def events_path(self, call_id: str):
        return call_dir(call_id) / "memory_events.jsonl"

    def snapshot_path(self, call_id: str):
        return call_dir(call_id) / "memory_snapshot.json"

    def projections_path(self, call_id: str):
        return call_dir(call_id) / "memory_projections.jsonl"

    def init(self, call_id: str) -> dict[str, Any]:
        snap = empty_snapshot()
        with self._lock:
            self._state[call_id] = snap
            self._events[call_id] = []
        directory = call_dir(call_id)
        directory.mkdir(parents=True, exist_ok=True)
        self.events_path(call_id).write_text("", encoding="utf-8")
        self._write_snapshot(call_id, snap)
        if self.projections_path(call_id).exists():
            self.projections_path(call_id).write_text("", encoding="utf-8")
        return _copy_snapshot(snap)

    def get_snapshot(self, call_id: str) -> dict[str, Any]:
        with self._lock:
            if call_id in self._state:
                return _copy_snapshot(self._state[call_id])
        path = self.snapshot_path(call_id)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                snap = _copy_snapshot(data if isinstance(data, dict) else empty_snapshot())
                with self._lock:
                    self._state.setdefault(call_id, snap)
                    self._events.setdefault(call_id, self._read_events_file(call_id))
                return _copy_snapshot(snap)
            except json.JSONDecodeError:
                return empty_snapshot()
        return empty_snapshot()

    def list_events(self, call_id: str) -> list[dict[str, Any]]:
        with self._lock:
            if call_id in self._events:
                return list(self._events[call_id])
        events = self._read_events_file(call_id)
        with self._lock:
            self._events.setdefault(call_id, events)
        return list(events)

    def snapshot_at_turn(self, call_id: str, turn_seq: int) -> dict[str, Any]:
        snap = empty_snapshot()
        for event in self.list_events(call_id):
            if int(event.get("turn_seq") or 0) > turn_seq:
                break
            if event.get("applied"):
                self._apply_ops_to(snap, event.get("operations") or [])
        return snap

    def record_projection(self, call_id: str, turn_seq: int, projection: str, *, include_summary: bool) -> None:
        line = {
            "turn_seq": turn_seq,
            "ts": _utcnow(),
            "include_summary": include_summary,
            "projection": projection,
        }
        path = self.projections_path(call_id)
        with self._lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    def projection_at_turn(self, call_id: str, turn_seq: int) -> str | None:
        path = self.projections_path(call_id)
        if not path.exists():
            return None
        last = None
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if int(row.get("turn_seq") or 0) == turn_seq:
                last = row.get("projection")
        return last

    def apply_proposals(
        self,
        call_id: str,
        operations: list[dict[str, Any]] | None,
        *,
        turn_seq: int,
        source: str = "model",
        actor: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        ops = operations or []
        accepted: list[dict[str, Any]] = []
        errors: list[str] = []
        for raw in ops:
            ok, normalized, err = self.validate_op(raw)
            if not ok:
                errors.append(err or "invalid op")
                continue
            accepted.append(normalized)

        event = {
            "turn_seq": turn_seq,
            "ts": _utcnow(),
            "source": source,
            "operations": accepted,
            "applied": bool(accepted),
            "validation_errors": errors,
        }
        if actor:
            event["actor"] = actor
        if reason:
            event["reason"] = reason

        with self._lock:
            current = self._state.get(call_id)
            snap = _copy_snapshot(current) if current is not None else empty_snapshot()
            if current is None:
                loaded = self._read_snapshot_file(call_id)
                if loaded:
                    snap = loaded
            if accepted:
                self._apply_ops_to(snap, accepted)
            self._state[call_id] = snap
            self._events.setdefault(call_id, []).append(event)

        self._append_event(call_id, event)
        self._write_snapshot(call_id, snap)
        if errors:
            logger.info(f"[MEMORY] rejected ops call={call_id} turn={turn_seq} errors={errors[:4]}")
        return {"snapshot": _copy_snapshot(snap), "event": event}

    def manual_correction(
        self,
        call_id: str,
        operations: list[dict[str, Any]],
        *,
        actor: str,
        reason: str,
        turn_seq: int = 0,
    ) -> dict[str, Any]:
        return self.apply_proposals(
            call_id,
            operations,
            turn_seq=turn_seq,
            source="manual_correction",
            actor=actor,
            reason=reason,
        )

    def validate_op(self, raw: Any) -> tuple[bool, dict[str, Any], str | None]:
        if not isinstance(raw, dict):
            return False, {}, "op must be an object"
        op = str(raw.get("op") or "").strip()
        if op not in ALLOWED_OPS:
            return False, {}, f"unknown op: {op or '(empty)'}"
        if op in ("set_fact", "set_preference"):
            key = str(raw.get("key") or "").strip()
            value = str(raw.get("value") if raw.get("value") is not None else "").strip()
            if not _KEY_RE.match(key):
                return False, {}, f"invalid key: {key!r}"
            if not value:
                return False, {}, f"{op} requires a non-empty value"
            return True, {"op": op, "key": key, "value": value[:_VALUE_MAX]}, None
        value = str(raw.get("value") if raw.get("value") is not None else "").strip()
        if not value:
            return False, {}, f"{op} requires a non-empty value"
        cap = self._summary_char_cap() if op == "update_summary" else _CONTEXT_LINE_MAX
        return True, {"op": op, "value": value[:cap]}, None

    def _apply_ops_to(self, snapshot: dict[str, Any], operations: list[dict[str, Any]] | None = None) -> None:
        settings = get_settings()
        max_chars = settings.working_memory_max_chars
        ops = operations if operations is not None else []
        for op in ops:
            name = op["op"]
            if name == "set_fact":
                facts = snapshot["facts"]
                if op["key"] not in facts and len(facts) >= _MAX_FACTS:
                    continue
                facts[op["key"]] = op["value"]
            elif name == "set_preference":
                prefs = snapshot["preferences"]
                if op["key"] not in prefs and len(prefs) >= _MAX_PREFERENCES:
                    continue
                prefs[op["key"]] = op["value"]
            elif name == "append_context":
                line = op["value"].lstrip("- ").strip()
                existing = snapshot.get("important_context") or ""
                next_text = f"{existing} {line}".strip() if existing else line
                if len(next_text) > max_chars:
                    next_text = next_text[-max_chars:]
                snapshot["important_context"] = next_text
            elif name == "update_summary":
                snapshot["summary"] = op["value"][: self._summary_char_cap()]

    def _summary_char_cap(self) -> int:
        return max(80, get_settings().rolling_summary_max_tokens * 4)

    def _read_snapshot_file(self, call_id: str) -> dict[str, Any] | None:
        path = self.snapshot_path(call_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return _copy_snapshot(data if isinstance(data, dict) else empty_snapshot())

    def _write_snapshot(self, call_id: str, snapshot: dict[str, Any]) -> None:
        self.snapshot_path(call_id).write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _append_event(self, call_id: str, event: dict[str, Any]) -> None:
        with self.events_path(call_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _read_events_file(self, call_id: str) -> list[dict[str, Any]]:
        path = self.events_path(call_id)
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return out

    def reset_for_tests(self) -> None:
        with self._lock:
            self._state.clear()
            self._events.clear()


memory_manager = MemoryManager()
