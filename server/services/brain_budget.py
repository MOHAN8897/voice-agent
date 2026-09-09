"""
Brain budget resolver — runtime override or env default.
"""
from __future__ import annotations

from server.config.env import get_settings
from server.services.runtime_settings import runtime_settings


def resolve_brain_budget(session_id: str) -> int:
    """Runtime override, else saved instruction budget, else env default.

    Live turns must not keep a stale 3.5k budget when the session brain is ~6k+.
    """
    from server.agent.brain_prompt_composer import BUDGET_MAX_TOKENS, BUDGET_MIN_TOKENS

    settings = get_settings()
    rt = runtime_settings.get(session_id)
    candidates: list[int] = []
    raw = rt.get("brainPromptBudgetTokens")
    if raw is not None:
        try:
            candidates.append(int(raw))
        except (TypeError, ValueError):
            pass
    try:
        from server.agent.instruction_store import instruction_store

        meta = instruction_store.get_with_meta(session_id)
        stored = meta.get("budgetTokens")
        if stored is not None:
            candidates.append(int(stored))
        est = meta.get("estimatedTokens")
        if est is not None:
            candidates.append(int(est))
    except Exception:
        pass
    candidates.append(int(settings.brain_prompt_budget_tokens))
    budget = max(candidates) if candidates else int(settings.brain_prompt_budget_tokens)
    return max(BUDGET_MIN_TOKENS, min(BUDGET_MAX_TOKENS, budget))
