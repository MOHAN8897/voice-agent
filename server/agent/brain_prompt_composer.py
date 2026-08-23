"""
Brain prompt composer — merges factory sections + user overrides into ONE plain-text prompt.
"""
from __future__ import annotations

from server.prompts.brain_prompt import DEFAULT_BRAIN_PROMPT_SECTIONS

MAX_BEHAVIOUR_CHARS = 8_000
MAX_BUSINESS_CHARS = 8_000
MAX_BRAIN_PROMPT_WORDS = 2_500
MAX_BRAIN_PROMPT_CHARS = 50_000  # safety cap; primary limit is word count
BUDGET_MIN_TOKENS = 1_500
BUDGET_MAX_TOKENS = 2_500


class PromptBudgetExceeded(Exception):
    def __init__(self, estimated: int, budget: int, *, words: int | None = None, word_limit: int | None = None):
        self.estimated = estimated
        self.budget = budget
        self.over_by = estimated - budget
        self.words = words
        self.word_limit = word_limit
        if word_limit is not None and words is not None and words > word_limit:
            super().__init__(
                f"Brain prompt is {words} words but the limit is {word_limit}. Shorten your brain prompt."
            )
        else:
            super().__init__(
                f"Brain prompt is {estimated} tokens but budget is {budget}. "
                f"Shorten your brain prompt or increase the budget slider (max {BUDGET_MAX_TOKENS} tokens)."
            )


def estimate_tokens(text: str) -> int:
    """Rough token estimate (chars / 4). Good enough for budget validation."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def count_words(text: str) -> int:
    if not text or not text.strip():
        return 0
    return len(text.split())


def _strip_legacy_tags(text: str) -> str:
    for tag in (
        "agent_behaviour_instructions",
        "business_context_instructions",
        "user_custom_instructions",
    ):
        text = text.replace(f"<{tag}>", "").replace(f"</{tag}>", "")
    return text.strip()


def sanitize_behaviour(text: str) -> str:
    if not text:
        return ""
    return _strip_legacy_tags(text.strip()[:MAX_BEHAVIOUR_CHARS])


def sanitize_business(text: str) -> str:
    if not text:
        return ""
    return _strip_legacy_tags(text.strip()[:MAX_BUSINESS_CHARS])


def sanitize_user_instructions(text: str) -> str:
    return sanitize_behaviour(text)


def sanitize_brain_prompt(text: str) -> str:
    if not text:
        return ""
    return _strip_legacy_tags(text.strip()[:MAX_BRAIN_PROMPT_CHARS])


def compose_brain_prompt(
    *,
    behaviour: str = "",
    business: str = "",
    language: str = "te-IN",
    style: str | None = None,
) -> str:
    """Merge sections into ONE string. No runtime trimming."""
    behaviour = sanitize_behaviour(behaviour) or DEFAULT_BRAIN_PROMPT_SECTIONS["behaviour"]
    business = sanitize_business(business) or DEFAULT_BRAIN_PROMPT_SECTIONS["business"]
    style_line = style or "very brief, 1-2 sentences, spoken Telugu"

    parts = [
        DEFAULT_BRAIN_PROMPT_SECTIONS["safety"],
        DEFAULT_BRAIN_PROMPT_SECTIONS["telugu"],
        f"--- BEHAVIOUR ---\n{behaviour}",
        f"--- BUSINESS ---\n{business}",
        f"Language: {language}. Style: {style_line}.",
    ]
    return "\n\n".join(parts)


def compose_brain_prompt_sections(
    *,
    behaviour: str = "",
    business: str = "",
    language: str = "te-IN",
    style: str | None = None,
) -> dict[str, str]:
    behaviour = sanitize_behaviour(behaviour) or DEFAULT_BRAIN_PROMPT_SECTIONS["behaviour"]
    business = sanitize_business(business) or DEFAULT_BRAIN_PROMPT_SECTIONS["business"]
    style_line = style or "very brief, 1-2 sentences, spoken Telugu"
    return {
        "safety": DEFAULT_BRAIN_PROMPT_SECTIONS["safety"],
        "telugu": DEFAULT_BRAIN_PROMPT_SECTIONS["telugu"],
        "behaviour": behaviour,
        "business": business,
        "footer": f"Language: {language}. Style: {style_line}.",
    }


def validate_brain_prompt_budget(text: str, budget_tokens: int) -> int:
    """Returns estimated tokens; raises PromptBudgetExceeded if over limits."""
    est = estimate_tokens(text)
    words = count_words(text)
    if words > MAX_BRAIN_PROMPT_WORDS:
        raise PromptBudgetExceeded(est, budget_tokens, words=words, word_limit=MAX_BRAIN_PROMPT_WORDS)
    budget_tokens = max(BUDGET_MIN_TOKENS, min(BUDGET_MAX_TOKENS, int(budget_tokens)))
    if est > budget_tokens:
        raise PromptBudgetExceeded(est, budget_tokens, words=words)
    return est


def section_token_estimates(sections: dict[str, str]) -> dict[str, int]:
    return {k: estimate_tokens(v) for k, v in sections.items()}
