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
    derive_status_tags,
    empty_outcome,
    merge_outcome_facts,
    normalize_extracted_fields,
    validate_disposition,
)
from server.call.paths import call_dir
from server.config.env import get_settings
from server.realtime.language_guard import filter_unrelated_scripts
from server.realtime.models import http_openai_model, is_realtime_llm_model
from server.utils.logger import logger

_QUEUE: asyncio.Queue[tuple[str, bool]] = asyncio.Queue()
_WORKER: asyncio.Task | None = None
_CALL_LOCKS: dict[str, asyncio.Lock] = {}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def outcome_path(call_id: str):
    return call_dir(call_id) / "outcome.json"


def call_summary_path(call_id: str):
    return call_dir(call_id) / "call_summary.json"


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


async def enqueue(call_id: str, *, force: bool = False) -> None:
    try:
        await call_store.update(call_id, {"finalization_status": "pending"})
    except Exception as exc:
        logger.warning(f"[CALL] failed to set pending finalization_status for {call_id}: {exc}")
    await _QUEUE.put((call_id, force))
    _ensure_worker()


async def recover_pending_post_calls() -> int:
    """Find any calls whose post-call processing was interrupted by restart and re-queue."""
    try:
        pending = await call_store.list_pending_finalization()
        count = 0
        for rec in pending:
            cid = rec.get("call_id")
            if cid:
                logger.info(f"[RECOVERY] Re-enqueuing interrupted post-call analysis for {cid}")
                await enqueue(str(cid), force=True)
                count += 1
        if count:
            logger.info(f"[RECOVERY] Re-enqueued {count} pending post-call jobs")
        return count
    except Exception as exc:
        logger.warning(f"[RECOVERY] post-call recovery failed: {exc}")
        return 0


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
        call_id, force = await _QUEUE.get()
        try:
            await run_outcome(call_id, force=force)
        except Exception as e:
            logger.warning(f"[CALL] post-call failed call={call_id} err={str(e)[:200]}")
            await _mark_outcome(call_id, "failed")
        finally:
            _QUEUE.task_done()


async def process_now(call_id: str) -> dict[str, Any]:
    """Synchronous helper for tests / recovery / retry."""
    return await run_outcome(call_id)


async def run_outcome(call_id: str, *, force: bool = False) -> dict[str, Any]:
    lock = _CALL_LOCKS.setdefault(call_id, asyncio.Lock())
    async with lock:
        existing = read_outcome(call_id)
        if (
            existing
            and existing.get("generation_ok")
            and existing.get("prompt_version") == "outcome_v3"
            and not force
        ):
            return existing
        return await _run_outcome_locked(call_id)


