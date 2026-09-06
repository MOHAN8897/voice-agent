"""Post-call pipeline — outcome LLM after hang-up. Never blocks call/end."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from server.call.call_context import get as get_ctx
from server.call.call_ledger import call_ledger
from server.call.call_store import call_store
from server.call.memory_manager import memory_manager
from server.call.outcome_schema import (
    DISPOSITIONS,
    OUTCOME_JSON_SCHEMA,
    empty_outcome,
    normalize_extracted_fields,
    validate_disposition,
)
from server.call.paths import call_dir
from server.config.env import get_settings
from server.utils.logger import logger

_QUEUE: asyncio.Queue[str] = asyncio.Queue()
_WORKER: asyncio.Task | None = None


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def outcome_path(call_id: str):
    return call_dir(call_id) / "outcome.json"


def attempts_path(call_id: str):
    return call_dir(call_id) / "outcome_attempts.jsonl"


def read_outcome(call_id: str) -> dict[str, Any] | None:
    path = outcome_path(call_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def enqueue(call_id: str) -> None:
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
            await run_outcome(call_id)
        except Exception as e:
            logger.warning(f"[CALL] post-call failed call={call_id} err={str(e)[:200]}")
            await _mark_outcome(call_id, "failed")
        finally:
            _QUEUE.task_done()


async def process_now(call_id: str) -> dict[str, Any]:
    """Synchronous helper for tests / recovery / retry."""
    return await run_outcome(call_id)


async def run_outcome(call_id: str, *, force: bool = False) -> dict[str, Any]:
    settings = get_settings()
    model = settings.post_call_llm_model
    await _mark_outcome(call_id, "processing")
    transcript = call_ledger.read_lines(call_id)
    snapshot = memory_manager.get_snapshot(call_id)
    meta = call_ledger.read_meta(call_id)
    payload, error = await _generate_outcome(transcript, snapshot, meta, model=model)
    attempt = {
        "ts": _utcnow(),
        "model": model,
        "ok": error is None,
        "error": error,
        "disposition": payload.get("disposition"),
    }
    _append_attempt(call_id, attempt)
    payload["model"] = model
    payload["prompt_version"] = "outcome_v1"
    payload["generated_at"] = _utcnow()
    payload["generation_ok"] = error is None
    disposition = validate_disposition(payload.get("disposition"))
    if payload.get("disposition") not in DISPOSITIONS:
        payload["disposition"] = disposition
        payload["notes"] = (payload.get("notes") or "") + " (disposition coerced to no_outcome)"
    outcome_path(call_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    status = "complete" if error is None else "failed"
    await call_store.update(call_id, {"disposition": payload["disposition"]})
    await _mark_outcome(call_id, status)
    return payload


async def _generate_outcome(
    transcript: list[dict[str, Any]],
    snapshot: dict[str, Any],
    meta: dict[str, Any],
    *,
    model: str,
) -> tuple[dict[str, Any], str | None]:
    settings = get_settings()
    if not transcript:
        return empty_outcome(model=model, reason="empty transcript"), None

    messages = [
        {
            "role": "developer",
            "content": (
                "You analyze completed voice calls. Output structured JSON only. "
                "extracted_fields must be an array of {key, value} strings "
                "(name, budget, slot, etc). Use [] if nothing was captured. "
                "Disposition rubric: new_lead (first contact/info captured), interested "
                "(positive, not yet qualified), qualified (meets criteria), site_visit_planned "
                "(concrete appointment), callback_required (explicit follow-up), not_interested "
                "(clear rejection), wrong_number, converted (goal achieved), no_outcome "
                "(<3 turns or inconclusive)."
            ),
        },
        {
            "role": "user",
            "content": (
                "[Full transcript]\n"
                + "\n".join(f"{row.get('role')}: {row.get('text')}" for row in transcript)
                + "\n\n[Final working memory]\n"
                + json.dumps(snapshot, ensure_ascii=False)
                + "\n\n[Agent context]\n"
                + json.dumps(
                    {
                        "agent_id": meta.get("agent_id"),
                        "compiled_brain_version": meta.get("compiled_brain_version"),
                    },
                    ensure_ascii=False,
                )
            ),
        },
    ]

    last_error: str | None = None
    retries = max(1, settings.post_call_max_retries)
    resolved = meta.get("resolved_stack") or {}
    llm_block = resolved.get("llm") or {}
    provider_id = llm_block.get("provider") or "openai"
    locked_model = llm_block.get("model") or model
    for attempt in range(retries):
        try:
            from server.providers import get_provider_registry
            from server.providers.base import LLMConfig

            registry = get_provider_registry()
            adapter = registry.get_llm(provider_id)
            payload = await adapter.structured_completion(
                messages,
                OUTCOME_JSON_SCHEMA,
                LLMConfig(provider=provider_id, model=locked_model),
                schema_name="call_outcome",
                max_output_tokens=800,
            )
            if not isinstance(payload, dict):
                raise ValueError("outcome payload is not an object")
            payload["extracted_fields"] = normalize_extracted_fields(payload.get("extracted_fields"))
            payload.setdefault("objections", [])
            payload.setdefault("next_action", None)
            payload.setdefault("summary_te", "")
            payload.setdefault("summary_en", "")
            payload.setdefault("disposition_confidence", 0.0)
            return payload, None
        except Exception as e:
            last_error = str(e)[:240]
            logger.warning(f"[CALL] outcome attempt {attempt + 1} failed: {last_error}")
            await asyncio.sleep(0.2 * (2**attempt))
    failed = empty_outcome(model=model, reason=last_error or "outcome generation failed")
    return failed, last_error


def _append_attempt(call_id: str, attempt: dict[str, Any]) -> None:
    with attempts_path(call_id).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(attempt, ensure_ascii=False) + "\n")


async def _mark_outcome(call_id: str, outcome_status: str) -> None:
    """Outcome is independent of ledger/audio. Overall complete once A+audio are done."""
    ctx = get_ctx(call_id)
    if ctx:
        ctx.components["outcome"] = outcome_status
        ledger_ok = ctx.components.get("ledger") == "complete"
        audio_ok = ctx.components.get("audio") in ("complete", "empty", "failed")
        if ledger_ok and audio_ok and outcome_status in ("complete", "failed", "skipped"):
            ctx.status = "complete"
        elif outcome_status == "processing" and ctx.status != "complete":
            ctx.status = "finalizing"
    rec = await call_store.get(call_id)
    if rec and rec.get("finalization_status") in ("pending", "processing", "failed"):
        if outcome_status == "processing":
            overall = "processing"
        elif outcome_status in ("complete", "failed", "skipped"):
            overall = "complete"
        else:
            overall = rec.get("finalization_status") or "processing"
        await call_store.update(call_id, {"finalization_status": overall})
