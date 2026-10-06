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


def _sync_post_call_transcript_usage(
    usage: dict[str, Any],
    meta: dict[str, Any],
    *,
    duration_sec: float,
    fx: float,
) -> tuple[float, float]:
    """Recompute post-call transcribe ₹/$ when wall duration is finalized at hangup."""
    from server.services.transcription_policy import transcription_policy_from_meta

    policy = transcription_policy_from_meta(meta)
    if not policy.post_call_enabled:
        usage["post_call_transcript_usd"] = 0.0
        usage["post_call_transcript_inr"] = 0.0
        return 0.0, 0.0
    block = meta.get("post_call_transcript") if isinstance(meta.get("post_call_transcript"), dict) else {}
    status = str(block.get("status") or "")
    if status != "complete" and not usage.get("post_call_transcript_usd"):
        usd = float(usage.get("post_call_transcript_usd") or 0)
        inr = float(usage.get("post_call_transcript_inr") or usd * fx)
        return usd, inr
    from server.services.usage_pricing import cost_gemini_post_call_transcribe

    model = str(usage.get("post_call_transcript_model") or policy.post_call_model or "gemini-3.5-transcribe")
    cost = cost_gemini_post_call_transcribe(duration_sec=max(0.0, float(duration_sec or 0)), model=model)
    usd = float(cost.get("usd") or 0)
    inr = usd * fx
    usage["post_call_transcript_model"] = model
    usage["post_call_transcript_usd"] = usd
    usage["post_call_transcript_inr"] = inr
    usage["post_call_transcript_seconds"] = float(duration_sec or 0)
    if status == "complete":
        usage["transcription_billing"] = usage.get("transcription_billing") or "post_call_gemini_transcribe"
    return usd, inr