async def _run_outcome_locked(call_id: str) -> dict[str, Any]:
    settings = get_settings()
    model = http_openai_model(settings)
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
    payload["prompt_version"] = "outcome_v3"
    payload["generated_at"] = _utcnow()
    payload["generation_ok"] = error is None
    disposition = validate_disposition(payload.get("disposition"))
    if payload.get("disposition") not in DISPOSITIONS:
        payload["disposition"] = disposition
        payload["notes"] = (payload.get("notes") or "") + " (disposition coerced to no_outcome)"
    _english_only_summaries(payload)
    facts = merge_outcome_facts(
        payload.get("extracted_fields"),
        snapshot,
        caller_id=str(meta.get("caller_id") or "") or None,
        callee_e164=str(meta.get("callee_e164") or "") or None,
        direction=str(meta.get("direction") or "") or None,
    )
    handoff = meta.get("language_callback")
    if isinstance(handoff, dict):
        payload["language_callback"] = handoff
        if handoff.get("status") == "requested":
            payload["disposition"] = "callback_required"
            facts["preferred_language"] = handoff["caller_language"]
            facts["callback_requested"] = "true"
            payload["summary_en"] = (payload.get("summary_en") or "") + " Language handoff: " + handoff["summary"]
            payload["next_action"] = f"Arrange a callback in {handoff['caller_language']}. No callback time has been booked."
    payload["extracted_fields"] = facts
    payload["facts"] = facts
    payload["status_tags"] = derive_status_tags(
        payload.get("disposition"),
        facts,
        next_action=payload.get("next_action"),
        objections=payload.get("objections"),
    )
    outcome_path(call_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_call_summary(call_id, payload)
    status = "complete" if error is None else "failed"
    await call_store.update(call_id, {"disposition": payload["disposition"]})
    await _mark_outcome(call_id, status)
    # The judgement above is only useful if it lands in the CRM, attributed to the
    # agent that took the call. Runs last so a lead write can never invalidate the
    # outcome the console reads, and swallows its own errors for the same reason.
    payload["lead"] = await _sync_lead(call_id, payload, meta)
    return payload


async def _sync_lead(
    call_id: str, outcome: dict[str, Any], meta: dict[str, Any]
) -> dict[str, Any] | None:
    """Attribute this call's outcome to a lead owned by the calling agent."""
    try:
        record = await call_store.get(call_id)
    except Exception:
        logger.warning("lead_sync: could not load call %s", call_id, exc_info=True)
        return None
    if not record:
        return None
    from server.services.saas.lead_sync import sync_outcome_to_lead

    return await sync_outcome_to_lead(
        outcome=outcome,
        tenant_id=record.get("tenant_id"),
        agent_id=record.get("agent_id"),
        meta=meta,
        call_id=call_id,
    )


async def _generate_outcome(
    transcript: list[dict[str, Any]],
    snapshot: dict[str, Any],
    meta: dict[str, Any],
    *,
    model: str,
) -> tuple[dict[str, Any], str | None]:
    settings = get_settings()
    if not transcript:
        empty = empty_outcome(model=model, reason="empty transcript")
        empty["summary_en"] = "No transcript was captured for this call."
        empty["next_action"] = "Review the call recording and telephony logs."
        return empty, "empty transcript"

    messages = [
        {
            "role": "developer",
            "content": (
                "You analyze completed voice calls. Output structured JSON only. "
                "Write the entire call summary in English only. Put it in summary_en. "
                "Leave summary_te as an empty string. "
                "Summaries must cover the entire call chronologically: caller intent, facts shared, "
                "agent response, objections, agreed next step, and how the call ended. "
                "Never claim an action was completed unless the transcript confirms it. "
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
    provider_id = "openai"
    locked_model = http_openai_model(settings)
    if is_realtime_llm_model(model):
        locked_model = http_openai_model(settings)
    elif model and not is_realtime_llm_model(model):
        locked_model = model
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
    turns = [
        f"{str(row.get('role') or 'unknown').title()}: {str(row.get('text') or '').strip()}"
        for row in transcript
        if str(row.get("text") or "").strip()
    ]
    failed["summary_en"] = (
        "Automatic summary generation failed. Transcript review: " + " ".join(turns)
    )[:2000]
    failed["next_action"] = "Review the transcript and captured facts."
    failed["extracted_fields"] = normalize_extracted_fields(snapshot.get("facts"))
    return failed, last_error


def _english_only_summaries(payload: dict[str, Any]) -> None:
    en = str(payload.get("summary_en") or "").strip()
    te = str(payload.get("summary_te") or "").strip()
    if not en and te:
        en = te
    payload["summary_en"] = filter_unrelated_scripts(en, "en-IN")
    payload["summary_te"] = ""


def _write_call_summary(call_id: str, outcome: dict[str, Any]) -> None:
    summary = {
        "call_id": call_id,
        "language_callback": outcome.get("language_callback"),
        "disposition": validate_disposition(outcome.get("disposition")),
        "disposition_confidence": outcome.get("disposition_confidence"),
        "summary_te": outcome.get("summary_te") or "",
        "summary_en": outcome.get("summary_en") or "",
        "next_action": outcome.get("next_action"),
        "extracted_fields": outcome.get("extracted_fields") or {},
        "facts": outcome.get("facts") or {},
        "status_tags": outcome.get("status_tags") or [],
        "objections": outcome.get("objections") or [],
        "model": outcome.get("model"),
        "generated_at": outcome.get("generated_at"),
        "generation_ok": outcome.get("generation_ok"),
    }
    call_summary_path(call_id).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


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
