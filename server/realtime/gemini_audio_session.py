"""Gemini Live PSTN instructions — OpenAI Realtime audio parity, no prompt-cache padding."""
from __future__ import annotations

import re

from server.agent.brain_prompt_composer import estimate_tokens, fit_text_to_tokens
from server.brain.sections import STATIC_OUTPUT_RULES
from server.prompts.agent_voice_rules import live_realtime_audio_rules
from server.realtime.text_session import _is_outbound, first_turn_identity_rules
from server.services.pstn_text_chunker import _parse_agent_identity

GEMINI_LIVE_INSTRUCTION_TOKEN_BUDGET = 8_500

_SECTION_HEADER = re.compile(r"(?:^|\n)---\s*(.+?)\s*---\s*\n", re.IGNORECASE)

_FLOW_PIN_TITLES = (
    "CONVERSATION FLOW",
    "OUTBOUND WORKFLOW",
    "INBOUND WORKFLOW",
    "LIVE CALL GUIDE",
)

_PINNED_BUSINESS_TITLES = (
    "ENTITY TAGS",
    "AGENT IDENTITY",
    "COMPANY & OFFER",
    "CANONICAL OPENING",
    "YOUR ROLE ON THIS CALL",
)

_PRIORITY_SECTIONS = (
    "PLATFORM CALL RULES",
    "CALL END POLICY",
    "STATIC OUTPUT RULES",
    "TURN DISCIPLINE",
    "LEAD CAPTURE",
    "PROFESSIONAL CLOSE",
    "OBJECTION HANDLING",
    "GUARDRAILS",
    "SAFETY",
)

# User business + flow are injected as PINNED blocks above; never repeat in the tail.
_GEMINI_TAIL_EXCLUDE_TITLES = frozenset(
    {
        "CALLING SCRIPT",
        "ENTITY TAGS",
        "AGENT IDENTITY",
        "COMPANY & OFFER",
        "CANONICAL OPENING",
        "YOUR ROLE ON THIS CALL",
        "CONVERSATION FLOW",
        "OUTBOUND WORKFLOW",
        "INBOUND WORKFLOW",
        "LIVE CALL GUIDE",
        "OPENING",
        "WORK SCOPE",
        "ROLE & OBJECTIVE",
        "BUSINESS KNOWLEDGE",
        "COMPANY",
        "PHONE CALL",
        "VOICE EXAMPLES",
        "OVERLAP",
    }
)


def condense_compiled_brain_for_gemini(compiled_brain: str | None) -> str:
    """Drop OpenAI cache-padding duplicates; keep one copy of static safety rules."""
    raw = (compiled_brain or "").strip()
    if not raw:
        return ""
    static = STATIC_OUTPUT_RULES.strip()
    if static and raw.count(static) > 1:
        first = raw.find(static)
        tail = raw[first + len(static) :]
        while static in tail:
            idx = tail.find(static)
            tail = tail[:idx] + tail[idx + len(static) :]
        raw = f"{raw[:first]}{static}{tail}"
    raw = re.sub(r"\n{4,}", "\n\n", raw)
    return raw.strip()


def _split_brain_sections(brain: str) -> list[tuple[str, str]]:
    """Return (title, body) pairs in document order; merge duplicate titles."""
    if not brain.strip():
        return []
    matches = list(_SECTION_HEADER.finditer(brain))
    if not matches:
        return [("BODY", brain.strip())]
    raw: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        title = match.group(1).strip().upper()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(brain)
        body = brain[start:end].strip()
        if body:
            raw.append((title, body))
    merged: dict[str, str] = {}
    order: list[str] = []
    for title, body in raw:
        if title in merged:
            merged[title] = f"{merged[title]}\n\n{body}"
        else:
            merged[title] = body
            order.append(title)
    return [(t, merged[t]) for t in order]


