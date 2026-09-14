"""Session call-end policy — UI overlay + brain section + hangup reason allow-list."""
from __future__ import annotations

from typing import Any

from server.prompts.agent_voice_rules import (
    CALL_END_DEFAULTS,
    CALL_END_FAREWELLS,
    normalize_compile_language,
)

HANGUP_REASONS = ("goodbye", "firm_refusal", "goal_complete", "abuse", "out_of_scope")
DEFAULT_HANGUP_REASONS = ("goodbye", "firm_refusal", "goal_complete", "abuse")


def default_call_end_policy(language: str | None = None) -> dict[str, Any]:
    lang = normalize_compile_language(language)
    return {
        # Out-of-scope cannot be proven from one turn. It remains available as
        # an explicit policy overlay, but is unsafe as a default hangup reason.
        "allowedReasons": list(DEFAULT_HANGUP_REASONS),
        "farewell": CALL_END_FAREWELLS[lang],
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
        return frozenset(HANGUP_REASONS)
    raw = policy.get("allowedReasons") or []
    reasons = [str(r).strip().lower() for r in raw if str(r).strip().lower() in HANGUP_REASONS]
    return frozenset(reasons or HANGUP_REASONS)


def format_call_end_section(language: str | None, policy: dict[str, Any] | None = None) -> str:
    from server.call.hangup_judge import HANGUP_JUDGMENT_RULES

    lang = normalize_compile_language(language)
    normalized = normalize_call_end_policy(policy, language=lang)
    reasons = ", ".join(normalized["allowedReasons"])
    farewell = normalized["farewell"]
    return (
        "--- CALL END POLICY ---\n"
        f"{CALL_END_DEFAULTS[lang]}\n"
        f"{HANGUP_JUDGMENT_RULES}\n"
        f"Allowed hangup reasons for this agent: {reasons}. "
        "Never speak a farewell unless end_call.should_end is true. "
        f"Farewell example: `{farewell}` Speak the full line, then stop — the platform disconnects after it plays."
    )
