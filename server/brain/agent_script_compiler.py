"""
Agent script compiler — turn a short natural-language brief into a cached brain.

Default path (v16): extract agent name + company from the brief and emit a minimal
BUSINESS KNOWLEDGE script only. Platform voice, safety, hangup, and output rules are
assembled separately in ``_assemble_brain``.

Legacy path (``use_llm=True``): full sectional LLM script generation (disabled by default).
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
    flow_section,
    infer_agent_role,
    role_section,
)
from server.brain.sections import STATIC_OUTPUT_RULES
from server.config.env import get_settings
from server.realtime.models import http_openai_model
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

COMPILER_VERSION = "agent_script_v16"

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
_PLACEHOLDER_BAD = re.compile(
    r"\[(?:agent name|company(?: name)?|name|todo|tbd|insert|placeholder)[^\]]*\]"
    r"|\{\{[^{}]+\}\}"
    r"|_{3,}"
    r"|\*{3,}"
    r"|\bTODO\b|\bTBD\b|\bXXX\b",
    re.I,
)
_STEP_TREE_LINE = re.compile(
    r"(?:^|\n)\s*(?:step|question)\s*[1-9]\s*[:.)]",
    re.I,
)
# Stricter than checklist_flow_detected — avoid false hits on "one useful question at a time".
_LEFTOVER_TREE = re.compile(
    r"(?:^|\n)\s*(?:step|question)\s*[1-9]\s*[:.)]"
    r"|first ask .{0,40}then (?:ask|qualify)"
    r"|collect all of the following"
    r"|interrogation checklist"
    r"|(?:ask|qualify).{0,80}budget.{0,60}location.{0,60}timeline",
    re.I | re.S,
)
_MONEY_AMOUNT = re.compile(
    r"(?:₹|rs\.?\s*|inr\s*|rupees?\s*)[\d,]+(?:\s*(?:lakh|lakhs|crore|crores))?"
    r"|[\d,]+\s*(?:lakh|lakhs|crore|crores)\b",
    re.I,
)
_BAD_IDENTITY = frozenset({"", "agent", "unknown", "none", "n/a", "na", "[agent name]"})
_WORKISH_FIRST = frozenset({
    "a", "an", "the", "people", "customers", "users", "callers", "someone",
    "car", "cars", "cab", "cabs", "taxi", "booking", "bookings", "help",
    "support", "insurance", "loan", "loans", "sales", "orders", "delivery",
    "plant", "plants", "this", "that",
})
_COMPANY_HINT = re.compile(
    r"(shop|mart|realty|estates?|plants|pvt|ltd|limited|inc|corp|hospital|clinic|"
    r"dental|hotel|bank|school|college|academy|nursery|store|studio|farms|farm|"
    r"motors?|crm|saas|software)",
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
    # Non-canonical writer sprawl — stripped on bind so they cannot survive.
    "DISCOVERY RULES",
    "RECOMMENDATION RULES",
    "DISCOVERY",
    "RECOMMENDATION",
)
_SECTION_SPLIT = "|".join(re.escape(name) for name in _SECTION_NAMES)
_SPRAWL_HEADERS = (
    "DISCOVERY RULES",
    "RECOMMENDATION RULES",
    "DISCOVERY",
    "RECOMMENDATION",
)


def _clean_identity_value(value: str) -> str:
    text = _PLACEHOLDER_RE.sub("", value or "").strip(" .,:;-")
    text = re.sub(r"\s+", " ", text)
    if not text or text.lower() in {"none", "n/a", "na", "unknown"}:
        return ""
    return text[:60]


def extract_agent_name_from_brief(brief: str) -> str:
    """Extract agent name; stop before from/for/where. Supports multi-word + Unicode."""
    # Allow letters from any script (Telugu etc.), not ASCII-only.
    name_value = (
        r"([^\n.,;]+?)"
        r"(?=\s+(?:from|for|where)\b|[.,;]|$)"
    )
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
            if not name:
                continue
            # Guard against swallowing a whole clause as a "name".
            if len(name.split()) > 4 or len(name) > 40:
                continue
            return name
    return ""


def extract_company_from_brief(brief: str) -> str:
    text = brief or ""
    match = re.search(r"company(?:\s*name)?\s*(?:is|:)\s*([^\n.]{2,50})", text, re.I)
    if match:
        return _clean_identity_value(match.group(1))

    def _accept_company(candidate: str) -> str:
        candidate = _clean_identity_value(candidate)
        if not candidate:
            return ""
        # Reject pickup/location debris mistaken for a brand.
        if re.search(
            r"\b(hitec|gachibowli|ameerpet|kukatpally|pickup|drop[- ]?off|near|area)\b",
            candidate,
            re.I,
        ):
            return ""
        first = candidate.split()[0]
        if (
            first.lower() not in _WORKISH_FIRST
            and not first[:1].isdigit()
            and (first[:1].isupper() or _COMPANY_HINT.search(candidate))
        ):
            return candidate
        return ""

    # Prefer "named X for Company" — more specific than a bare "from".
    match = re.search(
        r"(?:agent\s+)?named\s+[^\n.,;]{1,40}?\s+for\s+([^\n.,;]{2,60}?)(?=\s*[.,;]|$)",
        text,
        re.I,
    )
    if match:
        candidate = match.group(1)
        candidate = re.split(
            r"\b(?:car service|service center|service centre|that |who |which |where )\b",
            candidate,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" .,:;-")
        # "Horizon Learning Institute in Hyderabad" → company without city clause
        candidate = re.split(
            r"\s+in\s+(?:Hyderabad|Bengaluru|Bangalore|Chennai|Mumbai|Delhi|Pune)\b",
            candidate,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" .,:;-")
        accepted = _accept_company(candidate)
        if accepted:
            return accepted

    # "Agent name Priya from Acme Realty." / "calling from Acme Realty"
    # Do NOT match bare "pickup from …" / "workshop from …".
    match = re.search(
        r"(?:(?:agent\s*(?:name|named)\s*(?:(?:is)\b\s*|:\s*)?[^\n.,;]+?\s+)|(?:calling\s+))"
        r"from\s+([^\n.,;]{2,50}?)(?=\s*[.,;]|$)",
        text,
        re.I,
    )
    if match:
        accepted = _accept_company(match.group(1))
        if accepted:
            return accepted

    match = re.search(r"(?:telecaller|agent|caller)\s+for\s+(.+?)(?:\.|,|;|$)", text, re.I)
    if match:
        candidate = re.split(r"\bagent\s+name\b", match.group(1), flags=re.I)[0]
        accepted = _accept_company(candidate)
        if accepted:
            return accepted
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
    # After stripping company, clean leftover "for in Hyderabad" / "for ." debris.
    text = re.sub(r"\bfor\s+(?=in\b)", "", text, flags=re.I)
    text = re.sub(r"\bfor\s+(?=[.,;]|$)", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .,:;-")
    if not text:
        text = " ".join((brief or "").split())
    # Keep operational facts (fees/batches) — a 240-char chop was dropping prices mid-sentence.
    max_scope = 360
    if len(text) > max_scope:
        cut = text[: max_scope - 3].rsplit(" ", 1)[0]
        # If truncation removed a money amount present in the full scope, append a compact fee line.
        money_full = _MONEY_AMOUNT.findall(text)
        money_cut = _MONEY_AMOUNT.findall(cut)
        if money_full and len(money_cut) < len(money_full):
            missing = [m for m in money_full if m not in money_cut][:3]
            fee_tail = " Fees: " + "; ".join(missing) + "."
            room = max_scope - len(cut) - len(fee_tail)
            if room < 0:
                cut = cut[: max(40, max_scope - len(fee_tail) - 3)].rsplit(" ", 1)[0]
            cut = cut.rstrip(" .,:;-") + fee_tail
        text = cut.rstrip(" .,:;-") + ("..." if not cut.endswith(".") else "")
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
    """Keep soft ask-if-unknown ladders; replace only hard Question/Step trees.

    Platform FLOW always provides natural progression policy. Writer soft fields
    are preserved when they are not numbered trees.
    """
    from server.prompts.conversation_policy import checklist_flow_detected

    header = "CONVERSATION FLOW"
    pattern = re.compile(
        rf"(?:^|\n)(?:---\s*)?{re.escape(header)}(?:\s*---)?[ \t]*\n"
        rf"(.*?)(?=(?:\n(?:---\s*)?(?:{_SECTION_SPLIT})(?:\s*---)?[ \t]*\n)|\Z)",
        re.S | re.I,
    )
    match = pattern.search(script or "")
    writer_body = (match.group(1) if match else "").strip()
    soft_fields = ""
    keep_soft = role in {
        "sales",
        "lead_qualification",
        "appointment",
        "education",
        "support",
    }
    if writer_body and keep_soft and not checklist_flow_detected(writer_body):
        soft = re.sub(
            r"(?im)^(this is a (?:policy|human-call policy).*$|natural sales progression.*$|"
            r"appointment flow:.*$|education flow:.*$|service / support flow:.*$|"
            r"role on this call:.*$|lead conversion:.*$)",
            "",
            writer_body,
        ).strip()
        if soft and len(soft) > 40:
            soft_fields = soft[:1200]
    platform = flow_section(role, brief_fields=soft_fields)
    if match:
        return pattern.sub("\n" + platform, script, count=1).strip()
    body = (script or "").strip()
    if not body:
        return platform
    return f"{body}\n\n{platform}"


def _money_digit_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for match in _MONEY_AMOUNT.finditer(text or ""):
        digits = re.sub(r"[^\d]", "", match.group(0))
        if digits:
            keys.add(digits.lstrip("0") or "0")
    return keys


def validate_agent_script(
    script: str,
    *,
    brief: str,
    agent_name: str,
) -> list[str]:
    """
    Post-sanitize checks before save. FLOW is always platform-replaced; this catches
    leftover Step/Q trees in other sections, placeholders, empty identity, invented prices.
    """
    reasons: list[str] = []
    name = (agent_name or "").strip().lower()
    if name in _BAD_IDENTITY:
        reasons.append("empty or placeholder agent identity")

    body = script or ""
    if _PLACEHOLDER_BAD.search(body):
        reasons.append("placeholder tokens remain in script")

    non_flow = _strip_script_section(body, "CONVERSATION FLOW")
    if _STEP_TREE_LINE.search(non_flow) or _LEFTOVER_TREE.search(non_flow):
        reasons.append("Step/Question tree remains outside platform FLOW")
    if re.search(
        r"(?:^|\n)\s*(?:---\s*)?(?:DISCOVERY(?:\s+RULES)?|RECOMMENDATION(?:\s+RULES)?)\b",
        non_flow,
        re.I,
    ):
        reasons.append("non-canonical DISCOVERY/RECOMMENDATION section remains")

    brief_keys = _money_digit_keys(brief)
    for match in _MONEY_AMOUNT.finditer(body):
        span = match.group(0)
        # Guardrail language ("Never invent prices") has no digit amounts.
        digits = re.sub(r"[^\d]", "", span)
        if not digits:
            continue
        key = digits.lstrip("0") or "0"
        if key not in brief_keys:
            reasons.append(f"price/amount not in brief: {span[:48]}")
            break

    return reasons


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
    for title in (
        "AGENT IDENTITY",
        "OPENING",
        "WORK SCOPE",
        "ROLE & OBJECTIVE",
        "LIVE CALL GUIDE",
        *_SPRAWL_HEADERS,
    ):
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
        f"Example opening: {opening_line}\n"
        "ONE spoken reply per turn — never paste a greeting then restart with a second greeting.\n"
        "First speak: opening once only (intro + ask if they have a moment — no name/qualify in the same breath).\n"
        "If opening already spoken (PSTN): never re-greet. Answer briefly; if open, take next missing "
        "lead field (interest once → name → WORK SCOPE preference → next step). At most one question.\n"
        "If they already said interested: never re-ask interest — acknowledge and progress.\n"
        "If the caller spoke first: one short identifying answer — do not dump then revise the canned opening."
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


def _sanitize_business_facts(brief: str, *, agent_name: str, company_name: str) -> str:
    """Facts-only block: strip agent-creation boilerplate and other speaker names."""
    scope = work_scope_from_brief(brief, company_name)
    agent_lower = (agent_name or "").strip().lower()
    if agent_lower:

        def _strip_other_speaker(match: re.Match[str]) -> str:
            name = _clean_identity_value(match.group(1))
            if not name:
                return ""
            if name.lower() == agent_lower:
                return match.group(0)
            if len(name.split()) <= 3:
                return ""
            return match.group(0)

        scope = re.sub(
            r"\b(?:this is|i am|i'm|my name is)\s+([A-Za-z][A-Za-z\s]{0,40}?)(?=[,\s.]|$)",
            _strip_other_speaker,
            scope,
            flags=re.I,
        )
    scope = re.sub(r"\s+", " ", scope).strip(" .,:;-")
    return scope or "Use the business objective from the agent brief."


def _structured_business_script(
    brief: str,
    *,
    agent_name: str,
    company_name: str,
    work_scope: str,
    opening_line: str,
    language: str = "te-IN",
) -> str:
    """Industry-standard structured script: identity, offer, opening, workflow, guardrails."""
    _ = language
    business = _sanitize_business_facts(brief, agent_name=agent_name, company_name=company_name)
    if not business.strip():
        business = (work_scope or brief or "").strip()
    if company_name:
        identity = (
            f"You are {agent_name}, representing {company_name}. "
            f"You are the only speaker on this call — always speak as {agent_name}."
        )
    else:
        identity = (
            f"You are {agent_name}. "
            f"You are the only speaker on this call — always speak as {agent_name}."
        )
    return (
        f"--- AGENT IDENTITY ---\n{identity}\n\n"
        f"--- COMPANY & OFFER ---\n{business}\n\n"
        f"--- CANONICAL OPENING ---\n"
        f"Say this once on your first turn after the callee speaks:\n{opening_line}\n"
        f"Never use inbound help-desk phrasing on the first turn.\n\n"
        f"--- OUTBOUND WORKFLOW ---\n"
        f"1. Wait for the callee to speak first (hello, yes, who is this).\n"
        f"2. One intro using CANONICAL OPENING — then listen.\n"
        f"3. If they have time: one discovery question from COMPANY & OFFER.\n"
        f"4. If busy: offer callback. If not interested: thank them and close.\n\n"
        f"--- OBJECTION HANDLING ---\n"
        f"Acknowledge the concern in one sentence; do not restart the full pitch.\n\n"
        f"--- GUARDRAILS ---\n"
        f"Never invent prices, availability, or policies.\n"
        f"Never greet twice in one call.\n"
        f"Never claim to be anyone except {agent_name}.\n"
        f"Never use help-desk language on the first turn.\n"
    )


def _simple_business_script(
    brief: str,
    *,
    agent_name: str,
    company_name: str,
    work_scope: str,
    opening_line: str,
    language: str = "te-IN",
) -> str:
    """Minimal script: identity + business facts from the brief. Prefer _structured_business_script."""
    return _structured_business_script(
        brief,
        agent_name=agent_name,
        company_name=company_name,
        work_scope=work_scope,
        opening_line=opening_line,
        language=language,
    )


def _legacy_deterministic_script(
    brief: str,
    *,
    agent_name: str,
    company_name: str,
    work_scope: str,
    opening_line: str,
    language: str = "te-IN",
    role: str = "other",
) -> str:
    """Legacy fallback — full sectional script when OpenAI is unavailable."""
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


_deterministic_script = _legacy_deterministic_script


async def _llm_generate_script(
    brief: str,
    *,
    language: str,
    budget_tokens: int,
    repair_hint: str = "",
) -> dict[str, Any] | None:
    """Legacy — full sectional script via structured LLM. Disabled unless ``use_llm=True``."""
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
        repair = (repair_hint or "").strip()
        repair_block = (
            f"\n\nPrevious draft failed validation — fix these and rewrite the full script:\n{repair}\n"
            "No Step/Question trees. No placeholders. No prices/amounts unless they appear in the brief.\n"
            if repair
            else ""
        )
        user = (
            f"Language: {language}\n\n"
            f"User brief:\n{brief}\n\n"
            "Infer the role from the brief. Write a FULL conversational policy with every section "
            "through CLOSING. Do not compress for token savings. Include every fee and location fact "
            "from the brief in WORK SCOPE."
            f"{repair_block}"
        )
        # Room for a full sectional script (no 400–800 word compression).
        script_tokens = max(4500, min(8000, int(budget_tokens) + 2000))

        async def _run():
            return await adapter.structured_completion(
                input_messages=[
                    {"role": "developer", "content": [{"type": "input_text", "text": system}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user}]},
                ],
                schema=AGENT_SCRIPT_SCHEMA,
                config=LLMConfig(
                    provider="openai",
                    model=http_openai_model(settings),
                ),
                schema_name="agent_calling_script",
                max_output_tokens=script_tokens,
            )

        payload = await asyncio.wait_for(_run(), timeout=45)
        script = str(payload.get("agent_script") or "").strip()
        if len(script) >= 80:
            return payload
        from server.utils.logger import logger

        logger.warning("[AGENT_SCRIPT] structured LLM returned empty/tiny script; trying plain fallback")
    except Exception as exc:
        from server.utils.logger import logger

        logger.warning(f"[AGENT_SCRIPT] structured LLM failed: {type(exc).__name__}: {str(exc)[:240]}")

    # Plain-text fallback when JSON schema truncates or fails — still better than a thin stub.
    return await _llm_generate_script_plain(brief, language=language, budget_tokens=budget_tokens)


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
        model = http_openai_model(settings)
        system = script_writer_system(language=language, budget_tokens=budget_tokens)
        user = (
            f"Language: {language}\n\nBrief:\n{brief}\n\n"
            "Write the complete calling script with all section headers through CLOSING. "
            "Do not compress for token savings.\n\nScript:"
        )
        out_tokens = max(4500, min(8000, int(budget_tokens) + 2000))
        response = await asyncio.wait_for(
            client.responses.create(
                model=model,
                input=[
                    {"role": "developer", "content": [{"type": "input_text", "text": system}]},
                    {"role": "user", "content": [{"type": "input_text", "text": user}]},
                ],
                max_output_tokens=out_tokens,
                store=False,
            ),
            timeout=45,
        )
        script = str(getattr(response, "output_text", None) or "").strip()
        if len(script) < 80:
            return None
        return {"agent_script": script}
    except Exception as exc:
        from server.utils.logger import logger

        logger.warning(f"[AGENT_SCRIPT] plain LLM failed: {type(exc).__name__}: {str(exc)[:200]}")
        return None


def _script_has_full_sections(script: str) -> bool:
    """Thin LLM drafts must not replace the rich sectional calling script used in audits."""
    upper = (script or "").upper()
    required = (
        "VOICE STYLE",
        "CONVERSATION FLOW",
        "OBJECTION HANDLING",
        "GUARDRAILS",
        "CLOSING",
    )
    if not all(title in upper for title in required):
        return False
    # Rough floor: a complete bound script is well above a 400–800 word compressed stub.
    return estimate_tokens(script) >= 900


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
    use_llm: bool = False,
) -> tuple[str, AgentScriptResult, int, int, int]:
    """
    Turn a short agent brief into a cached brain prompt.
    Default: minimal business-knowledge script + platform rules in ``_assemble_brain``.
    Set ``use_llm=True`` for legacy full sectional script generation.
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
    llm_payload: dict[str, Any] | None = None
    llm_name = ""
    llm_company = ""
    role_summary = ""
    key_facts: list[str] = []
    llm_role = ""
    model = "simple_business_v1"

    agent_name, company_name, work_scope, opening_line = resolve_script_identity(
        cleaned,
        language=lang,
    )
    if not role_summary:
        role_summary = work_scope
    role = infer_agent_role(cleaned, llm_role=llm_role)

    def _bind_script(raw: str) -> str:
        return ensure_script_identity_and_scope(
            raw,
            agent_name=agent_name,
            company_name=company_name,
            work_scope=work_scope,
            opening_line=opening_line,
            language=lang,
            role=role,
        )

    if use_llm:
        llm_payload = await _llm_generate_script(
            cleaned, language=lang, budget_tokens=budget_tokens
        )
        if llm_payload:
            script = str(llm_payload.get("agent_script") or "").strip()
            model = http_openai_model(get_settings())
            llm_name = str(llm_payload.get("agent_name") or "").strip()
            llm_company = str(llm_payload.get("company_name") or "").strip()
            role_summary = str(llm_payload.get("role_summary") or "").strip() or role_summary
            key_facts = list(llm_payload.get("key_facts") or [])[:8]
            llm_role = str(llm_payload.get("role") or "").strip()
            role = infer_agent_role(cleaned, llm_role=llm_role)
            agent_name, company_name, work_scope, opening_line = resolve_script_identity(
                cleaned,
                llm_name=llm_name,
                llm_company=llm_company,
                language=lang,
            )
        else:
            script = ""

        if not script:
            script = _legacy_deterministic_script(
                cleaned,
                agent_name=agent_name,
                company_name=company_name,
                work_scope=work_scope,
                opening_line=opening_line,
                language=lang,
                role=role,
            )
            model = "legacy_deterministic_v1"
        else:
            script = _bind_script(script)
            if not _script_has_full_sections(script):
                from server.utils.logger import logger

                logger.warning(
                    "[AGENT_SCRIPT] legacy LLM draft incomplete; using legacy deterministic script"
                )
                script = _legacy_deterministic_script(
                    cleaned,
                    agent_name=agent_name,
                    company_name=company_name,
                    work_scope=work_scope,
                    opening_line=opening_line,
                    language=lang,
                    role=role,
                )
                model = "legacy_deterministic_quality_floor_v1"

        validation_issues = validate_agent_script(
            script, brief=cleaned, agent_name=agent_name
        )
    else:
        script = _simple_business_script(
            cleaned,
            agent_name=agent_name,
            company_name=company_name,
            work_scope=work_scope,
            opening_line=opening_line,
            language=lang,
        )
        validation_issues = []

    if validation_issues and use_llm and llm_payload:
        from server.utils.logger import logger

        logger.warning(
            f"[AGENT_SCRIPT] validation failed, one regenerate: {'; '.join(validation_issues)[:240]}"
        )
        repair_payload = await _llm_generate_script(
            cleaned,
            language=lang,
            budget_tokens=budget_tokens,
            repair_hint="; ".join(validation_issues),
        )
        if repair_payload:
            repaired = str(repair_payload.get("agent_script", "")).strip()
            if repaired:
                script = _bind_script(repaired)
                validation_issues = validate_agent_script(
                    script, brief=cleaned, agent_name=agent_name
                )
                if not validation_issues:
                    llm_payload = repair_payload
                    llm_name = str(repair_payload.get("agent_name") or llm_name).strip()
                    llm_company = str(repair_payload.get("company_name") or llm_company).strip()
                    role_summary = (
                        str(repair_payload.get("role_summary") or "").strip() or role_summary
                    )
                    key_facts = list(repair_payload.get("key_facts") or key_facts)[:8]
                    model = http_openai_model(get_settings())
        if not _script_has_full_sections(script):
            validation_issues = list(validation_issues) + ["incomplete_script_sections"]

    if validation_issues and use_llm:
        from server.utils.logger import logger

        logger.warning(
            f"[AGENT_SCRIPT] legacy validation fallback: "
            f"{'; '.join(validation_issues)[:240]}"
        )
        script = _legacy_deterministic_script(
            cleaned,
            agent_name=agent_name,
            company_name=company_name,
            work_scope=work_scope,
            opening_line=opening_line,
            language=lang,
            role=role,
        )
        model = "legacy_deterministic_validation_fallback_v1"

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
        script = _simple_business_script(
            cleaned,
            agent_name=agent_name,
            company_name=company_name,
            work_scope=work_scope,
            opening_line=opening_line,
            language=lang,
        )
        script, compiled = _ensure_cache_floor(
            script=script,
            language=lang,
            style=style_val,
            call_end_policy=call_end_policy,
        )
        compiled_tokens = estimate_tokens(compiled)
        model = "simple_business_budget_fallback_v1"
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
