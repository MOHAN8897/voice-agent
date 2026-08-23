"""
Metrics & Prompt transparency — server/routes/metrics.py
GET /api/metrics → p50/p95 per stage (industry standard)
GET /api/prompt/effective?sessionId=&transcript= → shows built developer instructions (no secrets)
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from server.agent.conversation_manager import conversation_manager
from server.agent.instruction_builder import build_agent_instructions
from server.agent.instruction_store import instruction_store
from server.config.constants import constants
from server.config.env import get_settings
from server.prompts.system_prompt import CORE_SYSTEM_PROMPT
from server.utils.metrics import metrics

router = APIRouter()


@router.get("/api/metrics")
async def get_metrics():
    snap = metrics.snapshot()
    snap["sessions"] = conversation_manager.stats()
    snap["instruction_sessions"] = instruction_store.stats()
    snap["version"] = constants.APP_VERSION
    try:
        snap["model"] = get_settings().openai_model
    except Exception:
        snap["model"] = "unknown"
    return snap


@router.post("/api/metrics/reset")
async def reset_metrics():
    metrics.reset()
    return {"ok": True, "reset": True}


@router.get("/api/prompt/effective")
async def effective_prompt(
    sessionId: str = Query("default"),
    transcript: str = Query("Python అంటే ఏమిటి?", max_length=5000),
    language_code: str = Query("te-IN"),
):
    """
    Returns the effective prompt hierarchy for transparency (no secrets).
    Shows System core + wrapped BEHAVIOUR + wrapped BUSINESS + style.
    """
    behaviour = instruction_store.get_behaviour(sessionId)
    business = instruction_store.get_business(sessionId)
    style = instruction_store.get_style(sessionId)
    developer_instructions = build_agent_instructions(
        core_instructions=CORE_SYSTEM_PROMPT,
        behaviour_instructions=behaviour,
        business_instructions=business,
        language=language_code,
        response_style=style,
    )

    def _clip(t: str, n: int = 700) -> str:
        return t[:n] + ("..." if len(t) > n else "")

    return {
        "hierarchy": {
            "1_system_safety": "System instructions are server-enforced (never overridden by user).",
            "2_core": CORE_SYSTEM_PROMPT[:600] + "...",
            "3a_behaviour_wrapped": f"<agent_behaviour_instructions>{_clip(behaviour)}</agent_behaviour_instructions>" if behaviour else "(none)",
            "3b_business_wrapped": f"<business_context_instructions>{_clip(business)}</business_context_instructions>" if business else "(none)",
            "5_conversation_history_len": len(conversation_manager.get_history(sessionId)),
            "6_current_transcript": transcript[:300],
        },
        "developer_instructions_preview": developer_instructions[:3400],
        "full_developer_instructions_length": len(developer_instructions),
        "sessionId": sessionId,
        "language_code": language_code,
        "channels": {
            "behaviour_present": bool(behaviour),
            "behaviour_chars": len(behaviour),
            "business_present": bool(business),
            "business_chars": len(business),
            "style": style,
        },
    }
