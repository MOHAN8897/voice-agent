"""
Agent script compiler — turn a short natural-language brief into a full calling script.

Sarvam-style agent creation: user describes the agent in plain language; GPT expands it
into a structured telecaller script that becomes the cached brain for the session.
"""
from __future__ import annotations

import hashlib
import re
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
from server.prompts.conversation_policy import (
    LIVE_CALL_GUIDE_BODY,
    checklist_flow_detected,
    flow_section,
    infer_agent_role,
    role_section,
)
from server.brain.sections import STATIC_OUTPUT_RULES
from server.config.env import get_settings
from server.prompts.agent_voice_rules import (
    IDENTITY_SPEAK,
    call_end_policy_section,
    language_runtime_footer,
    normalize_compile_language,
    opening_line_for,
    script_writer_system,
    spoken_pack_for,
)
from server.prompts.brain_prompt import SECTION_SAFETY
from server.prompts.voice_defaults import style_for_language

COMPILER_VERSION = "agent_script_v13"

AGENT_SCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent_script": {
            "type": "string",
            "description": "Complete plain-text calling script with section headers",
        },
        "agent_name": {"type": "string"},
        "company_name": {"type": "string"},
        "role": {
            "type": "string",
            "description": "Primary role from the brief objective, not incidental nouns",
            "enum": [
                "sales",
                "support",
                "recruitment",
                "appointment",
                "education",
                "information",
                "lead_qualification",
                "follow_up",
                "other",
            ],
        },
        "role_summary": {"type": "string"},
        "key_facts": {"type": "array", "items": {"type": "string"}},
        "unknown_topics": {"type": "array", "items": {"type": "string"}},
        "opening_line_te": {"type": "string"},
        "may_sell": {"type": "boolean"},
        "guardrails": {"type": "array", "items": {"type": "string"}},
    },
    # OpenAI strict JSON Schema requires every declared property to be required.
    # Values may be empty, but omitted optional keys make the whole request fail.
    "required": [
        "agent_script",
        "agent_name",
        "company_name",
        "role",
        "role_summary",
        "key_facts",
        "unknown_topics",
        "opening_line_te",
        "may_sell",
        "guardrails",
    ],
    "additionalProperties": False,
}


@dataclass
class AgentScriptResult:
    agent_script: str
    agent_name: str = ""
    company_name: str = ""
    role_summary: str = ""
    key_facts: list[str] = field(default_factory=list)
    detected_role: str = "other"
    response_style: str = ""
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
            "detected_role": self.detected_role,
            "response_style": self.response_style,
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


