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

    def review_fields(self, call_id: str) -> dict[str, Any]:
        """Cost, pipeline, and identity from meta.json for history/detail APIs."""
        meta = self.read_meta(call_id)
        if not meta:
            return {}
        out: dict[str, Any] = {}
        usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else None
        if usage:
            out["usage"] = usage
            out["cost_usd"] = usage.get("cost_usd")
            out["cost_inr"] = usage.get("cost_inr")
            out["cost_inr_per_min"] = usage.get("cost_inr_per_min")
            out["model_cost_usd"] = usage.get("model_cost_usd")
            out["model_cost_inr"] = usage.get("model_cost_inr")
            out["telnyx_usd"] = usage.get("telnyx_usd")
            out["telnyx_inr"] = usage.get("telnyx_inr")
        if usage and usage.get("duration_sec") is not None:
            out["duration_sec"] = usage.get("duration_sec")
        pipeline = meta.get("pipeline") or (usage or {}).get("pipeline")
        if pipeline:
            out["pipeline"] = pipeline
        for key in ("caller_id", "end_reason", "compiled_brain_version", "combination_id", "campaign_id"):
            if meta.get(key):
                out[key] = meta[key]
        stack = meta.get("resolved_stack")
        if isinstance(stack, dict) and stack:
            out["resolved_stack"] = stack
        return out

    def stamp_ended_usage(self, call_id: str, *, reason: str, duration_sec: int | None) -> None:
        """Freeze wall-clock duration, Telnyx minutes, and ₹/min after hangup."""
        meta = self.read_meta(call_id)
        if not meta:
            return
        meta["ended_at"] = _utcnow()
        meta["end_reason"] = reason
        if duration_sec is not None:
            meta["duration_sec"] = duration_sec
        usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
        minutes = max(0, int(duration_sec or 0)) / 60.0
        fx = float(usage.get("fx_rate_inr") or 0)
        if fx <= 0:
            try:
                from server.config.env import get_settings

                fx = float(get_settings().fx_rate_inr or 95.64)
            except Exception:
                fx = 95.64
        model_usd = float(usage.get("model_cost_usd") if usage.get("model_cost_usd") is not None else usage.get("cost_usd") or 0)
        model_inr = float(usage.get("model_cost_inr") if usage.get("model_cost_inr") is not None else usage.get("cost_inr") or 0)
        telnyx_usd = 0.0
        channel = str(meta.get("channel") or "")
        pipeline = str(meta.get("pipeline") or usage.get("pipeline") or "")
        if channel == "pstn" or pipeline == "realtime_voice":
            from server.services.usage_pricing import cost_telnyx_call_usd

            telnyx_usd = cost_telnyx_call_usd(
                duration_sec=duration_sec,
                direction=str(meta.get("direction") or "outbound"),
            )
        telnyx_inr = telnyx_usd * fx
        total_usd = model_usd + telnyx_usd
        total_inr = model_inr + telnyx_inr
        usage["pipeline"] = usage.get("pipeline") or pipeline
        usage["duration_sec"] = float(duration_sec or 0)
        usage["model_cost_usd"] = model_usd
        usage["model_cost_inr"] = model_inr
        usage["telnyx_usd"] = telnyx_usd
        usage["telnyx_inr"] = telnyx_inr
        usage["cost_usd"] = total_usd
        usage["cost_inr"] = total_inr
        usage["fx_rate_inr"] = fx
        usage["cost_usd_per_min"] = (total_usd / minutes) if minutes > 0 else 0.0
        usage["cost_inr_per_min"] = (total_inr / minutes) if minutes > 0 else 0.0
        meta["usage"] = usage
        self.write_meta(call_id, meta)

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
