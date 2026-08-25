"""
Metrics & Prompt transparency — server/routes/metrics.py
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from server.agent.brain_prompt_composer import (
    compose_brain_prompt_sections,
    estimate_tokens,
    section_token_estimates,
)
from server.agent.conversation_manager import conversation_manager
from server.agent.instruction_store import instruction_store
from server.agent.session_memory import session_memory
from server.config.constants import constants
from server.config.env import get_settings
from server.services.brain_budget import resolve_brain_budget
from server.services.prompt_cache_key import cache_eligible
from server.services.prompt_cache_tracker import prompt_cache_tracker
from server.utils.metrics import metrics

router = APIRouter()


@router.get("/api/metrics/calls/{call_id}")
async def call_metrics(call_id: str):
    from server.call.call_ledger import call_ledger
    from server.call.call_store import call_store
    from server.call.memory_manager import memory_manager

    stored = await call_store.get(call_id)
    if stored is None and not call_ledger.meta_path(call_id).exists():
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Call not found"}},
        )
    trace = call_ledger.read_trace(call_id)
    turns = trace.get("turns") or []
    memory_ops = sum(int(t.get("memory_ops_applied") or 0) for t in turns)
    return {
        "call_id": call_id,
        "trace": trace,
        "aggregates": {
            "turns": len(turns),
            "memory_ops_applied": memory_ops,
            "stt_final_ms": [t.get("stt_final_ms") for t in turns],
            "llm_ttft_ms": [t.get("llm_ttft_ms") for t in turns],
        },
        "memory": memory_manager.get_snapshot(call_id),
        "call": stored,
    }


@router.get("/api/metrics")
async def get_metrics():
    snap = metrics.snapshot()
    snap["sessions"] = conversation_manager.stats()
    snap["instruction_sessions"] = instruction_store.stats()
    snap["prompt_cache"] = prompt_cache_tracker.snapshot()
    snap["version"] = constants.APP_VERSION
    try:
        snap["model"] = get_settings().openai_model
    except Exception:
        snap["model"] = "unknown"
    return snap


@router.post("/api/metrics/reset")
async def reset_metrics():
    metrics.reset()
    prompt_cache_tracker.reset()
    return {"ok": True, "reset": True}


@router.get("/api/prompt/effective")
async def effective_prompt(
    sessionId: str = Query("default"),
    transcript: str = Query("Python అంటే ఏమిటి?", max_length=5000),
    language_code: str = Query("te-IN"),
):
    behaviour = instruction_store.get_behaviour(sessionId)
    business = instruction_store.get_business(sessionId)
    style = instruction_store.get_style(sessionId)
    budget = resolve_brain_budget(sessionId)

    brain_prompt = instruction_store.get_brain_prompt(
        sessionId,
        language=language_code,
        budget_tokens=budget,
    )
    estimated = estimate_tokens(brain_prompt)
    section_tokens = section_token_estimates(
        compose_brain_prompt_sections(
            behaviour=behaviour,
            business=business,
            language=language_code,
            style=style,
        )
    )

    settings = get_settings()
    history = conversation_manager.get_context_for_brain(
        sessionId,
        max_turns=settings.brain_context_turns,
    )
    summary = session_memory.get_summary(sessionId) if settings.enable_session_summary else ""
    history_est = estimate_tokens(" ".join(str(m.get("content", "")) for m in history))
    transcript_est = estimate_tokens(transcript)
    summary_est = estimate_tokens(summary) if summary else 0

    return {
        "sessionId": sessionId,
        "language_code": language_code,
        "brainPrompt": brain_prompt,
        "estimatedTokens": estimated,
        "budgetTokens": budget,
        "headroom": max(0, budget - estimated),
        "cacheEligible": cache_eligible(estimated),
        "sections": section_tokens,
        "conversation_history_len": len(conversation_manager.get_history(sessionId)),
        "brain_context_turns": settings.brain_context_turns,
        "brain_context_messages": len(history),
        "session_summary_enabled": settings.enable_session_summary,
        "session_summary": summary or None,
        "token_estimates": {
            "brain": estimated,
            "history": history_est,
            "summary": summary_est,
            "transcript": transcript_est,
            "total_input_est": estimated + history_est + summary_est + transcript_est,
        },
        "current_transcript": transcript[:300],
        "channels": {
            "behaviour_present": bool(behaviour),
            "behaviour_chars": len(behaviour),
            "business_present": bool(business),
            "business_chars": len(business),
            "style": style,
        },
    }
