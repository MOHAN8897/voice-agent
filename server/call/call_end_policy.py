"""Session call-end policy — UI overlay + brain section + hangup reason allow-list."""
from __future__ import annotations

import re
from typing import Any

from server.prompts.agent_voice_rules import (
    CALL_END_DEFAULTS,
    CALL_END_FAREWELLS,
    normalize_compile_language,
    pack_get,
)

HANGUP_REASONS = ("goodbye", "firm_refusal", "goal_complete", "abuse", "out_of_scope")
DEFAULT_HANGUP_REASONS = ("goodbye", "firm_refusal", "goal_complete", "abuse")

CLOSING_TOOL_DESCRIPTION = (
    "Request the platform to end the call in the SAME turn as one short spoken farewell. "
    "Use firm_refusal/customer_declined for a clear refusal or opt-out, goodbye/caller_goodbye "
    "for an explicit end request, and goal_complete when the configured required outcome and "
    "applicable agreed next step are complete. A callback, visit or handoff is required only "
    "when that workflow applies and is permitted; never invent one to close an information or support call. "
    "Never call for bare okay/thanks, unclear speech, an unanswered question or busy without an end request. "
    "Before disconnect is committed, a meaningful new request may reopen the conversation. "
    "After an accepted close, finish the farewell once and stop; the platform disconnects "
    "immediately when farewell playback finishes, without a post-farewell silence wait."
)


def default_call_end_policy(language: str | None = None) -> dict[str, Any]:
    lang = normalize_compile_language(language)
    return {
        # Out-of-scope cannot be proven from one turn. It remains available as
        # an explicit policy overlay, but is unsafe as a default hangup reason.
        "allowedReasons": list(DEFAULT_HANGUP_REASONS),
        "farewell": pack_get(CALL_END_FAREWELLS, lang),
    }


def normalize_call_end_policy(raw: Any, *, language: str | None = None) -> dict[str, Any]:
    lang = normalize_compile_language(language)
    base = default_call_end_policy(lang)
    if not isinstance(raw, dict):
        return base
    reasons_raw = raw.get("allowedReasons") or raw.get("allowed_reasons")
    if isinstance(reasons_raw, list) and reasons_raw:
        reasons = [str(r).strip().lower() for r in reasons_raw if str(r).strip().lower() in HANGUP_REASONS]
        if reasons:
            base["allowedReasons"] = reasons
    farewell = str(raw.get("farewell") or "").strip()[:240]
    if farewell and farewell not in CALL_END_FAREWELLS.values():
        base["farewell"] = farewell
    return base


def allowed_reasons_for(policy: dict[str, Any] | None) -> frozenset[str]:
    if not policy:
        return frozenset(DEFAULT_HANGUP_REASONS)
    raw = policy.get("allowedReasons") or policy.get("allowed_reasons") or []
    reasons = [str(r).strip().lower() for r in raw if str(r).strip().lower() in HANGUP_REASONS]
    return frozenset(reasons or DEFAULT_HANGUP_REASONS)


def format_call_end_section(language: str | None, policy: dict[str, Any] | None = None) -> str:
    from server.call.hangup_judge import HANGUP_JUDGMENT_RULES

    lang = normalize_compile_language(language)
    normalized = normalize_call_end_policy(policy, language=lang)
    reasons = ", ".join(normalized["allowedReasons"])
    farewell = normalized["farewell"]
    locale_cues = re.sub(r"Farewell example:.*$", "", pack_get(CALL_END_DEFAULTS, lang)).strip()
    locale_cues = re.sub(
        r"Busy:.*?(?=Speak the farewell)",
        "Busy: offer a callback only when the configured workflow permits it; honor a requested stop. ",
        locale_cues,
    )
    return (
        "--- CALL END POLICY ---\n"
        f"{locale_cues}\n"
        f"{HANGUP_JUDGMENT_RULES}\n"
        f"Allowed hangup reasons for this agent: {reasons}. "
        "Never speak a farewell unless end_call.should_end is true. "
        f"Farewell example: `{farewell}` Speak the full line, then stop — "
        "the platform disconnects immediately when farewell playback finishes."
    )
