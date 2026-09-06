"""
Session brain compiler — one-time merge of dev behaviour + client business into cache-stable brain.
Normative: prd/12-brain-business-memory-spec.md §3, memory implemenation.md §2–3.
"""
from __future__ import annotations

import hashlib

from server.agent.brain_prompt_composer import (
    BUDGET_MAX_TOKENS,
    sanitize_behaviour,
    sanitize_business,
    validate_brain_prompt_budget,
    validate_user_section,
    fit_text_to_tokens,
    estimate_tokens,
    MAX_BEHAVIOUR_CHARS,
    MAX_BEHAVIOUR_WORDS,
    MAX_BUSINESS_CHARS,
    MAX_BUSINESS_WORDS,
)
from server.brain.business_prompt_optimizer import OptimizerResult, optimize_session_dual_prompt
from server.brain.sections import STATIC_OUTPUT_RULES
from server.prompts.agent_voice_rules import (
    call_end_policy_section,
    language_runtime_footer,
    spoken_pack_for,
)
from server.prompts.brain_prompt import SECTION_SAFETY
from server.prompts.voice_defaults import (
    CACHE_FLOOR_PAD,
    DEFAULT_BEHAVIOUR_INSTRUCTIONS,
    DEFAULT_BUSINESS_INSTRUCTIONS,
    style_for_language,
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
            style_for_language(style, language).strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _assemble_session_brain(
    *,
    language: str,
    style_val: str,
    body: str,
    call_end_policy: dict | None = None,
) -> str:
    """Every session-brain variant keeps the default hangup section."""
    return (
        f"{SECTION_SAFETY}\n\n"
        f"{spoken_pack_for(language)}\n\n"
        f"{body.strip()}\n\n"
        f"{call_end_policy_section(language, call_end_policy)}\n\n"
        f"{STATIC_OUTPUT_RULES}\n\n"
        f"{language_runtime_footer(language, style_val)}"
    )


def assemble_raw_dual_prompt(
    *,
    behaviour: str,
    business: str,
    language: str = "te-IN",
    style: str | None = None,
    call_end_policy: dict | None = None,
) -> str:
    """Deterministic raw assembly — never sent to cache; preserved for audit."""
    b = sanitize_behaviour(behaviour) or DEFAULT_BEHAVIOUR_INSTRUCTIONS
    z = sanitize_business(business) or DEFAULT_BUSINESS_INSTRUCTIONS
    style_line = style_for_language(style, language)
    return (
        f"--- PLATFORM SAFETY ---\n{SECTION_SAFETY}\n\n"
        f"--- PLATFORM VOICE ---\n{spoken_pack_for(language)}\n\n"
        f"--- BEHAVIOUR (dev/platform) ---\n{b}\n\n"
        f"--- BUSINESS (customer) ---\n{z}\n\n"
        f"{call_end_policy_section(language, call_end_policy)}\n\n"
        f"{language_runtime_footer(language, style_line)}"
    )


async def compile_session_brain(
    *,
    behaviour: str,
    business: str,
    language: str = "te-IN",
    style: str | None = None,
    budget_tokens: int = 2500,
    previous_compiled: str | None = None,
    call_end_policy: dict | None = None,
) -> tuple[str, OptimizerResult, int, int]:
    """
    Compile behaviour + business into one concise cached brain prompt.
    Returns (compiled_text, optimizer_report, raw_token_est, compiled_token_est).
    """
    raw_b = (behaviour or "").strip()
    raw_z = (business or "").strip()
    validate_user_section(
        "Behaviour instructions",
        raw_b,
        word_limit=MAX_BEHAVIOUR_WORDS,
        char_limit=MAX_BEHAVIOUR_CHARS,
    )
    validate_user_section(
        "Business instructions",
        raw_z,
        word_limit=MAX_BUSINESS_WORDS,
        char_limit=MAX_BUSINESS_CHARS,
    )
    b = sanitize_behaviour(raw_b)
    z = sanitize_business(raw_z)
    style_val = style_for_language(style, language)
    raw_prompt = assemble_raw_dual_prompt(
        behaviour=b,
        business=z,
        language=language,
        style=style_val,
        call_end_policy=call_end_policy,
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

    compiled = _assemble_session_brain(
        language=language,
        style_val=style_val,
        body=opt.optimized_business_prompt,
        call_end_policy=call_end_policy,
    )
    static_shell = _assemble_session_brain(
        language=language,
        style_val=style_val,
        body="",
        call_end_policy=call_end_policy,
    )
    # Static safety/voice policy is mandatory and can exceed an old saved
    # slider value. Preserve a small user-instruction allowance instead of
    # failing compilation solely because the platform shell grew.
    effective_budget = min(
        BUDGET_MAX_TOKENS,
        max(int(budget_tokens), estimate_tokens(static_shell) + 180),
    )
    user_budget = max(180, effective_budget - estimate_tokens(static_shell) - 40)
    fitted = fit_text_to_tokens(opt.optimized_business_prompt.strip(), user_budget)
    if fitted != opt.optimized_business_prompt.strip():
        opt.optimized_business_prompt = fitted
        compiled = _assemble_session_brain(
            language=language,
            style_val=style_val,
            body=fitted,
            call_end_policy=call_end_policy,
        )
    validate_brain_prompt_budget(compiled, effective_budget)
    compiled_tokens = estimate_tokens(compiled)
    if compiled_tokens < 1024:
        # OpenAI explicit cache requires ≥1024 tokens in the breakpoint prefix.
        filler = (
            f"{opt.optimized_business_prompt.strip()}\n\n"
            f"{CACHE_FLOOR_PAD.strip()}\n{CACHE_FLOOR_PAD.strip()}"
        )
        filler = fit_text_to_tokens(filler, user_budget)
        compiled = _assemble_session_brain(
            language=language,
            style_val=style_val,
            body=filler,
            call_end_policy=call_end_policy,
        )
        validate_brain_prompt_budget(compiled, effective_budget)
        compiled_tokens = estimate_tokens(compiled)
    return compiled, opt, raw_tokens, compiled_tokens