def _extract_pinned_business(brain: str) -> str:
    """Always retain user business script sections (not trimmed away by token budget)."""
    blocks: list[str] = []
    for title, body in _split_brain_sections(brain):
        upper = title.upper()
        for needle in _PINNED_BUSINESS_TITLES:
            if needle in upper and body.strip():
                blocks.append(f"PINNED {needle}\n{fit_text_to_tokens(body.strip(), 1400)}")
                break
    return "\n\n".join(blocks)


def _gemini_tail_section_excluded(title: str) -> bool:
    upper = title.upper().strip()
    if upper in _GEMINI_TAIL_EXCLUDE_TITLES:
        return True
    if upper.startswith("SPOKEN LANGUAGE"):
        return True
    return False


def _gemini_support_sections_only(brain: str) -> str:
    """Platform tail for Gemini Live — excludes user script already PINNED above."""
    sections = _split_brain_sections(brain)
    if not sections:
        return brain.strip()
    kept: list[str] = []
    for title, body in sections:
        if _gemini_tail_section_excluded(title):
            continue
        if not body.strip():
            continue
        kept.append(f"--- {title} ---\n{body.strip()}")
    return "\n\n".join(kept).strip()


def _extract_pinned_flow(brain: str) -> str:
    for title, body in _split_brain_sections(brain):
        upper = title.upper()
        for needle in _FLOW_PIN_TITLES:
            if needle in upper and body.strip():
                return body
    for needle in _FLOW_PIN_TITLES:
        pat = re.compile(
            rf"(?:^|\n)---\s*{re.escape(needle)}\s*---\s*\n(.*?)(?=\n---\s*[^-\n]+\s*---|\Z)",
            re.S | re.I,
        )
        match = pat.search(brain or "")
        if match and match.group(1).strip():
            return match.group(1).strip()
    return ""


def prioritize_brain_for_gemini(brain: str, token_budget: int) -> str:
    """Keep identity, opening, and flow when trimming — same facts OpenAI path retains."""
    brain = brain.strip()
    if not brain or token_budget <= 0:
        return brain
    if estimate_tokens(brain) <= token_budget:
        return brain
    preamble = ""
    matches = list(_SECTION_HEADER.finditer(brain))
    if matches and matches[0].start() > 0:
        preamble = brain[: matches[0].start()].strip()
    sections = _split_brain_sections(brain)
    if not sections:
        return fit_text_to_tokens(brain, token_budget)
    ordered: list[tuple[str, str]] = []
    if preamble:
        ordered.append(("PREAMBLE", preamble))
    seen: set[str] = set()
    for want in _PRIORITY_SECTIONS:
        for title, body in sections:
            if want in title.upper() and title not in seen:
                ordered.append((title, body))
                seen.add(title)
                break
    for title, body in sections:
        if title not in seen:
            ordered.append((title, body))
            seen.add(title)
    chunks: list[str] = []
    used = 0
    for title, body in ordered:
        block = f"--- {title} ---\n{body}"
        tok = estimate_tokens(block)
        if used + tok > token_budget:
            room = max(80, token_budget - used - 12)
            if room < 100:
                break
            block = f"--- {title} ---\n{fit_text_to_tokens(body, room)}"
            tok = estimate_tokens(block)
        chunks.append(block)
        used += tok
        if used >= token_budget:
            break
    return "\n\n".join(chunks).strip() or fit_text_to_tokens(brain, token_budget)


def _gemini_outbound_block(
    language: str,
    opening_greeting: str | None,
) -> str:
    line = (opening_greeting or "").strip()
    parts = [
        "CALL DIRECTION (outbound — mandatory; same as OpenAI Realtime PSTN)",
        "- You placed this call. VAD is on — do not speak first while the line is silent.",
        "- The platform plays your scripted opening as audio after the callee speaks (hello / yes).",
        "- If that opening was already spoken, never repeat it verbatim; answer their actual question.",
        "- If they ask who is calling: one beat with agent name + company + purpose from AGENT IDENTITY.",
        "- After intro, follow CONVERSATION FLOW / OUTBOUND or INBOUND WORKFLOW in order; "
        "skip steps they already answered.",
        "- Turn discipline: 1–2 short sentences, then stop. At most one question per turn.",
        "- If they are busy: one callback offer, no pitch. Stay on the line.",
    ]
    if line:
        parts.append(f"[Canonical opening line already spoken or to match]\n{line}")
    return "\n".join(parts)


