"""Object A — append-only transcript ledger. Sole writer of transcript.jsonl."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.call.paths import call_dir
from server.utils.logger import logger

_locks: dict[str, asyncio.Lock] = {}
_seq: dict[str, int] = {}
_sealed: set[str] = set()


def _lock(call_id: str) -> asyncio.Lock:
    if call_id not in _locks:
        _locks[call_id] = asyncio.Lock()
    return _locks[call_id]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CallLedger:
    def transcript_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "transcript.jsonl"

    def meta_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "meta.json"

    def trace_path(self, call_id: str) -> Path:
        return call_dir(call_id) / "trace.json"

    async def init(self, call_id: str, meta: dict[str, Any]) -> None:
        directory = call_dir(call_id)
        directory.mkdir(parents=True, exist_ok=True)
        self.meta_path(call_id).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.transcript_path(call_id).write_text("", encoding="utf-8")
        self.trace_path(call_id).write_text(
            json.dumps(
                {
                    "call_id": call_id,
                    "combination_id": meta.get("combination_id"),
                    "compiled_brain_version": meta.get("compiled_brain_version"),
                    "turns": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _seq[call_id] = 0
        _sealed.discard(call_id)

    async def append_user_turn(
        self,
        call_id: str,
        text: str,
        *,
        stt_latency_ms: int | None = None,
        ts: str | None = None,
    ) -> dict[str, Any]:
        return await self._append(
            call_id,
            {"role": "user", "text": text, "stt_latency_ms": stt_latency_ms, "partial": False, "ts": ts},
        )

    async def append_assistant_turn(
        self,
        call_id: str,
        text: str,
        *,
        brain_latency_ms: int | None = None,
        tts_first_byte_ms: int | None = None,
        ts: str | None = None,
    ) -> dict[str, Any]:
        return await self._append(
            call_id,
            {
                "role": "assistant",
                "text": text,
                "brain_latency_ms": brain_latency_ms,
                "tts_first_byte_ms": tts_first_byte_ms,
                "ts": ts,
            },
        )

    async def _append(self, call_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with _lock(call_id):
            if call_id in _sealed:
                raise RuntimeError(f"ledger sealed: {call_id}")
            seq = _seq.get(call_id, 0) + 1
            _seq[call_id] = seq
            line = {
                "seq": seq,
                "role": payload["role"],
                "text": payload.get("text") or "",
                "ts": payload.get("ts") or _utcnow(),
            }
            for key in ("stt_latency_ms", "brain_latency_ms", "tts_first_byte_ms", "partial"):
                if key in payload and payload[key] is not None:
                    line[key] = payload[key]
            path = self.transcript_path(call_id)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            return line

    async def seal(self, call_id: str) -> None:
        async with _lock(call_id):
            _sealed.add(call_id)

    def is_sealed(self, call_id: str) -> bool:
        return call_id in _sealed

    def read_lines(self, call_id: str) -> list[dict[str, Any]]:
        path = self.transcript_path(call_id)
        if not path.exists():
            return []
        lines: list[dict[str, Any]] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("[CALL] skipped corrupt ledger line", extra={"call_id": call_id})
        return lines

    def read_meta(self, call_id: str) -> dict[str, Any]:
        path = self.meta_path(call_id)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def write_meta(self, call_id: str, meta: dict[str, Any]) -> None:
        self.meta_path(call_id).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_trace(self, call_id: str) -> dict[str, Any]:
        path = self.trace_path(call_id)
        if not path.exists():
            return {"call_id": call_id, "turns": []}
        return json.loads(path.read_text(encoding="utf-8"))

    async def append_trace_turn(self, call_id: str, turn: dict[str, Any]) -> None:
        async with _lock(call_id):
            trace = self.read_trace(call_id)
            trace.setdefault("turns", []).append(turn)
            self.trace_path(call_id).write_text(
                json.dumps(trace, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def reset_for_tests(self) -> None:
        _locks.clear()
        _seq.clear()
        _sealed.clear()


call_ledger = CallLedger()
