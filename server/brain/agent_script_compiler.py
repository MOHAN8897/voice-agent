"""
Agent script compiler — turn a short natural-language brief into a full calling script.

Sarvam-style agent creation: user describes the agent in plain language; GPT expands it
into a structured telecaller script that becomes the cached brain for the session.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from server.agent.brain_prompt_composer import (
    BUDGET_MAX_TOKENS,
    CACHE_MIN_TOKENS,
    estimate_tokens,
    sanitize_agent_brief,
    validate_brain_prompt_budget,
    validate_user_section,
    MAX_AGENT_BRIEF_CHARS,
    MAX_AGENT_BRIEF_WORDS,
)
from server.brain.sections import STATIC_OUTPUT_RULES
from server.config.env import get_settings
from server.prompts.agent_voice_rules import (
    AGENT_OPENING_REQUIREMENTS,
    AGENT_TANGLISH_LANGUAGE_RULE,
    AGENT_VOICE_BEHAVIOR_RULES,
)
from server.prompts.brain_prompt import SECTION_SAFETY, SECTION_TELUGU_VOICE
from server.prompts.voice_defaults import DEFAULT_RESPONSE_STYLE

COMPILER_VERSION = "agent_script_v2"

AGENT_SCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent_script": {
            "type": "string",
            "description": "Complete plain-text calling script with section headers",
        },
        "agent_name": {"type": "string"},
        "company_name": {"type": "string"},
        "role_summary": {"type": "string"},
        "key_facts": {"type": "array", "items": {"type": "string"}},
        "opening_line_te": {"type": "string"},
        "qualification_questions": {"type": "array", "items": {"type": "string"}},
        "guardrails": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["agent_script"],
    "additionalProperties": False,
}


@dataclass
class AgentScriptResult:
    agent_script: str
    agent_name: str = ""
    company_name: str = ""
    role_summary: str = ""
    key_facts: list[str] = field(default_factory=list)
    source_checksum: str = ""
    optimizer_model: str = "deterministic_v1"
    optimizer_version: str = COMPILER_VERSION
    optimized_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_token_estimate: int = 0
    optimized_token_estimate: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "optimized_business_prompt": self.agent_script,
            "agent_script": self.agent_script,
            "agent_name": self.agent_name,
            "company_name": self.company_name,
            "role_summary": self.role_summary,
            "preserved_facts": self.key_facts[:8],
            "preserved_rules": [],
            "deduplicated_items": [],
            "conflicts": [],
            "source_checksum": self.source_checksum,
            "optimizer_model": self.optimizer_model,
            "optimizer_version": self.optimizer_version,
            "optimized_at": self.optimized_at,
            "raw_token_estimate": self.raw_token_estimate,
            "optimized_token_estimate": self.optimized_token_estimate,
            "tokens_saved": 0,
        }


def brief_checksum(*, brief: str, language: str, style: str | None) -> str:
    payload = "\n---\n".join([brief.strip(), language.strip(), (style or DEFAULT_RESPONSE_STYLE).strip()])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _deterministic_script(brief: str) -> str:
    """Fallback when OpenAI is unavailable — still produces a usable script skeleton."""
    return (
        "--- AGENT IDENTITY ---\n"
        f"Follow this brief on every call:\n{brief.strip()}\n\n"
        "--- OPENING ---\n"
        "Namaste! Nenu [agent name], [company name] nundi matladutunnanu. Meeku ela help cheyagalanu?\n"
        "Greet the customer, say the business name, and introduce yourself by name on every call.\n\n"
        "--- VOICE STYLE ---\n"
        f"{AGENT_VOICE_BEHAVIOR_RULES}\n\n"
        "--- CONVERSATION FLOW ---\n"
        "Listen first. Keep every reply to 60–80 characters unless the caller asks for more detail.\n"
        "Ask one clarifying question at a time (budget, location, timeline, product type).\n"
        "Be persuasive until a firm no; then stop pushing. Mirror the customer's language mix.\n"
        "Remember facts they already gave — never ask for quantity, color, delivery, or budget twice.\n\n"
        "--- GUARDRAILS ---\n"
        "Never invent prices, availability, policies, or prior conversations.\n"
        "If unsure, say you will confirm and offer a callback.\n"
        "Politely end the call when the user says goodbye.\n\n"
        "--- CLOSING ---\n"
        "Summarize next step (site visit, callback, order confirm) in one sentence.\n"
        "Thank them and close naturally."
    )


async def _llm_generate_script(
    brief: str,
    *,
    language: str,
    budget_tokens: int,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.enable_openai:
        return None
    try:
        import asyncio

        from server.providers.base import LLMConfig
        from server.providers.openai_llm import OpenAILLMAdapter

        adapter = OpenAILLMAdapter()
        target_words = max(400, min(2000, int(budget_tokens * 0.4)))
        system = (
            "You write complete voice-agent calling scripts for Telugu phone assistants in India. "
            "Given a short user brief, output a single plain-text script the agent follows on every call. "
            "Include clear section headers:\n"
            "AGENT IDENTITY, OPENING, VOICE STYLE, CONVERSATION FLOW, OBJECTION HANDLING, GUARDRAILS, CLOSING.\n"
            "Rules:\n"
            f"- TOP PRIORITY — {AGENT_TANGLISH_LANGUAGE_RULE}\n"
            "- All example dialogue lines in the script must demonstrate natural Tanglish, not literary Telugu.\n"
            "- You MUST include every section through CLOSING — never stop mid-section.\n"
            "- Extract agent name, company, and role from the brief when provided.\n"
            f"- {AGENT_OPENING_REQUIREMENTS}\n"
            "- Telecaller / sales flows: qualify budget, location, timeline; offer one clear next step.\n"
            "- Plain text only — no markdown, no bullet symbols, no numbered lists.\n"
            "- NEVER invent prices, discounts, inventory, policies, or capabilities not in the brief.\n"
            "- Keep responses short for live voice (1-2 sentences per turn).\n"
            "- Every live reply should target 60–80 characters unless the caller explicitly asks for more detail.\n"
            "- All numbers (prices, quantities, phone numbers, dates, times) must be spoken in English only — use English digits or English number words, never Telugu number words or Telugu numerals.\n"
            f"- Target roughly {target_words} words for agent_script.\n\n"
            "MANDATORY — weave these voice-sales behaviors into VOICE STYLE and CONVERSATION FLOW "
            "(natural prose, not a raw checklist dump):\n"
            f"{AGENT_VOICE_BEHAVIOR_RULES}"
        )
        user = (
            f"Language: {language}\n\n"
            f"User brief:\n{brief}\n\n"
            "Write the complete calling script now."
        )

        async def _run():
            return await adapter.structured_completion(
                input_messages=[
                    {"role": "developer", "content": [{"type": "input_text", "text": system}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user}]},
                ],
                schema=AGENT_SCRIPT_SCHEMA,
                config=LLMConfig(
                    provider="openai",
                    model=settings.post_call_llm_model or settings.openai_model,
                ),
                schema_name="agent_calling_script",
                max_output_tokens=min(4000, budget_tokens),
            )

        payload = await asyncio.wait_for(_run(), timeout=25)
        if payload.get("agent_script"):
            return payload
    except Exception as exc:
        from server.utils.logger import logger

        logger.warning(f"[AGENT_SCRIPT] structured LLM failed: {str(exc)[:200]}")
        fallback = await _llm_generate_script_plain(brief, language=language, budget_tokens=budget_tokens)
        if fallback:
            return fallback
    return None


async def _llm_generate_script_plain(
    brief: str,
    *,
    language: str,
    budget_tokens: int,
) -> dict[str, Any] | None:
    """Plain-text completion fallback when JSON schema path fails."""
    settings = get_settings()
    if not settings.enable_openai:
        return None
    try:
        import asyncio

        from server.utils.http_clients import get_openai_client

        client = get_openai_client()
        model = settings.post_call_llm_model or settings.openai_model
        system = (
            "Write a complete Telugu telecaller calling script as plain text with section headers: "
            "AGENT IDENTITY, OPENING, VOICE STYLE, CONVERSATION FLOW, OBJECTION HANDLING, GUARDRAILS, CLOSING. "
            "Extract agent name and company from the brief. No markdown bullets. "
            f"{AGENT_OPENING_REQUIREMENTS} "
            "All numbers in example dialogue must be in English (digits or English words), never Telugu numerals. "
            f"TOP PRIORITY: {AGENT_TANGLISH_LANGUAGE_RULE} "
            "Weave these voice behaviors subtly into VOICE STYLE and CONVERSATION FLOW:\n"
            f"{AGENT_VOICE_BEHAVIOR_RULES}"
        )
        user = f"Language: {language}\n\nBrief:\n{brief}\n\nScript:"
        response = await asyncio.wait_for(
            client.responses.create(
                model=model,
                input=[
                    {"role": "developer", "content": [{"type": "input_text", "text": system}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user}]},
                ],
                max_output_tokens=min(4000, budget_tokens),
                store=False,
            ),
            timeout=25,
        )
        script = str(getattr(response, "output_text", None) or "").strip()
        if len(script) < 80:
            return None
        return {"agent_script": script}
    except Exception:
        return None


def _assemble_brain(*, script: str, language: str, style: str | None) -> str:
    style_val = (style or DEFAULT_RESPONSE_STYLE)[:100]
    return (
        f"{SECTION_SAFETY}\n\n"
        f"{SECTION_TELUGU_VOICE}\n\n"
        f"{script.strip()}\n\n"
        f"{STATIC_OUTPUT_RULES}\n\n"
        f"Language: {language}. Style: {style_val}."
    )


_SCRIPT_CACHE_PAD = (
    "\n\n--- CALLING SCRIPT REINFORCEMENT ---\n"
    "Live call rules: stay in character using the agent name and company from the script; "
    "keep every reply to 60–80 characters unless the caller explicitly asks for more detail; "
    "speak natural Tanglish (Telugu + everyday English) — never literary or pandit-style Telugu; "
    "be persuasive until a firm no, then stop; avoid filler openers like అవును/సరే at the start of every turn; "
    "ask one useful question per turn to move the sale forward; "
    "never re-ask facts the caller already gave (budget, quantity, delivery, color); "
    "speak every number, price, quantity, phone number, and time in English only (English digits or words, never Telugu numerals); "
    "use natural Telugu with conversational English (price, order, delivery, confirm); "
    "adapt tone to the caller; every reply must answer, handle an objection, or advance the sale; "
    "stay on script and business scope — politely redirect off-topic questions back to the product or service; "
    "never invent prices, discounts, or inventory.\n"
)


def _ensure_cache_floor(
    *,
    script: str,
    language: str,
    style: str | None,
) -> tuple[str, str]:
    """Pad script only if below OpenAI cache minimum (1024 tokens). Never truncate."""
    style_val = (style or DEFAULT_RESPONSE_STYLE)[:100]
    body = script.strip()
    compiled = _assemble_brain(script=body, language=language, style=style_val)
    if estimate_tokens(compiled) >= CACHE_MIN_TOKENS:
        return body, compiled

    padded = body
    for _ in range(8):
        padded = f"{padded}{_SCRIPT_CACHE_PAD}"
        compiled = _assemble_brain(script=padded, language=language, style=style_val)
        if estimate_tokens(compiled) >= CACHE_MIN_TOKENS:
            return padded, compiled
    return padded, compiled


async def compile_agent_from_brief(
    *,
    brief: str,
    language: str = "te-IN",
    style: str | None = None,
    budget_tokens: int = 3500,
    previous_compiled: str | None = None,
) -> tuple[str, AgentScriptResult, int, int, int]:
    """
    Expand a short agent brief into a full cached brain prompt.
    Returns (compiled_brain, result, raw_token_est, compiled_token_est, effective_budget_tokens).
    """
    raw = (brief or "").strip()
    validate_user_section(
        "Agent brief",
        raw,
        word_limit=MAX_AGENT_BRIEF_WORDS,
        char_limit=MAX_AGENT_BRIEF_CHARS,
    )
    cleaned = sanitize_agent_brief(raw)
    style_val = (style or DEFAULT_RESPONSE_STYLE)[:100]
    checksum = brief_checksum(brief=cleaned, language=language, style=style_val)
    raw_tokens = estimate_tokens(cleaned)

    llm_payload = await _llm_generate_script(cleaned, language=language, budget_tokens=budget_tokens)
    if llm_payload:
        script = str(llm_payload.get("agent_script", "")).strip()
        model = get_settings().post_call_llm_model or get_settings().openai_model
        agent_name = str(llm_payload.get("agent_name") or "").strip()
        company_name = str(llm_payload.get("company_name") or "").strip()
        role_summary = str(llm_payload.get("role_summary") or "").strip()
        key_facts = list(llm_payload.get("key_facts") or [])[:8]
    else:
        script = _deterministic_script(cleaned)
        model = "deterministic_v1"
        agent_name = ""
        company_name = ""
        role_summary = ""
        key_facts = []

    script, compiled = _ensure_cache_floor(
        script=script,
        language=language,
        style=style_val,
    )
    compiled_tokens = estimate_tokens(compiled)
    effective_budget = min(BUDGET_MAX_TOKENS, max(int(budget_tokens), compiled_tokens))
    validate_brain_prompt_budget(compiled, effective_budget)

    result = AgentScriptResult(
        agent_script=script,
        agent_name=agent_name,
        company_name=company_name,
        role_summary=role_summary,
        key_facts=key_facts,
        source_checksum=checksum,
        optimizer_model=model,
        raw_token_estimate=raw_tokens,
        optimized_token_estimate=estimate_tokens(script),
    )

    if previous_compiled and previous_compiled.strip() == compiled.strip():
        result.to_dict()  # ensure stable
        conflicts = [{
            "severity": "warning",
            "description": "Agent script unchanged — edit the brief before re-saving",
            "recommended_resolution": "Change company, agent name, or instructions in the brief",
        }]
        d = result.to_dict()
        d["conflicts"] = conflicts

    return compiled, result, raw_tokens, compiled_tokens, effective_budget
