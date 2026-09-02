"""
Brain prompt composer — merges factory sections + user overrides into ONE plain-text prompt.
"""
from __future__ import annotations

from server.prompts.brain_prompt import DEFAULT_BRAIN_PROMPT_SECTIONS

# User-editable sections stay small so the composed brain stays cache-eligible
# (≥1024 tokens) without crowding dynamic memory after the cache breakpoint.
# Static factory prefix is ~900 tokens; leave ~150-400 tokens for memory/history.
MAX_BEHAVIOUR_CHARS = 2_000
MAX_BUSINESS_CHARS = 2_400
MAX_BEHAVIOUR_WORDS = 280
MAX_BUSINESS_WORDS = 320
MAX_AGENT_BRIEF_CHARS = 1_200
MAX_AGENT_BRIEF_WORDS = 180
RECOMMENDED_AGENT_BRIEF_WORDS = 80
RECOMMENDED_BEHAVIOUR_WORDS = 180
RECOMMENDED_BUSINESS_WORDS = 220
MAX_BRAIN_PROMPT_WORDS = 1_800
MAX_BRAIN_PROMPT_CHARS = 12_000
BUDGET_MIN_TOKENS = 1_500
BUDGET_MAX_TOKENS = 2_500
CACHE_MIN_TOKENS = 1_024
MEMORY_HEADROOM_TOKENS = 300


class PromptSectionTooLong(Exception):
    def __init__(self, section: str, words: int, word_limit: int, chars: int, char_limit: int):
        self.section = section
        self.words = words
        self.word_limit = word_limit
        self.chars = chars
        self.char_limit = char_limit
        super().__init__(
            f"{section} is {words} words / {chars} characters "
            f"(limit {word_limit} words / {char_limit} characters). "
            f"Keep this section short so the cached brain stays under {BUDGET_MAX_TOKENS} tokens "
            f"and leaves room for live memory."
        )


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
                f"Shorten behaviour/business instructions (recommended "
                f"{RECOMMENDED_BEHAVIOUR_WORDS}+{RECOMMENDED_BUSINESS_WORDS} words) "
                f"or raise the budget slider (max {BUDGET_MAX_TOKENS} tokens)."
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


def sanitize_agent_brief(text: str) -> str:
    if not text:
        return ""
    return _strip_legacy_tags(text.strip()[:MAX_AGENT_BRIEF_CHARS])


def validate_user_section(section: str, text: str, *, word_limit: int, char_limit: int) -> None:
    raw = (text or "").strip()
    words = count_words(raw)
    chars = len(raw)
    if words > word_limit or chars > char_limit:
        raise PromptSectionTooLong(section, words, word_limit, chars, char_limit)


def fit_text_to_tokens(text: str, max_tokens: int) -> str:
    """Trim from the end by words until the estimate fits. Never used on live turns."""
    if max_tokens <= 0 or estimate_tokens(text) <= max_tokens:
        return text.strip()
    words = text.split()
    lo, hi = 0, len(words)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = " ".join(words[:mid]).strip()
        if estimate_tokens(candidate) <= max_tokens:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


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
