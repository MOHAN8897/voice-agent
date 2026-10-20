"""Gemini Live instructions for primary web and PSTN sessions."""
from __future__ import annotations

import re

from server.agent.brain_prompt_composer import estimate_tokens
from server.brain.sections import STATIC_OUTPUT_RULES
from server.prompts.agent_voice_rules import live_audio_modality_rules, spoken_pack_for
from server.realtime.text_session import _is_outbound, first_turn_identity_rules
from server.services.pstn_text_chunker import _parse_agent_identity

# The instruction is re-sent on every live session, so its size is a recurring
# per-call cost. 8_500 was far above what the rules actually need: the same
# brevity block and the same language lock were each embedded 3-4 times.
GEMINI_LIVE_INSTRUCTION_TOKEN_BUDGET = 2_500

# The hangup policy, the guardrails and the script discipline are what make a
# call safe to end and safe to run. They are never the thing that gets trimmed to
# reach the budget, so the brain support keeps at least this much.
GEMINI_MIN_BRAIN_SUPPORT_TOKENS = 900

GEMINI_TURN_STYLE = (
    "Keep spoken turns to one or two concise, complete sentences. Answer first. "
    "Acknowledge only when useful; ask at most one relevant question, then wait. "
    "A brief answer is enough when no follow-up is needed. Never cut words or add filler."
)

_SECTION_HEADER = re.compile(r"(?:^|\n)---\s*(.+?)\s*---\s*\n", re.IGNORECASE)

# Blocks that appear verbatim more than once in the assembled instruction. Keeping
# the first copy and dropping the rest changes no rule the model is asked to follow;
# it only stops paying for the same sentence several times.
_DUPLICATED_RULE_BLOCKS: tuple[str, ...] = ()


def _load_duplicate_rule_blocks() -> tuple[str, ...]:
    """Resolve the duplicated blocks lazily so import order stays acyclic."""
    global _DUPLICATED_RULE_BLOCKS
    if _DUPLICATED_RULE_BLOCKS:
        return _DUPLICATED_RULE_BLOCKS
    from server.prompts.agent_voice_rules import LANGUAGE_LOCK
    from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE

    blocks = [LIVE_REPLY_BREVITY_RULE, *LANGUAGE_LOCK.values()]
    _DUPLICATED_RULE_BLOCKS = tuple(b.strip() for b in blocks if b and len(b.strip()) > 80)
    return _DUPLICATED_RULE_BLOCKS


def _strip_repeated_rule_blocks(text: str) -> str:
    """Keep the first occurrence of each known-duplicated rule block."""
    for block in _load_duplicate_rule_blocks():
        if text.count(block) <= 1:
            continue
        first = text.find(block)
        head, tail = text[: first + len(block)], text[first + len(block) :]
        tail = tail.replace(block, "")
        text = head + tail
    return re.sub(r"\n{4,}", "\n\n", text).strip()

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
    "WORK SCOPE",
    "ROLE & OBJECTIVE",
    "BUSINESS KNOWLEDGE",
    "COMPANY",
    "CALLING SCRIPT",
    "OPENING",
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
    raw = _strip_repeated_rule_blocks(raw)
    from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE
    # Character budgets belong to text/TTS plumbing, not native spoken output.
    raw = raw.replace(LIVE_REPLY_BREVITY_RULE, GEMINI_TURN_STYLE)
    raw = re.sub(r"\n{4,}", "\n\n", raw)
    return raw.strip()


def _split_brain_sections(brain: str) -> list[tuple[str, str]]:
    """Return (title, body) pairs in document order; merge duplicate titles."""
    if not brain.strip():
        return []
    matches = list(_SECTION_HEADER.finditer(brain))
    if not matches:
        return [("BODY", brain.strip())]
    preamble = brain[:matches[0].start()].strip()
    raw: list[tuple[str, str]] = [("PREAMBLE", preamble)] if preamble else []
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
            if needle == upper and body.strip():
                blocks.append(f"PINNED {needle}\n{body.strip()}")
                break
    return "\n\n".join(blocks)


def _gemini_tail_section_excluded(title: str) -> bool:
    upper = title.upper().strip()
    if upper in _GEMINI_TAIL_EXCLUDE_TITLES:
        return True
    if upper.startswith("SPOKEN LANGUAGE"):
        return True
    return False


