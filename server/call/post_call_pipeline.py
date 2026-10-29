"""Post-call pipeline â€” outcome LLM after hang-up. Never blocks call/end."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any
from weakref import WeakValueDictionary

from server.call.call_context import get as get_ctx
from server.call.call_ledger import call_ledger
from server.call.call_store import call_store
from server.call.memory_manager import memory_manager
from server.call.outcome_schema import (
    DISPOSITIONS,
    MODEL_STATUS_TAGS,
    OUTCOME_JSON_SCHEMA,
    derive_status_tags,
    empty_outcome,
    merge_outcome_facts,
    normalize_custom_tags,
    normalize_extracted_fields,
    normalize_model_tags,
    validate_disposition,
)
from server.call.paths import call_dir
from server.config.env import get_settings
from server.realtime.language_guard import filter_unrelated_scripts
from server.realtime.models import http_openai_model, is_realtime_llm_model
from server.utils.logger import logger

_QUEUE: asyncio.Queue[tuple[str, bool]] = asyncio.Queue(maxsize=1024)
_WORKER: asyncio.Task | None = None
_CALL_LOCKS: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_PENDING: dict[str, bool] = {}


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
    _ensure_worker()
    if call_id in _PENDING:
        _PENDING[call_id] = _PENDING[call_id] or force
        return
    _PENDING[call_id] = force
    try:
        await _QUEUE.put((call_id, force))
    except BaseException:
        _PENDING.pop(call_id, None)
        raise


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
        force = _PENDING.pop(call_id, force) or force
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
            and existing.get("prompt_version") == "outcome_v4"
            and not force
        ):
            if not existing.get("integration_dispatch_complete"):
                await reconcile_and_dispatch_post_call(call_id, existing)
                outcome_path(call_id).write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
                await _mark_outcome(call_id, "complete")
            return existing
        return await _run_outcome_locked(call_id)


async def _run_outcome_locked(call_id: str) -> dict[str, Any]:
    settings = get_settings()
    model = http_openai_model(settings)
    await _mark_outcome(call_id, "processing")
    transcript = call_ledger.read_lines(call_id)
    snapshot = memory_manager.get_snapshot(call_id)
    meta = call_ledger.read_meta(call_id)
    from server.services.saas.post_call_costs import capture_post_call_cost
    with capture_post_call_cost(call_id):
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
    payload["prompt_version"] = "outcome_v4"
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
    from server.call.order_confirmation import enforce_order_proof, read_order_proof

    order_proof = read_order_proof(
        call_id, tenant_id=str(meta.get("tenant_id") or "") or None
    )
    downgraded = enforce_order_proof(payload, order_proof)
    if downgraded:
        # Codes only: the proof holds customer details, the transcript holds words.
        logger.info("[ORDER] outcome downgraded call=%s reason=%s", call_id, downgraded)
        payload["summary_en"] = (
            (payload.get("summary_en") or "").rstrip()
            + "\n\nServer check: no confirmed order was recorded for this call, "
            "so it was not marked as converted."
        ).strip()
    # Server records outrank a model reading of the transcript, in both directions.
    if order_proof and str(order_proof.get("status") or "") == "confirmed" and payload.get("disposition") != "converted":
        payload["disposition"] = "converted"
        payload["next_action"] = payload.get("next_action") or "Fulfil the confirmed order recorded on this call."
    saved_callback = meta.get("callback_request") if isinstance(meta.get("callback_request"), dict) else None
    if saved_callback and not meta.get("callback_cancelled") \
            and str(saved_callback.get("status") or "requested") in {"requested", "saved", "scheduled"} \
            and payload.get("disposition") in {None, "no_outcome", "new_lead", "interested"}:
        payload["disposition"] = "callback_required"
        facts["callback_requested"] = "true"
    payload["disclosure_status"] = _detect_disclosure_delivery(transcript, meta)
    stored_pref = str((call_ledger.read_meta(call_id) or {}).get("contact_preference") or meta.get("contact_preference") or "none").strip().lower()
    payload["contact_preference"] = stored_pref
    if stored_pref == "do_not_call":
        # Consent is authoritative server state, not a sales-model judgement.
        # Do not surface an actionable callback alongside a permanent opt-out.
        payload["disposition"] = "not_interested"
        payload["next_action"] = "Do not contact this number. The caller opted out."
        for key in ("callback_requested", "callback_time", "requested_time", "callback_phone"):
            facts.pop(key, None)
    payload["status_tags"] = derive_status_tags(
        payload.get("disposition"),
        facts,
        next_action=payload.get("next_action"),
        objections=payload.get("objections"),
        model_tags=payload.get("tags"),
        custom_tags=payload.get("custom_tags"),
        disclosure_status=payload.get("disclosure_status"),
        agent_failure=bool(call_ledger.read_failed_turns(call_id)),
        contact_preference=payload["contact_preference"],
    )
    outcome_path(call_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_call_summary(call_id, payload)
    status = "complete" if error is None else "failed"
    await call_store.update(
        call_id,
        {"disposition": payload["disposition"], "status_tags": payload["status_tags"]},
    )
    # The judgement above is only useful if it lands in the CRM, attributed to the
    # agent that took the call. Runs last so a lead write can never invalidate the
    # outcome the console reads, and swallows its own errors for the same reason.
    payload["lead"] = await _sync_lead(call_id, payload, meta)
    if payload.get("lead"):
        from server.services.saas.lead_scoring import assessment_time, persist_assessment
        payload["lead_assessment"] = await persist_assessment(
            str(meta.get("tenant_id") or ""), str(meta.get("agent_id") or ""),
            payload["lead"]["leadId"], call_id, payload, at=assessment_time(meta),
        )
    else:
        from server.services.saas.lead_scoring import assess_existing_contact
        payload["lead_assessment"] = await assess_existing_contact(meta, call_id, payload)
    try:
        await reconcile_and_dispatch_post_call(call_id, payload)
    except Exception as exc:
        logger.warning("[POST_CALL] Integration dispatch interrupted: %s", type(exc).__name__)
        raise
    outcome_path(call_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    await _mark_outcome(call_id, status)
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


def _outcome_models(meta: dict[str, Any], *, openai_model: str) -> list[tuple[str, str, str | None]]:
    """The call's own text LLM first, then OpenAI; one provider outage must not blank every outcome.

    Calls on a Sarvam stack were marked no_outcome whenever the separate OpenAI account
    was exhausted, although the model that ran the conversation was available.
    """
    from server.providers import get_provider_registry

    registry = get_provider_registry()
    llm = ((meta.get("resolved_stack") or {}).get("llm") or {}) if isinstance(meta.get("resolved_stack"), dict) else {}
    candidates: list[tuple[str, str, str | None]] = []
    provider, call_model = str(llm.get("provider") or ""), str(llm.get("model") or "")
    if provider and provider != "openai" and call_model and not is_realtime_llm_model(call_model):
        try:
            if registry.is_provider_enabled(provider, "llm") and registry.is_model_allowed(provider, "llm", call_model):
                candidates.append((provider, call_model, (llm.get("config") or {}).get("api_mode")))
        except Exception:
            pass
    candidates.append(("openai", openai_model, None))
    return candidates


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
                "A caller requesting an order or discussing buying details is interested, not merely new_lead. "
                "A callback is the business calling the caller; I will call you is not callback_required. "
                "Refusing a callback or one product is not refusing all contact. "
                "Do not treat an agent's unsupported promise as proof of success. "
                "extracted_fields must be an array of {key, value} strings "
                "(name, budget, slot, etc). Use [] if nothing was captured. "
                "Disposition rubric: new_lead (first contact/info captured), interested "
                "(positive, not yet qualified), qualified (meets criteria), site_visit_planned "
                "(concrete appointment), callback_required (explicit follow-up), not_interested "
                "(clear rejection), wrong_number, converted (goal achieved), no_outcome "
                "(<3 turns or inconclusive). "
                "tags: choose 2-6 tags that best describe what the caller wanted and how the "
                "call went. Use only this allow-list: "
                + ", ".join(sorted(MODEL_STATUS_TAGS))
                + ". "
                "custom_tags: up to 3 short lowercase hyphenated topical tags specific to this "
                "business or conversation (for example solar-rooftop, two-bedroom, delivery-date). "
                "Never include company, carrier or vendor names. "
                "Do not emit outcome:, contact:, compliance: or quality: tags — the server "
                "derives those from the transcript."
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
    locked_model = http_openai_model(settings)
    if model and not is_realtime_llm_model(model):
        locked_model = model
    candidates = _outcome_models(meta, openai_model=locked_model)
    for attempt in range(retries * len(candidates)):
        provider_id, candidate_model, api_mode = candidates[attempt % len(candidates)]
        try:
            from server.providers import get_provider_registry
            from server.providers.base import LLMConfig

            registry = get_provider_registry()
            adapter = registry.get_llm(provider_id)
            extra = {"api_mode": api_mode} if api_mode else {}
            payload = await adapter.structured_completion(
                messages,
                OUTCOME_JSON_SCHEMA,
                LLMConfig(provider=provider_id, model=candidate_model),
                schema_name="call_outcome",
                max_output_tokens=1200,
                **extra,
            )
            if not isinstance(payload, dict):
                raise ValueError("outcome payload is not an object")
            payload["extracted_fields"] = normalize_extracted_fields(payload.get("extracted_fields"))
            payload["tags"] = normalize_model_tags(payload.get("tags"))
            payload["custom_tags"] = normalize_custom_tags(payload.get("custom_tags"))
            payload.setdefault("objections", [])
            payload.setdefault("next_action", None)
            payload.setdefault("summary_te", "")
            payload.setdefault("summary_en", "")
            payload.setdefault("disposition_confidence", 0.0)
            payload["outcome_provider"] = provider_id
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


#: Recording disclosures are paraphrased, but every phrasing names "record" —
#: including the loanword used across Indian languages. Used only to audit that
#: the disclosure was delivered, never to generate it.
_DISCLOSURE_RE = re.compile(
    r"record|recording|recorded|రికార్డ|रिकॉर्ड|रेकॉर्ड|பதிவ|ರೆಕಾರ್ಡ|റെക്കോർഡ|রেকর্ড",
    re.IGNORECASE,
)


def _detect_disclosure_delivery(
    transcript: list[dict[str, Any]], meta: dict[str, Any]
) -> str | None:
    """Whether an enabled disclosure was actually spoken in the conversation."""
    info = (meta or {}).get("recording_disclosure")
    if not isinstance(info, dict) or not info.get("enabled") or not info.get("injected"):
        return None
    for row in transcript or []:
        if str(row.get("role") or "").lower() not in ("assistant", "agent"):
            continue
        if _DISCLOSURE_RE.search(str(row.get("text") or "")):
            return "delivered"
    return "missing"


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
        "tags": outcome.get("tags") or [],
        "custom_tags": outcome.get("custom_tags") or [],
        "disclosure_status": outcome.get("disclosure_status"),
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


async def get_agent_post_call_actions(tenant_id: str, agent_id: str) -> list[str]:
    """Retrieve whitelisted post_call actions for this agent."""
    import uuid
    from sqlalchemy import select
    from server.db.connection import get_session_factory
    from server.db.models.integration_models import AgentIntegration

    session_factory = get_session_factory()
    if not session_factory:
        return []
    try:
        async with session_factory() as session:
            stmt = select(AgentIntegration).where(
                AgentIntegration.tenant_id == uuid.UUID(str(tenant_id)),
                AgentIntegration.agent_id == uuid.UUID(str(agent_id)),
                AgentIntegration.timing_mode == "post_call",
                AgentIntegration.enabled.is_(True),
            )
            res = await session.execute(stmt)
            integrations = res.scalars().all()
            from server.services.tool_schema_registry import _normalize, tool_definition
            actions = set()
            for integration in integrations:
                # Connecting an app is not consent to automatic outbound messages.
                for action in integration.action_whitelist or []:
                    definition = tool_definition(action)
                    if definition and definition[0] == _normalize(integration.app_name):
                        actions.add(action.upper())
            return sorted(actions)
    except Exception as exc:
        logger.warning("[POST_CALL] Failed to fetch agent post call actions: %s", exc)
        return []


async def reconcile_and_dispatch_post_call(call_id: str, outcome: dict[str, Any]) -> None:
    """Execute explicitly configured actions using the durable write claim.

    Unknown in-call results stay unknown. They require provider verification,
    never a local status change or an automatic repeat of the external write.
    """
    import uuid
    from sqlalchemy import select
    from server.db.connection import get_session_factory
    from server.db.models.integration_models import ToolExecution
    from server.services.tool_router import tool_router
    from server.services.tool_schema_registry import tool_definition

    record = await call_store.get(call_id)
    if not record or not record.get("tenant_id") or not record.get("agent_id"):
        return
    tenant_id, agent_id = str(record["tenant_id"]), str(record["agent_id"])
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Integration tracking unavailable")
    async with factory() as session:
        pending = (await session.execute(select(ToolExecution).where(
            ToolExecution.tenant_id == uuid.UUID(tenant_id), ToolExecution.call_id == str(call_id),
            ToolExecution.status.in_(["initiated", "timed_out_pending"]),
        ))).scalars().all()
        outcome["integration_review_required"] = len(pending)
    actions = await get_agent_post_call_actions(tenant_id, agent_id)
    facts = outcome.get("extracted_fields") or {}
    if not isinstance(facts, dict):
        facts = {}
    results = []
    for action in actions:
        definition = tool_definition(action)
        properties = definition[1]["parameters"].get("properties", {})
        # Only actual extracted values are used. Missing resource IDs, recipients
        # or other required setup are rejected by the action schema.
        arguments = {key: facts[key] for key in properties if key in facts}
        result = await tool_router.route_and_execute(
            tenant_id, agent_id, str(call_id), action, arguments, timing="post_call",
        )
        results.append({"action": action, "result": result})
    outcome["integration_results"] = results
    outcome["integration_dispatch_complete"] = True