def brief_checksum(*, brief: str, language: str, style: str | None, call_end_policy: dict[str, Any] | None = None) -> str:
    policy_key = ""
    if call_end_policy:
        reasons = ",".join(str(r) for r in (call_end_policy.get("allowedReasons") or []))
        policy_key = f"{reasons}|{str(call_end_policy.get('farewell') or '')[:240]}"
    payload = "\n---\n".join(
        [brief.strip(), language.strip(), style_for_language(style, language).strip(), policy_key]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_PLACEHOLDER_RE = re.compile(r"\[(?:agent name|company(?: name)?)\]", re.I)
_WORKISH_FIRST = frozenset({
    "a", "an", "the", "people", "customers", "users", "callers", "someone",
    "car", "cars", "cab", "cabs", "taxi", "booking", "bookings", "help",
    "support", "insurance", "loan", "loans", "sales", "orders", "delivery",
    "plant", "plants", "this", "that",
})
_COMPANY_HINT = re.compile(
    r"(shop|mart|realty|plants|pvt|ltd|limited|inc|corp|hospital|clinic|"
    r"hotel|bank|school|college|nursery|store|studio|farms|farm)",
    re.I,
)
_LIVE_CALL_GUIDE_TITLE = "LIVE CALL GUIDE"
_SECTION_NAMES = (
    "AGENT IDENTITY",
    "OPENING",
    "WORK SCOPE",
    "ROLE & OBJECTIVE",
    "LIVE CALL GUIDE",
    "VOICE STYLE",
    "CONVERSATION FLOW",
    "OBJECTION HANDLING",
    "GUARDRAILS",
    "CLOSING",
)
_SECTION_SPLIT = "|".join(re.escape(name) for name in _SECTION_NAMES)


def _clean_identity_value(value: str) -> str:
    text = _PLACEHOLDER_RE.sub("", value or "").strip(" .,:;-")
    text = re.sub(r"\s+", " ", text)
    if not text or text.lower() in {"none", "n/a", "na", "unknown"}:
        return ""
    return text[:60]


def extract_agent_name_from_brief(brief: str) -> str:
    name_value = r"([^\n.,;]{2,50}?)(?=\s+(?:for|where)\b|[.,;]|$)"
    patterns = (
        rf"agent\s+named\s+{name_value}",
        rf"agent\s*name\s*(?:(?:is)\b\s*|:\s*)?{name_value}",
        rf"named\s+{name_value}",
        rf"\bnenu\s+{name_value}",
    )
    for pat in patterns:
        match = re.search(pat, brief or "", re.I)
        if match:
            name = _clean_identity_value(match.group(1))
            if name:
                return name
    return ""


def extract_company_from_brief(brief: str) -> str:
    text = brief or ""
    match = re.search(r"company(?:\s*name)?\s*(?:is|:)\s*([^\n.]{2,50})", text, re.I)
    if match:
        return _clean_identity_value(match.group(1))
    match = re.search(r"(?:calling from|from)\s+([A-Z][A-Za-z0-9 &.]{1,40})", text)
    if match:
        candidate = _clean_identity_value(match.group(1))
        if candidate and candidate.split()[0].lower() not in _WORKISH_FIRST:
            return candidate
    match = re.search(r"(?:telecaller|agent|caller)\s+for\s+(.+?)(?:\.|,|;|$)", text, re.I)
    if match:
        candidate = re.split(r"\bagent\s+name\b", match.group(1), flags=re.I)[0]
        candidate = _clean_identity_value(candidate)
        if not candidate:
            return ""
        first = candidate.split()[0]
        if first.lower() in _WORKISH_FIRST:
            return ""
        if first[:1].isupper() or _COMPANY_HINT.search(candidate):
            return candidate
    return ""


def infer_agent_name(brief: str) -> str:
    named = extract_agent_name_from_brief(brief)
    if named:
        return named
    return "Priya"


def work_scope_from_brief(brief: str, company: str) -> str:
    text = " ".join((brief or "").split())
    text = re.sub(r"^ok\s+", "", text, flags=re.I)
    text = re.sub(
        r"create\s+an?\s+(?:\w+\s+){0,3}agent\s+(?:named\s+)?[A-Za-z][A-Za-z]{1,24}\s*(?:for\s+)?",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"create\s+an?\s+agent\s+(?:named\s+)?[A-Za-z][A-Za-z]{1,24}\s*", "", text, flags=re.I)
    text = re.sub(
        r"agent\s+named\s+[^\n.,;]{2,50}?(?=\s+(?:for|where)\b|[.,;]|$)[.,;]?\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"agent\s*name\s*(?:(?:is)\b\s*|:\s*)?[^\n.,;]{2,50}?"
        r"(?=\s+(?:for|where)\b|[.,;]|$)[.,;]?\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"where\s+(?:he|she|they)\s+is\s+(?:an?\s+)?", "", text, flags=re.I)
    text = re.sub(r"company(?:\s*name)?\s*(?:is|:)?\s*[^\n.]{2,50}", "", text, flags=re.I)
    text = re.sub(r"never invent[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"do not sell[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"don'?t sell[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"must not sell[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"do not upsell[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"don'?t upsell[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"do not restart[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"don'?t restart[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"salary is not in this brief[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"never invent availability[^.]*\.?", "", text, flags=re.I)
    text = re.sub(r"never invent (?:discounts?|completed actions?)[^.]*\.?", "", text, flags=re.I)
    text = re.sub(
        r"no (?:email|calendar|messaging|ticketing|refund|booking|scheduling|payment|"
        r"crm|account-change|hiring-system|contact-list|enrollment)(?:[^.]*)"
        r"(?:tools?|systems?|access|capabilit(?:y|ies)|connected)[^.]*\.?",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\bsales pitch\b", "", text, flags=re.I)
    if company:
        text = re.sub(re.escape(company), "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .,:;-")
    if not text:
        text = " ".join((brief or "").split())
    if len(text) > 240:
        text = text[:237].rsplit(" ", 1)[0] + "..."
    return text


def build_opening_line(
    *,
    agent_name: str,
    company_name: str,
    work_scope: str,
    language: str = "te-IN",
) -> str:
    return opening_line_for(
        language,
        agent_name=agent_name,
        company_name=company_name,
        work_scope=work_scope,
    )


def resolve_script_identity(
    brief: str,
    *,
    llm_name: str = "",
    llm_company: str = "",
    language: str = "te-IN",
) -> tuple[str, str, str, str]:
    """Return (agent_name, company_name, work_scope, opening_line). Never invent a company."""
    brief_name = extract_agent_name_from_brief(brief)
    brief_company = extract_company_from_brief(brief)
    name = _clean_identity_value(brief_name or llm_name) or infer_agent_name(brief)
    if brief_company:
        company = brief_company
    else:
        guessed = _clean_identity_value(llm_company)
        company = guessed if guessed and guessed.lower() in (brief or "").lower() else ""
    work = work_scope_from_brief(brief, company)
    opening = build_opening_line(
        agent_name=name,
        company_name=company,
        work_scope=work,
        language=language,
    )
    return name, company, work, opening


def _strip_script_section(script: str, title: str) -> str:
    header = re.escape(title)
    pattern = re.compile(
        rf"(?:^|\n)(?:---\s*)?{header}(?:\s*---)?[ \t]*\n"
        rf"(.*?)(?=(?:\n(?:---\s*)?(?:{_SECTION_SPLIT})(?:\s*---)?[ \t]*\n)|\Z)",
        re.S | re.I,
    )
    return pattern.sub("\n", script, count=1).strip()


def _sanitize_conversation_flow(script: str, role: str = "other") -> str:
    header = "CONVERSATION FLOW"
    pattern = re.compile(
        rf"(?:^|\n)(?:---\s*)?{re.escape(header)}(?:\s*---)?[ \t]*\n"
        rf"(.*?)(?=(?:\n(?:---\s*)?(?:{_SECTION_SPLIT})(?:\s*---)?[ \t]*\n)|\Z)",
        re.S | re.I,
    )
    match = pattern.search(script or "")
    if not match:
        return script
    if not checklist_flow_detected(match.group(1) or ""):
        return script
    return pattern.sub("\n" + flow_section(role), script, count=1).strip()


def ensure_script_identity_and_scope(
    script: str,
    *,
    agent_name: str,
    company_name: str,
    work_scope: str,
    opening_line: str,
    language: str = "te-IN",
    role: str = "other",
) -> str:
    body = _PLACEHOLDER_RE.sub("", script or "").strip()
    for title in ("AGENT IDENTITY", "OPENING", "WORK SCOPE", "ROLE & OBJECTIVE", "LIVE CALL GUIDE"):
        body = _strip_script_section(body, title)
    body = _sanitize_conversation_flow(body, role)
    lang = normalize_compile_language(language)
    handle = (
        f", calling from {company_name}."
        if company_name
        else f". You handle: {work_scope.rstrip(' .')}."
    )
    identity = f"You are {agent_name}{handle} {IDENTITY_SPEAK[lang]}"
    opening = (
        f"{opening_line}\n"
        "Say this introduction (or a close natural variation) as the first turn when the call connects."
    )
    scope = (
        f"You only do this work on the call:\n{work_scope}\n"
        "Stay inside this scope. If the caller asks about something else, give one brief human boundary. "
        "Do not repeat the scope, catalog facts, price, hours, or issue summary unless the caller asks."
    )
    return (
        f"--- AGENT IDENTITY ---\n{identity}\n\n"
        f"--- OPENING ---\n{opening}\n\n"
        f"--- WORK SCOPE ---\n{scope}\n\n"
        f"{role_section(role)}\n\n"
        f"--- LIVE CALL GUIDE ---\n{LIVE_CALL_GUIDE_BODY}\n\n"
        f"{body}".strip()
    )


def _deterministic_script(
    brief: str,
    *,
    agent_name: str,
    company_name: str,
    work_scope: str,
    opening_line: str,
    language: str = "te-IN",
    role: str = "other",
) -> str:
    """Fallback when OpenAI is unavailable — still produces a usable script skeleton."""
    skeleton = (
        "--- VOICE STYLE ---\n"
        "Sound like a real person who works for this business. "
        "Keep replies to 1-2 spoken sentences. A question must earn its place.\n\n"
        f"{flow_section(role)}\n"
        "--- OBJECTION HANDLING ---\n"
        "Price, timing, already decided, already know that, will think about it: "
        "acknowledge the actual concern in one sentence. Do not resume a generic pitch.\n\n"
        "--- GUARDRAILS ---\n"
        "Never invent prices, availability, policies, salaries, or prior conversations.\n"
        "Never claim a message, ticket, booking, or other action happened unless an available tool performed it.\n"
        "If unsure, say you will confirm and offer a real next step.\n"
        "Politely end the call when the user says goodbye or don't-call.\n\n"
        "--- CLOSING ---\n"
        "One next step that fits this role, in one sentence. Thank them and close naturally.\n"
        "Firm no: short farewell and hang up.\n\n"
        f"Source facts and duties:\n{work_scope}"
    )
    return ensure_script_identity_and_scope(
        skeleton,
        agent_name=agent_name,
        company_name=company_name,
        work_scope=work_scope,
        opening_line=opening_line,
        language=language,
        role=role,
    )


async def _llm_generate_script(
    brief: str,
    *,
    language: str,
    budget_tokens: int,
) -> dict[str, Any] | None:
    from server.services.dev_runtime import openai_enabled

    if not openai_enabled():
        return None
    try:
        import asyncio

        from server.providers.base import LLMConfig
        from server.providers.openai_llm import OpenAILLMAdapter

        adapter = OpenAILLMAdapter()
        settings = get_settings()
        system = script_writer_system(language=language, budget_tokens=budget_tokens)
        user = (
            f"Language: {language}\n\n"
            f"User brief:\n{brief}\n\n"
            "Infer the role from the brief. Write a conversational policy, not a question tree."
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
                max_output_tokens=min(1800, budget_tokens),
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
    from server.services.dev_runtime import openai_enabled

    if not openai_enabled():
        return None
    try:
        import asyncio

        from server.utils.http_clients import get_openai_client

        client = get_openai_client()
        settings = get_settings()
        model = settings.post_call_llm_model or settings.openai_model
        system = script_writer_system(language=language, budget_tokens=budget_tokens)
        user = f"Language: {language}\n\nBrief:\n{brief}\n\nScript:"
        response = await asyncio.wait_for(
            client.responses.create(
                model=model,
                input=[
                    {"role": "developer", "content": [{"type": "input_text", "text": system}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user}]},
                ],
            max_output_tokens=min(1800, budget_tokens),
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


def _assemble_brain(
    *,
    script: str,
    language: str,
    style: str | None,
    extra_pad: str = "",
    call_end_policy: dict[str, Any] | None = None,
) -> str:
    lang = normalize_compile_language(language)
    style_val = style_for_language(style, lang)
    body = (
        f"{SECTION_SAFETY}\n\n"
        f"{spoken_pack_for(lang)}\n\n"
        f"--- CALLING SCRIPT ---\n{script.strip()}\n\n"
        f"{call_end_policy_section(lang, call_end_policy)}\n\n"
        f"{STATIC_OUTPUT_RULES}\n\n"
        f"{language_runtime_footer(lang, style_val)}"
    )
    if extra_pad:
        return f"{body}\n\n{extra_pad.strip()}"
    return body


def _ensure_cache_floor(
    *,
    script: str,
    language: str,
    style: str | None,
    call_end_policy: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Pad brain pack/static rules if below OpenAI cache minimum. Never pad agentScript."""
    lang = normalize_compile_language(language)
    style_val = style_for_language(style, lang)
    body = script.strip()
    compiled = _assemble_brain(
        script=body,
        language=lang,
        style=style_val,
        call_end_policy=call_end_policy,
    )
    if estimate_tokens(compiled) >= CACHE_MIN_TOKENS:
        return body, compiled

    pad_block = f"{STATIC_OUTPUT_RULES}\n\n{spoken_pack_for(lang)}"
    extra = ""
    for _ in range(8):
        extra = f"{extra}\n\n{pad_block}".strip()
        compiled = _assemble_brain(
            script=body,
            language=lang,
            style=style_val,
            extra_pad=extra,
            call_end_policy=call_end_policy,
        )
        if estimate_tokens(compiled) >= CACHE_MIN_TOKENS:
            return body, compiled
    return body, compiled


def reassemble_brain_from_script(
    *,
    script: str,
    language: str = "te-IN",
    style: str | None = None,
    call_end_policy: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Rebuild cached brain from an existing script (no GPT). Used when call-end policy changes."""
    return _ensure_cache_floor(
        script=script,
        language=language,
        style=style,
        call_end_policy=call_end_policy,
    )


async def compile_agent_from_brief(
    *,
    brief: str,
    language: str = "te-IN",
    style: str | None = None,
    budget_tokens: int = 3500,
    previous_compiled: str | None = None,
    call_end_policy: dict[str, Any] | None = None,
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
    lang = normalize_compile_language(language)
    style_val = style_for_language(style, lang)
    from server.call.call_end_policy import normalize_call_end_policy

    call_end_policy = normalize_call_end_policy(call_end_policy, language=lang)
    checksum = brief_checksum(
        brief=cleaned,
        language=lang,
        style=style_val,
        call_end_policy=call_end_policy,
    )
    raw_tokens = estimate_tokens(cleaned)

    llm_payload = await _llm_generate_script(cleaned, language=lang, budget_tokens=budget_tokens)
    if llm_payload:
        script = str(llm_payload.get("agent_script", "")).strip()
        model = get_settings().post_call_llm_model or get_settings().openai_model
        llm_name = str(llm_payload.get("agent_name") or "").strip()
        llm_company = str(llm_payload.get("company_name") or "").strip()
        role_summary = str(llm_payload.get("role_summary") or "").strip()
        key_facts = list(llm_payload.get("key_facts") or [])[:8]
        llm_role = str(llm_payload.get("role") or "").strip()
    else:
        script = ""
        model = "deterministic_v1"
        llm_name = ""
        llm_company = ""
        role_summary = ""
        key_facts = []
        llm_role = ""

    agent_name, company_name, work_scope, opening_line = resolve_script_identity(
        cleaned,
        llm_name=llm_name,
        llm_company=llm_company,
        language=lang,
    )
    if not role_summary:
        role_summary = work_scope
    role = infer_agent_role(cleaned, llm_role=llm_role)
    if not script:
        script = _deterministic_script(
            cleaned,
            agent_name=agent_name,
            company_name=company_name,
            work_scope=work_scope,
            opening_line=opening_line,
            language=lang,
            role=role,
        )
    else:
        script = ensure_script_identity_and_scope(
            script,
            agent_name=agent_name,
            company_name=company_name,
            work_scope=work_scope,
            opening_line=opening_line,
            language=lang,
            role=role,
        )

    script, compiled = _ensure_cache_floor(
        script=script,
        language=lang,
        style=style_val,
        call_end_policy=call_end_policy,
    )
    compiled_tokens = estimate_tokens(compiled)
    if compiled_tokens > BUDGET_MAX_TOKENS:
        # Generated scripts can exceed their requested target. Agent creation
        # must remain deterministic instead of returning 400 and leaving the
        # caller on a stale previously-published brain.
        script = _deterministic_script(
            cleaned,
            agent_name=agent_name,
            company_name=company_name,
            work_scope=work_scope,
            opening_line=opening_line,
            language=lang,
            role=role,
        )
        script, compiled = _ensure_cache_floor(
            script=script,
            language=lang,
            style=style_val,
            call_end_policy=call_end_policy,
        )
        compiled_tokens = estimate_tokens(compiled)
        model = "deterministic_budget_fallback_v1"
    effective_budget = min(BUDGET_MAX_TOKENS, max(int(budget_tokens), compiled_tokens))
    validate_brain_prompt_budget(compiled, effective_budget)

    result = AgentScriptResult(
        agent_script=script,
        agent_name=agent_name,
        company_name=company_name,
        role_summary=role_summary,
        key_facts=key_facts,
        detected_role=role,
        response_style=style_val,
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