def _spoken_section_matches_language(title: str, language: str | None) -> bool:
    """True when a `SPOKEN LANGUAGE (xx-YY)` heading is the one for this call."""
    upper = title.upper()
    if not upper.startswith("SPOKEN LANGUAGE"):
        return False
    if not language:
        return True
    return f"({language.upper()})" in upper


def _gemini_support_sections_only(
    brain: str,
    *,
    keep_spoken_pack: bool = False,
    language: str | None = None,
) -> str:
    """Platform tail for Gemini Live — excludes user script already PINNED above.

    A compiled brain can carry several `SPOKEN LANGUAGE` packs (the console keeps
    every configured language). Keeping all of them shipped the wrong language's
    register to the model, so only the pack for this call is retained.
    """
    sections = _split_brain_sections(brain)
    if not sections:
        return brain.strip()
    kept: list[str] = []
    for title, body in sections:
        upper = title.upper().strip()
        if upper.startswith("SPOKEN LANGUAGE"):
            if keep_spoken_pack and _spoken_section_matches_language(title, language):
                if body.strip():
                    kept.append(f"--- {title} ---\n{body.strip()}")
            continue
        if _gemini_tail_section_excluded(title):
            continue
        if not body.strip():
            continue
        kept.append(f"--- {title} ---\n{body.strip()}")
    return "\n\n".join(kept).strip()


def _extract_spoken_language_section(brain: str, language: str | None = None) -> str:
    for title, body in _split_brain_sections(brain):
        if _spoken_section_matches_language(title, language) and body.strip():
            return f"--- {title} ---\n{body.strip()}"
    return ""


def _extract_pinned_flow(brain: str) -> str:
    sections = _split_brain_sections(brain)
    return "\n\n".join(f"{title}\n{body}" for title, body in sections
                        if title in _FLOW_PIN_TITLES and body.strip())


def prioritize_brain_for_gemini(brain: str, token_budget: int) -> str:
    """Order complete sections; the budget never authorizes deleting business policy."""
    brain = brain.strip()
    if not brain or token_budget <= 0:
        return brain
    if estimate_tokens(brain) <= token_budget:
        return brain
    sections = _split_brain_sections(brain)
    if not sections:
        return brain
    ordered: list[tuple[str, str]] = []
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
    # This budget is a target, not permission to erase safety or cut a policy
    # sentence in half. Reserve complete mandatory sections before optional prose.
    mandatory = {"SAFETY", "CALL END POLICY", "STATIC OUTPUT RULES", "GUARDRAILS"}
    ordered = ([item for item in ordered if item[0] in mandatory]
               + [item for item in ordered if item[0] not in mandatory])
    return "\n\n".join(f"--- {title} ---\n{body}" for title, body in ordered).strip()


def _gemini_outbound_block(
    language: str,
    opening_greeting: str | None,
) -> str:
    line = (opening_greeting or "").strip()
    parts = [
        "CALL DIRECTION (outbound)",
        "- You placed this call. VAD is on — do not speak first while the line is silent.",
        "- The platform plays your scripted opening as audio after the callee speaks (hello / yes).",
        "- If that opening was already spoken, never repeat it verbatim; answer their actual question.",
        "- If opening delivery has not been confirmed, use CANONICAL OPENING once, then wait for their reply.",
        "- If they ask who is calling: one beat with agent name + company + purpose from AGENT IDENTITY.",
        "- After intro, follow CONVERSATION FLOW / OUTBOUND or INBOUND WORKFLOW in order; "
        "skip steps they already answered.",
        "- Turn discipline: 1–2 short sentences, then stop. At most one question per turn.",
        "- If they are busy: one callback offer, no pitch. Stay on the line.",
        "- CONTACT: You already called the customer number. Do not ask for their phone number again. "
        "Ask their preferred name once after they agree to speak, if unknown. "
        "Only collect an alternative phone if they request one; never read the connected digits aloud.",
    ]
    if line:
        parts.append(f"[Canonical opening line already spoken or to match]\n{line}")
    return "\n".join(parts)


