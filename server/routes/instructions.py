"""
Instructions routes — single brain prompt editing; legacy behaviour/business still supported.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from server.agent.brain_prompt_composer import (
    BUDGET_MAX_TOKENS,
    BUDGET_MIN_TOKENS,
    MAX_BEHAVIOUR_CHARS,
    MAX_BRAIN_PROMPT_CHARS,
    MAX_BRAIN_PROMPT_WORDS,
    MAX_BUSINESS_CHARS,
    PromptBudgetExceeded,
    estimate_tokens,
)
from server.agent.instruction_store import instruction_store
from server.agent.session_memory import session_memory
from server.config.env import get_settings, ConfigError
from server.prompts.brain_prompt import get_factory_brain_prompt
from server.services.brain_budget import resolve_brain_budget
from server.services.prompt_cache_key import cache_eligible

router = APIRouter()

CACHE_MIN_TOKENS = 1024


def _limits() -> tuple[int, int, int]:
    try:
        _ = get_settings()
    except ConfigError:
        pass
    return MAX_BEHAVIOUR_CHARS, MAX_BUSINESS_CHARS, MAX_BRAIN_PROMPT_CHARS


class SaveRequest(BaseModel):
    sessionId: str = Field("default", max_length=100)
    brainPrompt: str | None = Field(None, description="Single composed brain prompt (preferred)")
    behaviourInstructions: str | None = Field(None, description="Legacy: HOW the agent should respond")
    businessInstructions: str | None = Field(None, description="Legacy: business knowledge")
    instructions: str | None = Field(None, max_length=MAX_BEHAVIOUR_CHARS)
    responseStyle: str | None = Field(None, max_length=100)
    brainPromptBudgetTokens: int | None = Field(None, description="Optional budget override for validation")
    language_code: str | None = Field("te-IN", max_length=16)


@router.get("/api/instructions/default")
async def get_default_brain_prompt():
    """Factory default brain prompt for the UI editor."""
    prompt = get_factory_brain_prompt()
    est = estimate_tokens(prompt)
    return {
        "brainPrompt": prompt,
        "estimatedTokens": est,
        "cacheMinTokens": CACHE_MIN_TOKENS,
        "budgetMinTokens": BUDGET_MIN_TOKENS,
        "budgetMaxTokens": BUDGET_MAX_TOKENS,
        "maxWords": MAX_BRAIN_PROMPT_WORDS,
        "cacheEligible": cache_eligible(est),
        "maxChars": MAX_BRAIN_PROMPT_CHARS,
    }


@router.post("/api/instructions")
async def save_instructions(body: SaveRequest):
    b_max, z_max, p_max = _limits()
    budget = body.brainPromptBudgetTokens or resolve_brain_budget(body.sessionId)
    budget = max(BUDGET_MIN_TOKENS, min(BUDGET_MAX_TOKENS, int(budget)))

    try:
        if body.brainPrompt is not None:
            if len(body.brainPrompt) > p_max:
                raise HTTPException(
                    status_code=400,
                    detail={"error": {"code": "validation_error", "message": f"Brain prompt exceeds {p_max} characters"}},
                )
            est = estimate_tokens(body.brainPrompt)
            if est > budget and est <= BUDGET_MAX_TOKENS:
                budget = est
            saved = instruction_store.save_brain_prompt(body.sessionId, body.brainPrompt, budget_tokens=budget)
        else:
            behaviour = body.behaviourInstructions if body.behaviourInstructions is not None else body.instructions or ""
            if len(behaviour) > b_max:
                behaviour = behaviour[:b_max]
            business = body.businessInstructions or ""
            if len(business) > z_max:
                business = business[:z_max]
            from server.brain.session_brain_compiler import compile_session_brain

            prev_meta = instruction_store.get_with_meta(body.sessionId)
            prev_compiled = prev_meta.get("brainPrompt") if prev_meta.get("compiledVersion") else None
            compiled, opt, raw_est, compiled_est = await compile_session_brain(
                behaviour=behaviour,
                business=business,
                language=body.language_code or "te-IN",
                style=body.responseStyle,
                budget_tokens=budget,
                previous_compiled=prev_compiled,
            )
            saved = instruction_store.save_compiled(
                body.sessionId,
                behaviour,
                business,
                body.responseStyle,
                compiled_brain=compiled,
                optimizer_report=opt.to_dict(),
                source_checksum=opt.source_checksum,
                language=body.language_code or "te-IN",
                budget_tokens=budget,
                raw_token_estimate=raw_est,
            )
    except PromptBudgetExceeded as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "prompt_budget_exceeded",
                    "message": str(e),
                    "estimatedTokens": e.estimated,
                    "budgetTokens": e.budget,
                    "overBy": e.over_by,
                }
            },
        ) from e

    try:
        if get_settings().use_versioned_brains:
            from server.brain.instruction_bridge import sync_legacy_instructions_to_business_brain

            await sync_legacy_instructions_to_business_brain(
                behaviour=saved.get("behaviour", ""),
                business=saved.get("business", ""),
            )
    except Exception:
        pass

    return {
        "ok": True,
        "sessionId": body.sessionId,
        "brainPrompt": saved["brainPrompt"][:800] + ("..." if len(saved["brainPrompt"]) > 800 else ""),
        "brainPromptFull": saved["brainPrompt"],
        "compiledBrainPrompt": saved["brainPrompt"],
        "estimatedTokens": saved["estimatedTokens"],
        "budgetTokens": saved["budgetTokens"],
        "headroom": saved["budgetTokens"] - saved["estimatedTokens"],
        "cacheEligible": cache_eligible(saved["estimatedTokens"]),
        "cacheMinTokens": CACHE_MIN_TOKENS,
        "customBrainPrompt": saved.get("customBrainPrompt", False),
        "behaviour": saved.get("behaviour", ""),
        "business": saved.get("business", ""),
        "responseStyle": saved.get("style"),
        "behaviourLength": len(saved.get("behaviour") or ""),
        "businessLength": len(saved.get("business") or ""),
        "updatedAt": saved["updatedAt"],
        "compiledVersion": saved.get("compiledVersion", 0),
        "optimizerReport": saved.get("optimizerReport"),
        "rawTokenEstimate": saved.get("rawTokenEstimate", 0),
        "tokensSaved": max(0, int(saved.get("rawTokenEstimate") or 0) - int(saved.get("estimatedTokens") or 0)),
    }


@router.get("/api/instructions")
async def get_instructions(sessionId: str = "default", includeCompiled: bool = Query(False)):
    meta = instruction_store.get_with_meta(sessionId)
    b_max, z_max, p_max = _limits()
    budget = resolve_brain_budget(sessionId)
    est = int(meta.get("estimatedTokens") or estimate_tokens(meta.get("brainPrompt") or ""))
    if not meta.get("present"):
        default = get_factory_brain_prompt()
        meta["brainPrompt"] = default
        est = estimate_tokens(default)
    payload = {
        "sessionId": sessionId,
        **meta,
        "budgetTokens": budget,
        "headroom": max(0, budget - est),
        "cacheEligible": cache_eligible(est),
        "cacheMinTokens": CACHE_MIN_TOKENS,
        "budgetMinTokens": BUDGET_MIN_TOKENS,
        "budgetMaxTokens": BUDGET_MAX_TOKENS,
        "maxWords": MAX_BRAIN_PROMPT_WORDS,
        "limits": {
            "brainPromptMax": p_max,
            "behaviourMax": b_max,
            "businessMax": z_max,
            "maxWords": MAX_BRAIN_PROMPT_WORDS,
        },
    }
    if not includeCompiled:
        payload.pop("brainPrompt", None)
    return payload


@router.delete("/api/instructions")
async def clear_instructions(sessionId: str = "default"):
    instruction_store.clear(sessionId)
    session_memory.clear(sessionId)
    return {"ok": True, "sessionId": sessionId, "cleared": True}
