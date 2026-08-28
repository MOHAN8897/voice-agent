"""
Session brain compiler — one-time merge of dev behaviour + client business into cache-stable brain.
Normative: prd/12-brain-business-memory-spec.md §3, memory implemenation.md §2–3.
"""
from __future__ import annotations

import hashlib

from server.agent.brain_prompt_composer import (
    sanitize_behaviour,
    sanitize_business,
    validate_brain_prompt_budget,
    estimate_tokens,
)
from server.brain.business_prompt_optimizer import OptimizerResult, optimize_session_dual_prompt
from server.brain.sections import STATIC_OUTPUT_RULES
from server.prompts.brain_prompt import SECTION_SAFETY, SECTION_TELUGU_VOICE
from server.prompts.voice_defaults import (
    DEFAULT_BEHAVIOUR_INSTRUCTIONS,
    DEFAULT_BUSINESS_INSTRUCTIONS,
    DEFAULT_RESPONSE_STYLE,
)


def dual_source_checksum(
    *,
    behaviour: str,
    business: str,
    language: str,
    style: str | None,
) -> str:
    payload = "\n---\n".join(
        [
            behaviour.strip(),
            business.strip(),
            language.strip(),
            (style or DEFAULT_RESPONSE_STYLE).strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assemble_raw_dual_prompt(
    *,
    behaviour: str,
    business: str,
    language: str = "te-IN",
    style: str | None = None,
) -> str:
    """Deterministic raw assembly — never sent to cache; preserved for audit."""
    b = sanitize_behaviour(behaviour) or DEFAULT_BEHAVIOUR_INSTRUCTIONS
    z = sanitize_business(business) or DEFAULT_BUSINESS_INSTRUCTIONS
    style_line = style or DEFAULT_RESPONSE_STYLE
    return (
        f"--- PLATFORM SAFETY ---\n{SECTION_SAFETY}\n\n"
        f"--- PLATFORM VOICE ---\n{SECTION_TELUGU_VOICE}\n\n"
        f"--- BEHAVIOUR (dev/platform) ---\n{b}\n\n"
        f"--- BUSINESS (customer) ---\n{z}\n\n"
        f"Language: {language}. Style: {style_line}."
    )


async def compile_session_brain(
    *,
    behaviour: str,
    business: str,
    language: str = "te-IN",
    style: str | None = None,
    budget_tokens: int = 2500,
    previous_compiled: str | None = None,
) -> tuple[str, OptimizerResult, int, int]:
    """
    Compile behaviour + business into one concise cached brain prompt.
    Returns (compiled_text, optimizer_report, raw_token_est, compiled_token_est).
    """
    b = sanitize_behaviour(behaviour or "")
    z = sanitize_business(business or "")
    style_val = (style or DEFAULT_RESPONSE_STYLE)[:100]
    raw_prompt = assemble_raw_dual_prompt(
        behaviour=b,
        business=z,
        language=language,
        style=style_val,
    )
    checksum = dual_source_checksum(
        behaviour=b,
        business=z,
        language=language,
        style=style_val,
    )
    raw_tokens = estimate_tokens(raw_prompt)

    opt = await optimize_session_dual_prompt(
        behaviour=b or DEFAULT_BEHAVIOUR_INSTRUCTIONS,
        business=z or DEFAULT_BUSINESS_INSTRUCTIONS,
        raw_assembled=raw_prompt,
        source_checksum=checksum,
        budget_tokens=budget_tokens,
        previous_optimized=previous_compiled,
    )

    compiled = (
        f"{SECTION_SAFETY}\n\n"
        f"{SECTION_TELUGU_VOICE}\n\n"
        f"{opt.optimized_business_prompt.strip()}\n\n"
        f"{STATIC_OUTPUT_RULES}\n\n"
        f"Language: {language}. Style: {style_val}."
    )
    validate_brain_prompt_budget(compiled, budget_tokens)
    compiled_tokens = estimate_tokens(compiled)
    return compiled, opt, raw_tokens, compiled_tokens
