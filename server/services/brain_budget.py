"""
Brain budget resolver — runtime override or env default.
"""
from __future__ import annotations

from server.config.env import get_settings
from server.services.runtime_settings import runtime_settings


def resolve_brain_budget(session_id: str) -> int:
    settings = get_settings()
    rt = runtime_settings.get(session_id)
    raw = rt.get("brainPromptBudgetTokens")
    if raw is not None:
        return int(raw)
    return int(settings.brain_prompt_budget_tokens)