def _gemini_audio_and_tools() -> str:
    return (
        "CONVERSATION ACTIONS (override conflicting sales instructions)\n"
        "Speak answers naturally. request_end_call (or end_call) in the same turn as a short farewell "
        "when they clearly end or confirmed a callback. Do not end for okay/thanks alone.\n\n"
        "AUDIO & TOOLS\n"
        "- Speak naturally; no JSON, markdown, labels, or tool names aloud.\n"
        "- Do not hang up on okay, thanks, or a follow-up question alone."
    )


def build_gemini_audio_session_instructions(
    compiled_brain: str | None,
    *,
    caller_id: str | None = None,
    language: str = "te-IN",
    direction: str | None = None,
    opening_greeting: str | None = None,
    token_budget: int = GEMINI_LIVE_INSTRUCTION_TOKEN_BUDGET,
) -> str:
    """Gemini Live system_instruction aligned with OpenAI build_audio_session_instructions."""
    raw_brain = condense_compiled_brain_for_gemini(compiled_brain)
    parts: list[str] = [
        "GEMINI LIVE PSTN — same behavior as OpenAI Realtime speech-to-speech on this platform.",
    ]
    name, company = _parse_agent_identity(compiled_brain or "")
    if name or company:
        who = f"{name}, {company}" if company else name
        parts.append(f"PINNED IDENTITY (always use when asked who is calling): {who}.")
    parts.append(live_realtime_audio_rules(language, direction=direction))
    parts.append(first_turn_identity_rules(language, direction=direction))
    # Reserve flow before large opening-policy/knowledge sections can consume
    # the budget. This is a deterministic excerpt, not a second LLM summary.
    flow = _extract_pinned_flow(raw_brain)
    if flow:
        parts.append(
            "PINNED CONVERSATION FLOW\n"
            "After the platform confirms opening delivery, treat the greeting as done. "
            "Continue at the first unanswered step; do not repeat questions already answered.\n"
            + fit_text_to_tokens(flow, 1600)
        )
    business_pin = _extract_pinned_business(raw_brain)
    if business_pin:
        parts.append(
            "PINNED BUSINESS SCRIPT (mandatory — follow on every turn; do not invent facts)\n"
            + business_pin
        )
    parts.append(
        "ADHERENCE: Answer only from PINNED BUSINESS SCRIPT and COMPANY & OFFER facts. "
        "If a price or policy is not in the script, say you will confirm and offer a callback."
    )
    parts.append(
        f"SPOKEN LANGUAGE: default {language}. Mirror the caller when they clearly use another "
        "supported product language (te-IN, hi-IN, en-IN, en-US) while keeping the same script "
        "and goals. A transcript correction cannot correct audio already spoken."
    )
    reserve = estimate_tokens("\n\n".join(parts)) + 400
    brain_budget = max(1200, token_budget - reserve) if token_budget > 0 else 0
    support = _gemini_support_sections_only(raw_brain) if raw_brain else ""
    brain = prioritize_brain_for_gemini(support, brain_budget) if support else ""
    if brain:
        parts.append(brain)
    if _is_outbound(direction):
        parts.append(_gemini_outbound_block(language, opening_greeting))
    elif caller_id:
        parts.append("[Caller context]\nInbound caller connected (do not read their number aloud).")
    parts.append(_gemini_audio_and_tools())
    return "\n\n".join(p.strip() for p in parts if p and p.strip())
