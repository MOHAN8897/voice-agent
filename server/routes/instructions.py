"""
Instructions routes — server/routes/instructions.py
Dual-channel prompting: behavioural (how to respond) + business (client's domain knowledge).
Each capped at 10,000 chars server-side.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from server.agent.instruction_store import instruction_store
from server.config.env import get_settings, ConfigError

router = APIRouter()


def _limits() -> tuple[int, int]:
    try:
        _ = get_settings()
    except ConfigError:
        pass
    from server.agent.instruction_builder import MAX_BEHAVIOUR_INSTRUCTIONS, MAX_BUSINESS_INSTRUCTIONS
    return MAX_BEHAVIOUR_INSTRUCTIONS, MAX_BUSINESS_INSTRUCTIONS


class SaveRequest(BaseModel):
    sessionId: str = Field("default", max_length=100)
    behaviourInstructions: str | None = Field(None, description="HOW the agent should respond")
    businessInstructions: str | None = Field(None, description="Client business knowledge / domain grounding")
    # Legacy field — mapped to behaviour for backward compatibility with old clients
    instructions: str | None = Field(None, max_length=10000)
    responseStyle: str | None = Field(None, max_length=100)


@router.post("/api/instructions")
async def save_instructions(body: SaveRequest):
    b_max, z_max = _limits()

    behaviour = body.behaviourInstructions if body.behaviourInstructions is not None else body.instructions or ""
    if len(behaviour) > b_max:
        behaviour = behaviour[:b_max]
    business = body.businessInstructions or ""
    if len(business) > z_max:
        business = business[:z_max]

    saved = instruction_store.save(body.sessionId, behaviour, business, body.responseStyle)
    return {
        "ok": True,
        "sessionId": body.sessionId,
        "behaviour": saved["behaviour"],
        "business": saved["business"],
        "responseStyle": saved["style"],
        "behaviourLength": len(saved["behaviour"]),
        "businessLength": len(saved["business"]),
        "updatedAt": saved["updatedAt"],
    }


@router.get("/api/instructions")
async def get_instructions(sessionId: str = "default"):
    meta = instruction_store.get_with_meta(sessionId)
    limits = {"behaviourMax": _limits()[0], "businessMax": _limits()[1]}
    return {"sessionId": sessionId, **meta, "limits": limits}


@router.delete("/api/instructions")
async def clear_instructions(sessionId: str = "default"):
    instruction_store.clear(sessionId)
    return {"ok": True, "sessionId": sessionId, "cleared": True}
