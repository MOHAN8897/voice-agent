"""
Instructions routes — dual-channel editing; composed into single brainPrompt on save.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from server.agent.brain_prompt_composer import (
    MAX_BEHAVIOUR_CHARS,
    MAX_BUSINESS_CHARS,
    PromptBudgetExceeded,
)
from server.agent.instruction_store import instruction_store
from server.agent.session_memory import session_memory
from server.config.env import get_settings, ConfigError
from server.services.brain_budget import resolve_brain_budget
from server.services.prompt_cache_key import cache_eligible

router = APIRouter()


def _limits() -> tuple[int, int]:
    try:
        _ = get_settings()
    except ConfigError:
        pass
    return MAX_BEHAVIOUR_CHARS, MAX_BUSINESS_CHARS


class SaveRequest(BaseModel):
    sessionId: str = Field("default", max_length=100)
    behaviourInstructions: str | None = Field(None, description="HOW the agent should respond")
    businessInstructions: str | None = Field(None, description="Client business knowledge / domain grounding")
    instructions: str | None = Field(None, max_length=MAX_BEHAVIOUR_CHARS)
    responseStyle: str | None = Field(None, max_length=100)
    brainPromptBudgetTokens: int | None = Field(None, description="Optional budget override for validation")


@router.post("/api/instructions")
async def save_instructions(body: SaveRequest):
    b_max, z_max = _limits()

    behaviour = body.behaviourInstructions if body.behaviourInstructions is not None else body.instructions or ""
    if len(behaviour) > b_max:
        behaviour = behaviour[:b_max]
    business = body.businessInstructions or ""
    if len(business) > z_max:
        business = business[:z_max]

    budget = body.brainPromptBudgetTokens or resolve_brain_budget(body.sessionId)

    try:
        saved = instruction_store.save(
            body.sessionId,
            behaviour,
            business,
            body.responseStyle,
            budget_tokens=budget,
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

    return {
        "ok": True,
        "sessionId": body.sessionId,
        "behaviour": saved["behaviour"],
        "business": saved["business"],
        "responseStyle": saved["style"],
        "brainPrompt": saved["brainPrompt"][:500] + ("..." if len(saved["brainPrompt"]) > 500 else ""),
        "estimatedTokens": saved["estimatedTokens"],
        "budgetTokens": saved["budgetTokens"],
        "headroom": saved["budgetTokens"] - saved["estimatedTokens"],
        "cacheEligible": cache_eligible(saved["estimatedTokens"]),
        "behaviourLength": len(saved["behaviour"]),
        "businessLength": len(saved["business"]),
        "updatedAt": saved["updatedAt"],
    }


@router.get("/api/instructions")
async def get_instructions(sessionId: str = "default"):
    meta = instruction_store.get_with_meta(sessionId)
    limits = {"behaviourMax": _limits()[0], "businessMax": _limits()[1]}
    budget = resolve_brain_budget(sessionId)
    est = int(meta.get("estimatedTokens") or 0)
    return {
        "sessionId": sessionId,
        **meta,
        "budgetTokens": budget,
        "headroom": max(0, budget - est),
        "cacheEligible": cache_eligible(est),
        "limits": limits,
    }


@router.delete("/api/instructions")
async def clear_instructions(sessionId: str = "default"):
    instruction_store.clear(sessionId)
    session_memory.clear(sessionId)
    return {"ok": True, "sessionId": sessionId, "cleared": True}