def _gemini_audio_and_tools() -> str:
    return (
        "CONVERSATION ACTIONS (override conflicting sales instructions)\n"
        "Speak answers naturally. request_end_call (or end_call) in the same turn as a short farewell "
        "when they clearly end or the script objective and agreed next step are complete. "
        "Do not end for okay/thanks alone, unclear speech, or an unanswered question. "
        "After the accepted farewell, stop; the platform disconnects.\n\n"
        "AUDIO & TOOLS\n"
        "- Speak naturally; no JSON, markdown, labels, or tool names aloud.\n"
        "- Answer ordinary questions directly as speech. call_action is for real call-control decisions; its response field does not replace spoken audio.\n"
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
    """Build one selected-language instruction without dropping authored business content."""
    from server.brain.compiled_brain_artifact import refresh_platform_sections
    raw_brain = condense_compiled_brain_for_gemini(refresh_platform_sections(compiled_brain, language))
    parts: list[str] = [
        "You are a professional live phone agent. Use the business script and the selected language naturally.",
    ]
    name, company = _parse_agent_identity(compiled_brain or "")
    if name or company:
        who = f"{name}, {company}" if company else name
        parts.append(f"PINNED IDENTITY (always use when asked who is calling): {who}.")
    parts.append(live_audio_modality_rules())
    if not _is_outbound(direction):
        parts.append(first_turn_identity_rules(language, direction=direction))
    # Reserve flow before large opening-policy/knowledge sections can consume
    # the budget. This is a deterministic excerpt, not a second LLM summary.
    flow = _extract_pinned_flow(raw_brain)
    if flow:
        parts.append(
            "PINNED CONVERSATION FLOW\n"
            "After the platform confirms opening delivery, treat the greeting as done. "
            "Continue at the first unanswered step; do not repeat questions already answered.\n"
            + flow
        )
    business_pin = _extract_pinned_business(raw_brain)
    if business_pin:
        parts.append(
            "PINNED BUSINESS SCRIPT (mandatory — follow on every turn; do not invent facts)\n"
            + business_pin
        )
    parts.append(
        "Use the supplied business facts. Say when a business detail is unknown; do not invent prices, policies or completed actions."
    )
    # Build the tail parts first. They used to be appended after the brain was
    # trimmed, so they were never charged against the budget: the brain support
    # was cut to fit while these landed on top, and the budget was fiction.
    tail: list[str] = []
    spoken = spoken_pack_for(language, include_brevity=False, core_only=True)
    if spoken:
        tail.append(spoken)
    if _is_outbound(direction):
        tail.append(_gemini_outbound_block(language, opening_greeting))
    elif caller_id:
        tail.append("[Caller context]\nInbound caller connected (do not read their number aloud).")
    tail.append(_gemini_audio_and_tools())
    tail.append(
        "CONTACT PRIORITY: Ask an unknown preferred name at a natural pause after consent. "
        "On outbound calls the dialed number is already known; ask only if a different number is requested."
    )

    head_cost = estimate_tokens("\n\n".join(parts))
    tail_cost = sum(estimate_tokens(t) for t in tail)
    # The target orders sections and measures overhead. Long authored scripts
    # are allowed to exceed it; no facts, FAQ or policy may be cut to fit.
    brain_budget = max(GEMINI_MIN_BRAIN_SUPPORT_TOKENS, token_budget - head_cost - tail_cost) if token_budget > 0 else 0
    # The spoken pack is appended explicitly above, so drop it from the brain
    # support; otherwise the same register rules are paid for twice.
    support = (
        _gemini_support_sections_only(raw_brain, keep_spoken_pack=False, language=language)
        if raw_brain
        else ""
    )
    brain = prioritize_brain_for_gemini(support, brain_budget) if support else ""
    if brain:
        parts.append(brain)
    parts.extend(tail)
    joined = "\n\n".join(p.strip() for p in parts if p and p.strip())
    joined = joined.replace(
        "NEVER switch your spoken language. Every single reply MUST be in the configured agent language.",
        "Use the configured primary language with natural English mixing.",
    ).replace(
        "Never switch your spoken language — respond only in the configured language.",
        "Use the configured primary language with natural English mixing.",
    ).replace(
        "LANGUAGE: NEVER switch languages. Respond ONLY in the configured language.",
        "LANGUAGE: Use the selected primary language with natural English mixing.",
    ).replace(
        "You MUST respond ONLY in the configured agent language for every single reply.",
        "Use the selected primary language with natural English mixing.",
    )
    return _strip_repeated_rule_blocks(joined)
