"""Post-call transcript from Telnyx recording via Gemini 3.5 Transcribe."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.call.call_ledger import call_ledger
from server.config.env import get_settings
from server.realtime.models import is_gemini_live_voice_model
from server.services.gemini_post_call_transcribe import (
    transcribe_recording_file,
    words_to_transcript_lines,
)
from server.utils.logger import logger

_QUEUE: asyncio.Queue[str] = asyncio.Queue()
_WORKER: asyncio.Task | None = None
_CALL_LOCKS: dict[str, asyncio.Lock] = {}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _meta_block(meta: dict[str, Any]) -> dict[str, Any]:
    block = meta.get("post_call_transcript")
    return block if isinstance(block, dict) else {}


def call_uses_gemini_post_call_transcript(meta: dict[str, Any] | None) -> bool:
    if not meta:
        return False
    if str(meta.get("pipeline") or "") != "realtime_voice":
        return False
    from server.services.transcription_policy import transcription_policy_from_meta

    policy = transcription_policy_from_meta(meta)
    if not policy.post_call_enabled:
        return False
    from server.services.transcription_policy import pstn_stack_from_meta

    stack = pstn_stack_from_meta(meta)
    llm = stack.get("llm") if isinstance(stack.get("llm"), dict) else {}
    model = str(llm.get("model") or (meta.get("usage") or {}).get("llm_model") or "")
    return is_gemini_live_voice_model(model)


def recording_path(call_id: str) -> Path | None:
    from server.call.audio_archive import audio_archive

    wav = audio_archive.telnyx_wav_path(call_id)
    mp3 = audio_archive.telnyx_mp3_path(call_id)
    if wav.is_file() and wav.stat().st_size > 44:
        return wav
    if mp3.is_file() and mp3.stat().st_size > 0:
        return mp3
    return None


def schedule_post_call_transcription(call_id: str) -> None:
    if not call_id:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(enqueue(call_id))


def _claim_transcription_job(call_id: str, *, force: bool = False) -> bool:
    """One logical job per call_id (pending/processing/complete block re-enqueue)."""
    meta = call_ledger.read_meta(call_id) or {"call_id": call_id}
    block = dict(_meta_block(meta))
    status = str(block.get("status") or "")
    if status == "complete" and not force:
        return False
    if status in ("pending", "processing") and not force:
        return False
    block["status"] = "pending"
    block["updated_at"] = _utcnow()
    meta["post_call_transcript"] = block
    call_ledger.write_meta(call_id, meta)
    return True


async def enqueue(call_id: str, *, force: bool = False) -> None:
    meta = call_ledger.read_meta(call_id)
    if not call_uses_gemini_post_call_transcript(meta):
        return
    if not _claim_transcription_job(call_id, force=force):
        return
    await _QUEUE.put(call_id)
    _ensure_worker()


def _ensure_worker() -> None:
    global _WORKER
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _WORKER is None or _WORKER.done():
        _WORKER = loop.create_task(_drain())


async def _drain() -> None:
    while True:
        call_id = await _QUEUE.get()
        try:
            await run_transcription(call_id)
        except Exception as exc:
            logger.warning(
                "[CALL] post_call_transcript failed call=%s err=%s",
                call_id,
                str(exc)[:200],
            )
            await _mark_status(call_id, "failed", error=str(exc)[:240])
        finally:
            _QUEUE.task_done()


async def run_transcription(call_id: str, *, force: bool = False) -> dict[str, Any]:
    lock = _CALL_LOCKS.setdefault(call_id, asyncio.Lock())
    async with lock:
        meta = call_ledger.read_meta(call_id) or {"call_id": call_id}
        if not call_uses_gemini_post_call_transcript(meta):
            return {"status": "skipped"}
        block = _meta_block(meta)
        if block.get("status") == "complete" and not force:
            return block

        settings = get_settings()
        model = (settings.post_call_transcript_model or "gemini-3.5-transcribe").strip()
        max_attempts = max(1, int(settings.post_call_transcript_max_retries or 6))
        base_delay = max(0.5, float(settings.post_call_transcript_retry_base_sec or 3.0))

        await _mark_status(call_id, "processing", model=model)
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            path = recording_path(call_id)
            if path is None:
                last_error = "recording_not_ready"
                if attempt < max_attempts:
                    await asyncio.sleep(base_delay * attempt)
                    continue
                await _mark_status(call_id, "failed", error=last_error, attempts=attempt)
                return {"status": "failed", "error": last_error}

            # Auto language detection / code-switching (spec §8); no Live STT hint lock.
            try:
                words, fallback, usage_meta = await asyncio.to_thread(
                    transcribe_recording_file,
                    path,
                    model=model,
                    language_code=None,
                )
            except Exception as exc:
                last_error = str(exc)[:200]
                if attempt < max_attempts:
                    await asyncio.sleep(base_delay * attempt)
                    continue
                await _mark_status(call_id, "failed", error=last_error, attempts=attempt)
                return {"status": "failed", "error": last_error}

            lines = words_to_transcript_lines(
                words,
                call_started_at=str(meta.get("started_at") or ""),
                direction=str(meta.get("direction") or "outbound"),
                fallback_text=fallback,
            )
            if not lines:
                last_error = "empty_transcript"
                if attempt < max_attempts:
                    await asyncio.sleep(base_delay)
                    continue
                await _mark_status(call_id, "failed", error=last_error, attempts=attempt)
                return {"status": "failed", "error": last_error}

            await call_ledger.replace_transcript(call_id, lines)
            await _apply_transcript_billing(
                call_id,
                path=path,
                usage_meta=usage_meta,
                model=model,
                line_count=len(lines),
            )
            await _mark_status(
                call_id,
                "complete",
                model=model,
                attempts=attempt,
                lines=len(lines),
                source="telnyx+gemini-3.5-transcribe",
            )
            try:
                from server.call.post_call_pipeline import enqueue as enqueue_outcome

                await enqueue_outcome(call_id, force=True)
            except Exception as exc:
                logger.warning(
                    "[CALL] post_call_transcript outcome requeue failed call=%s err=%s",
                    call_id,
                    str(exc)[:160],
                )
            return {"status": "complete", "lines": len(lines)}

        await _mark_status(call_id, "failed", error=last_error or "unknown", attempts=max_attempts)
        return {"status": "failed", "error": last_error}


async def _mark_status(call_id: str, status: str, **extra: Any) -> None:
    meta = call_ledger.read_meta(call_id) or {"call_id": call_id}
    block = dict(_meta_block(meta))
    block["status"] = status
    block["updated_at"] = _utcnow()
    for key, value in extra.items():
        if value is not None:
            block[key] = value
    meta["post_call_transcript"] = block
    meta["transcript_source"] = block.get("source") or meta.get("transcript_source")
    call_ledger.write_meta(call_id, meta)


async def _apply_transcript_billing(
    call_id: str,
    *,
    path: Path,
    usage_meta: dict[str, Any],
    model: str,
    line_count: int = 0,
) -> None:
    from server.services.usage_pricing import (
        cost_gemini_post_call_transcribe,
        resolve_fx_rate_inr,
    )

    meta = call_ledger.read_meta(call_id) or {}
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    duration_sec = float(usage.get("duration_sec") or 0)
    if duration_sec <= 0 and path.is_file():
        duration_sec = max(1.0, path.stat().st_size / 32000.0)
    cost = cost_gemini_post_call_transcribe(duration_sec=duration_sec, model=model)
    fx_info = resolve_fx_rate_inr(preferred=usage.get("fx_rate_inr"))
    fx = float(fx_info["rate"] or 95.64)
    transcript_usd = float(cost.get("usd") or 0)
    transcript_inr = transcript_usd * fx
    usage["post_call_transcript_model"] = model
    usage["post_call_transcript_usd"] = transcript_usd
    usage["post_call_transcript_inr"] = transcript_inr
    usage["post_call_transcript_seconds"] = duration_sec
    usage["transcription_model"] = model
    usage["transcription_billing"] = "post_call_gemini_transcribe"
    if usage_meta.get("input_tokens") is not None:
        usage["post_call_transcript_input_tokens"] = usage_meta.get("input_tokens")
    if usage_meta.get("output_tokens") is not None:
        usage["post_call_transcript_output_tokens"] = usage_meta.get("output_tokens")
    model_usd = float(usage.get("model_cost_usd") if usage.get("model_cost_usd") is not None else usage.get("cost_usd") or 0)
    telnyx_usd = float(usage.get("telnyx_usd") or 0)
    total_usd = model_usd + telnyx_usd + transcript_usd
    total_inr = total_usd * fx
    usage["cost_usd"] = total_usd
    usage["cost_inr"] = total_inr
    minutes = max(duration_sec / 60.0, 1e-9)
    usage["cost_usd_per_min"] = total_usd / minutes
    usage["cost_inr_per_min"] = total_inr / minutes
    if line_count > 0:
        usage["dialog_turns"] = sum(
            1 for row in call_ledger.read_lines(call_id) if row.get("role") == "assistant"
        )
    meta["usage"] = usage
    call_ledger.write_meta(call_id, meta)
    try:
        await call_ledger.append_trace_turn(
            call_id,
            {
                "kind": "post_call_transcript",
                "post_call_transcript_usd": transcript_usd,
                "post_call_transcript_inr": transcript_inr,
                "post_call_transcript_model": model,
                "transcript_lines": line_count,
            },
        )
    except Exception:
        pass