def _sync_live_transcript_usage(
    usage: dict[str, Any],
    meta: dict[str, Any],
    *,
    duration_sec: float,
    fx: float,
) -> tuple[float, float]:
    from server.services.transcription_policy import transcription_policy_from_meta
    from server.services.usage_pricing import cost_openai_live_transcribe

    policy = transcription_policy_from_meta(meta)
    billed_sec = float(usage.get("live_transcript_seconds") or 0)
    if billed_sec <= 0 and policy.live_enabled:
        billed_sec = max(0.0, float(duration_sec or 0))
    if not policy.live_enabled or billed_sec <= 0:
        usage["live_transcript_usd"] = 0.0
        usage["live_transcript_inr"] = 0.0
        return 0.0, 0.0
    model = str(usage.get("live_transcript_model") or policy.live_model or "gpt-4o-mini-transcribe")
    cost = cost_openai_live_transcribe(duration_sec=billed_sec, model=model)
    usd = float(cost.get("usd") or 0)
    inr = usd * fx
    usage["live_transcript_model"] = model
    usage["live_transcript_usd"] = usd
    usage["live_transcript_inr"] = inr
    usage["live_transcript_seconds"] = billed_sec
    if not usage.get("transcription_billing"):
        usage["transcription_billing"] = "live_openai_transcribe"
    return usd, inr


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

    async def replace_transcript(self, call_id: str, lines: list[dict[str, Any]]) -> None:
        """Overwrite transcript.jsonl after seal (post-call transcription)."""
        async with _lock(call_id):
            path = self.transcript_path(call_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as fh:
                for row in lines:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if lines:
                _seq[call_id] = max(_seq.get(call_id, 0), int(lines[-1].get("seq") or len(lines)))

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
            out["model_cost_inr_per_min"] = usage.get("model_cost_inr_per_min")
            out["telnyx_usd"] = usage.get("telnyx_usd")
            out["telnyx_inr"] = usage.get("telnyx_inr")
            out["telnyx_inr_per_min"] = usage.get("telnyx_inr_per_min")
            out["telnyx_balance_start"] = usage.get("telnyx_balance_start")
            out["telnyx_balance_end"] = usage.get("telnyx_balance_end")
            out["telnyx_balance_delta_usd"] = usage.get("telnyx_balance_delta_usd")
            out["telnyx_cost_source"] = usage.get("telnyx_cost_source")
            out["gemini_38_live_cost_usd"] = usage.get("gemini_38_live_cost_usd")
            out["gemini_38_live_cost_inr"] = usage.get("gemini_38_live_cost_inr")
            out["gemini_list_audio_inr_per_min"] = usage.get("gemini_list_audio_inr_per_min")
            out["fx_source"] = usage.get("fx_source")
        if usage and usage.get("duration_sec") is not None:
            out["duration_sec"] = usage.get("duration_sec")
        pipeline = meta.get("pipeline") or (usage or {}).get("pipeline")
        if pipeline:
            out["pipeline"] = pipeline
        for key in (
            "caller_id",
            "end_reason",
            "hangup_reason",
            "hangup_playback_wait_ms",
            "hangup_trail_ms",
            "callback_close_phase",
            "compiled_brain_version",
            "combination_id",
            "campaign_id",
            "billed_user_id",
        ):
            if meta.get(key) not in (None, ""):
                out[key] = meta[key]
        stack = meta.get("resolved_stack")
        if isinstance(stack, dict) and stack:
            out["resolved_stack"] = stack
        tx = meta.get("post_call_transcript")
        if isinstance(tx, dict) and tx.get("status"):
            out["post_call_transcript"] = tx
        if meta.get("transcript_source"):
            out["transcript_source"] = meta.get("transcript_source")
        return out

    def stamp_ended_usage(self, call_id: str, *, reason: str, duration_sec: float | int | None) -> None:
        """Freeze wall-clock duration, Telnyx minutes, and ₹/min after hangup."""
        meta = self.read_meta(call_id)
        if not meta:
            return
        meta["ended_at"] = _utcnow()
        meta["end_reason"] = reason
        if duration_sec is not None:
            meta["duration_sec"] = float(duration_sec)
        usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
        # Telnyx list is per minute; prorate by wall-clock seconds (no ceil).
        minutes = max(0.0, float(duration_sec or 0)) / 60.0
        from server.services.usage_pricing import resolve_fx_rate_inr

        fx_info = resolve_fx_rate_inr(preferred=usage.get("fx_rate_inr"))
        fx = float(fx_info["rate"] or 95.64)
        model_usd = float(usage.get("model_cost_usd") if usage.get("model_cost_usd") is not None else usage.get("cost_usd") or 0)
        model_inr = model_usd * fx
        telnyx_usd = 0.0
        channel = str(meta.get("channel") or "")
        pipeline = str(meta.get("pipeline") or usage.get("pipeline") or "")
        telnyx_breakdown: dict[str, Any] = {}
        if channel == "pstn" or pipeline == "realtime_voice":
            from server.services.usage_pricing import (
                cost_telnyx_call_breakdown,
                telnyx_destination_country_from_e164,
                telnyx_estimate_call_recording,
            )

            dest = telnyx_destination_country_from_e164(str(meta.get("callee_e164") or ""))
            telnyx_breakdown = cost_telnyx_call_breakdown(
                duration_sec=duration_sec,
                direction=str(meta.get("direction") or "outbound"),
                media_streaming=True,
                call_recording=telnyx_estimate_call_recording(),
                destination_country=dest,
            )
            telnyx_usd = float(telnyx_breakdown.get("total_usd") or 0)
        telnyx_inr = telnyx_usd * fx
        post_tx_usd, post_tx_inr = _sync_post_call_transcript_usage(
            usage,
            meta,
            duration_sec=float(duration_sec or 0),
            fx=fx,
        )
        live_tx_usd, live_tx_inr = _sync_live_transcript_usage(
            usage,
            meta,
            duration_sec=float(duration_sec or 0),
            fx=fx,
        )
        transcript_usd = post_tx_usd + live_tx_usd
        transcript_inr = post_tx_inr + live_tx_inr
        total_usd = model_usd + telnyx_usd + transcript_usd
        total_inr = model_inr + telnyx_inr + transcript_inr
        usage["pipeline"] = usage.get("pipeline") or pipeline
        usage["duration_sec"] = float(duration_sec or 0)
        usage["model_cost_usd"] = model_usd
        usage["model_cost_inr"] = model_inr
        usage["telnyx_usd"] = telnyx_usd
        usage["telnyx_inr"] = telnyx_inr
        if telnyx_breakdown:
            usage["telnyx_voice_api_usd"] = telnyx_breakdown.get("voice_api_usd")
            usage["telnyx_sip_usd"] = telnyx_breakdown.get("sip_usd")
            usage["telnyx_media_stream_usd"] = telnyx_breakdown.get("media_stream_usd")
            usage["telnyx_call_recording_usd"] = telnyx_breakdown.get("call_recording_usd")
            usage["telnyx_destination_country"] = telnyx_breakdown.get("destination_country")
            usage["telnyx_sip_usd_per_min"] = telnyx_breakdown.get("sip_usd_per_min")
            usage["telnyx_cost_is_estimate"] = True
        usage["cost_usd"] = total_usd
        usage["cost_inr"] = total_inr
        usage["cost_is_estimate"] = False
        usage["fx_rate_inr"] = fx
        usage["fx_source"] = fx_info.get("source")
        if fx_info.get("as_of"):
            usage["fx_as_of"] = fx_info["as_of"]
        usage["gst_inr"] = 0.0
        usage["cost_usd_per_min"] = (total_usd / minutes) if minutes > 0 else 0.0
        usage["cost_inr_per_min"] = (total_inr / minutes) if minutes > 0 else 0.0
        usage["model_cost_usd_per_min"] = (model_usd / minutes) if minutes > 0 else 0.0
        usage["model_cost_inr_per_min"] = (model_inr / minutes) if minutes > 0 else 0.0
        usage["telnyx_usd_per_min"] = (telnyx_usd / minutes) if minutes > 0 else 0.0
        usage["telnyx_inr_per_min"] = (telnyx_inr / minutes) if minutes > 0 else 0.0
        from server.realtime.models import is_gemini_live_voice_model
        from server.services.usage_pricing import (
            GEMINI_LIVE_AUDIO_INPUT_USD_PER_MIN,
            GEMINI_LIVE_AUDIO_OUTPUT_USD_PER_MIN,
        )

        if is_gemini_live_voice_model(str(usage.get("llm_model") or "")):
            usage["gemini_38_live_cost_usd"] = model_usd
            usage["gemini_38_live_cost_inr"] = model_inr
            usage["gemini_38_live_tokens"] = {
                "input": int(usage.get("input_tokens") or 0),
                "output": int(usage.get("output_tokens") or 0),
                "input_audio": int(usage.get("input_audio_tokens") or 0),
                "output_audio": int(usage.get("output_audio_tokens") or 0),
                "cached": int(usage.get("cached_tokens") or 0),
            }
            usage["gemini_list_audio_input_usd_per_min"] = GEMINI_LIVE_AUDIO_INPUT_USD_PER_MIN
            usage["gemini_list_audio_output_usd_per_min"] = GEMINI_LIVE_AUDIO_OUTPUT_USD_PER_MIN
            usage["gemini_list_audio_inr_per_min"] = (
                GEMINI_LIVE_AUDIO_INPUT_USD_PER_MIN + GEMINI_LIVE_AUDIO_OUTPUT_USD_PER_MIN
            ) * fx
            usage["gemini_billing"] = usage.get("gemini_billing") or "session_cumulative_tokens"
            usage["gemini_billing_note"] = (
                usage.get("gemini_billing_note")
                or "Model cost uses billed token totals (text+audio+image), not call duration × list audio $/min."
            )
        if meta.get("telnyx_balance_start") is not None:
            usage["telnyx_balance_start"] = float(meta["telnyx_balance_start"])
            usage["telnyx_cost_source"] = usage.get("telnyx_cost_source") or "tariff_rate_deck"
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
