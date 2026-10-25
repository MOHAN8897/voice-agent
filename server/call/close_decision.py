"""Shared close-decision contract for every voice pipeline.

The model proposes one compact decision; the server validates it against the
current caller turn. Intent comes from meaning plus an evidence span, never
from a phrase list — a phrase list can only repair a missing tool call, and a
regex match alone never justifies a permanent opt-out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CLOSE_DECISIONS = ("continue", "clarify", "close", "callback")
CONTACT_PREFERENCES = ("none", "end_call", "do_not_call", "callback")
CLOSE_REASONS = (
    "none",
    "goodbye",
    "firm_refusal",
    "not_interested",
    "goal_complete",
    "abuse",
    "out_of_scope",
)

_PUNCT = re.compile(r"[^\w]+", re.UNICODE)

# Strong stop-contact language only. A soft "don't call me at night" is a
# preference, not a permanent opt-out, so it must not reach the DNC registry.
_OPT_OUT_EVIDENCE = re.compile(
    r"don'?t\s+(?:ever\s+)?(?:call|contact)\s+(?:me\s+)?(?:again|anymore|ever|at\s+all)|"
    r"do\s+not\s+(?:ever\s+)?(?:call|contact)\s+(?:me\s+)?(?:again|anymore|ever|at\s+all)|"
    r"never\s+(?:call|contact)|stop\s+(?:calling|the\s+calls)|"
    r"remove\s+me|take\s+me\s+off|"
    r"(?:కాల్|ఫోన్|call).{0,24}(?:వద్దు|చేయకండి|చేయొద్దు|అవసరం\s*లేదు)|"
    r"(?:कॉल|फोन|संपर्क|call).{0,24}(?:नहीं|मत|बंद|न\s*करें)|"
    r"(?:அழைக்க|தொடர்பு|கால்).{0,24}(?:வேண்டாம்|கூடாது)|"
    r"(?:ಕರೆ|ಫೋನ್|ಸಂಪರ್ಕ).{0,24}(?:ಬೇಡ|ಮಾಡಬೇಡಿ)|"
    r"(?:കോൾ|ഫോൺ|ബന്ധപ്പെട|വിളിക്ക).{0,24}(?:വേണ്ട|ഇല്ല|രുത്|േണ്ട(?!ത))|"
    r"(?:কল|ফোন|যোগাযোগ).{0,24}(?:নয়|না|করবেন\s*না)|"
    r"(?:કૉલ|કોલ|ફોન|સંપર્ક).{0,24}(?:નહીં|ના|ન\s*કરો)|"
    r"(?:ਕਾਲ|ਫੋਨ|ਸੰਪਰਕ).{0,24}(?:ਨਹੀਂ|ਨਾ)|"
    r"(?:कॉल|फोन|संपर्क).{0,24}(?:नको|नका)",
    re.I | re.S,
)

_CONTINUATION_LINES: dict[str, str] = {
    "te": "తప్పకుండా, చెప్పండి.",
    "hi": "ज़रूर, बताइए।",
    "mr": "नक्कीच, सांगा.",
    "ta": "கண்டிப்பாக, சொல்லுங்கள்.",
    "kn": "ಖಂಡಿತ, ಹೇಳಿ.",
    "ml": "തീർച്ചയായും, പറയൂ.",
    "bn": "অবশ্যই, বলুন।",
    "gu": "ચોક્કસ, કહો.",
    "pa": "ਜ਼ਰੂਰ, ਦੱਸੋ।",
    "en": "Of course — please go ahead.",
}


@dataclass(frozen=True)
class CloseProposal:
    decision: str
    reason: str
    should_end: bool
    evidence: str
    remaining_request: str
    contact_preference: str
    farewell: str
    conflict: bool = False


def _text(raw: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(raw or "")).strip()[:limit]


def parse_close_proposal(raw: Any) -> CloseProposal:
    if not isinstance(raw, dict):
        return CloseProposal("continue", "none", False, "", "", "none", "")
    explicit_decision = str(raw.get("decision") or "").strip().lower()
    reason = str(raw.get("reason") or "none").strip().lower()
    if reason not in CLOSE_REASONS:
        reason = "none"
    should_end = raw.get("should_end") is True
    decision = explicit_decision if explicit_decision in CLOSE_DECISIONS else (
        "close" if should_end else "continue"
    )
    # An explicit decision is the semantic signal; a should_end that is present
    # must agree with it. Omitting should_end is the compact contract, not a conflict.
    conflict = (
        "should_end" in raw
        and bool(explicit_decision in CLOSE_DECISIONS)
        and should_end != (decision == "close")
    )
    ends = (decision == "close") or (should_end and not explicit_decision)
    preference = str(raw.get("contact_preference") or "").strip().lower()
    if preference not in CONTACT_PREFERENCES:
        preference = ""
    if not preference and decision == "callback":
        preference = "callback"
    return CloseProposal(
        decision=decision,
        reason=reason,
        should_end=ends,
        evidence=_text(raw.get("evidence"), 200),
        remaining_request=_text(raw.get("remaining_request"), 240),
        contact_preference=preference,
        farewell=_text(raw.get("farewell"), 240),
        conflict=conflict,
    )


def _normalized(text: str) -> str:
    return _PUNCT.sub("", (text or "").casefold())


def evidence_matches(evidence: str, transcript: str) -> bool:
    """True when the span is present in the caller's own current words."""
    needle = _normalized(evidence)
    if len(needle) < 3:
        return False
    return needle in _normalized(transcript)


def meaningful_remaining_request(text: str) -> bool:
    cleaned = _text(text, 240)
    if len(cleaned) < 4:
        return False
    return cleaned.casefold() not in {"none", "null", "n/a", "na", "nothing"}


def continuation_line_for(language: str | None) -> str:
    from server.prompts.agent_voice_rules import normalize_compile_language

    lang = normalize_compile_language(language)
    return _CONTINUATION_LINES.get(lang.split("-")[0], _CONTINUATION_LINES["en"])


def opt_out_evidence(text: str) -> bool:
    """True only when the words themselves ask to stop being contacted."""
    return bool(_OPT_OUT_EVIDENCE.search((text or "").casefold()))


def contact_preference_for(
    proposed: str,
    *,
    reason: str,
    user_text: str,
    evidence: str,
    opt_out_matched: bool,
    callback_requested: bool,
) -> str:
    """Keep 'end this call' separate from 'never call me again'."""
    evidence_opt_out = evidence_matches(evidence, user_text) and opt_out_evidence(evidence)
    # A callback request makes a soft "don't call" ambiguous, so only words that
    # are final on their own may still enroll the caller in DNC.
    opt_out = evidence_opt_out or (opt_out_matched and not callback_requested)
    if opt_out:
        return "do_not_call"
    if proposed == "callback":
        return "callback"
    if proposed == "end_call":
        return "end_call"
    if reason == "goal_complete" and callback_requested:
        return "callback"
    return "end_call" if reason != "none" else "none"
