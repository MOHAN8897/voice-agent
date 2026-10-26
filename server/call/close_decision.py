"""Shared close-decision contract for every voice pipeline.

The model proposes one compact decision; the server validates it against the
current caller turn. Intent comes from meaning plus an evidence span, never
from a phrase list — a phrase list can only repair a missing tool call, and a
regex match alone never justifies a permanent opt-out.
"""
from __future__ import annotations

import re
import unicodedata
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
    r"(?:அழைக்க|தொடர்பு|கால்|call).{0,24}(?:வேண்டாம்|கூடாது|செய்யாதீங்க|செய்யாதீர்கள்|வேண்டாம)|"
    r"(?:ಕರೆ|ಫೋನ್|ಸಂಪರ್ಕ|call).{0,24}(?:ಬೇಡ|ಬೇಡಿ|ಮಾಡಬೇಡಿ|ಮಾಡಬೇಡ)|"
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
    # STT providers disagree on composed/decomposed Indic vowels; normalize
    # before stripping so a quote and the transcript still compare equal.
    return _PUNCT.sub("", unicodedata.normalize("NFC", (text or "").casefold()))


def evidence_matches(evidence: str, transcript: str) -> bool:
    """True when the span is present in the caller's own current words."""
    needle = _normalized(evidence)
    if len(needle) < 2:
        return False
    norm_trans = _normalized(transcript)
    if len(norm_trans) < 2:
        return False
    return needle in norm_trans


def meaningful_remaining_request(text: str) -> bool:
    """Any real leftover ask blocks a close, however short the note is.

    The model writes short notes like "price" or "ధర"; a four-character
    minimum silently discarded exactly those asks. Only the explicit "none"
    spellings the schema invites are empty.
    """
    cleaned = _text(text, 240).casefold()
    if not cleaned:
        return False
    return cleaned.strip(" .,!?;:-") not in {
        "none", "null", "n/a", "na", "nothing", "no request",
    }


def continuation_line_for(language: str | None) -> str:
    from server.prompts.agent_voice_rules import normalize_compile_language

    lang = normalize_compile_language(language)
    return _CONTINUATION_LINES.get(lang.split("-")[0], _CONTINUATION_LINES["en"])


_FAREWELL_ONLY = re.compile(
    r"^(?:ok(?:ay)?|sure|thanks?|thank\s+you|bye|goodbye|good\s+night|"
    r"have\s+a\s+(?:nice|good|wonderful)\s+day|thank\s+you\s+for\s+(?:calling|your\s+time)|"
    r"ధన్యవాదాలు|నమస్కారం|सधन्यवाद|नमस्ते|நன்றி|வணக்கம்|ಧನ್ಯವಾದಗಳು|ನಮಸ್ಕಾರ)"
    r"[\s,.;!?]*$",
    re.I,
)


_FAREWELL_CUE = re.compile(
    r"\b(?:goodbye|bye|farewell|take\s+care|talk\s+to\s+you\s+later|see\s+you)\b|"
    r"ధన్యవాదాలు|నమస్కారం|సమయం\s+ఇచ్చినందుకు|శుభ\s*దినం|మళ్లీ\s*మాట్లాడుకుందాం|"
    r"धन्यवाद|नमस्ते|नमस्कार|फिर\s*मिलेंगे|आपका\s*दिन\s*शुभ|"
    r"நன்றி|வணக்கம்|இனிதாக\s*அமையட்டும்|போய்\s*வருகிறேன்|"
    r"ಧನ್ಯವಾದಗಳು|ನಮಸ್ಕಾರ|ಶುಭವಾಗಲಿ|ಮತ್ತೆ\s*ಮಾತನಾಡೋಣ|ವಿದಾಯ",
    re.I,
)


def _is_farewell_tail(sentence: str) -> bool:
    """True for a goodbye/thanks sentence, including a polite lead-in tail."""
    from server.call.hangup_judge import agent_spoke_terminal_farewell

    s = (sentence or "").strip()
    if not s:
        return True
    if _FAREWELL_ONLY.match(s):
        return True
    if "?" in s:
        return False
    return bool(
        len(s.split()) <= 12
        and (_FAREWELL_CUE.search(s) or agent_spoke_terminal_farewell(s))
    )


def useful_answer_after_rejected_close(
    text: str, *, language: str | None = None
) -> str | None:
    """Keep the model's actual answer when the server rejects its close.

    The 2026-10-25 audit lost answers because every rejected close was replaced
    by "please go ahead", even when the reply had just stated the price and
    delivery. Only a farewell, an empty reply or a bare filler is discarded.
    """
    from server.call.hangup_judge import agent_spoke_terminal_farewell

    cleaned = _text(text, 2000)
    if not cleaned:
        return None
    if cleaned.casefold().strip(" .!?") == continuation_line_for(language).casefold().strip(" .!?"):
        return None
    parts = re.split(r"(?<=[.!?।])\s+", cleaned)
    while parts and _is_farewell_tail(parts[-1]):
        parts.pop()
    answer = " ".join(parts).strip()
    if not answer:
        return None
    # A reply that is *only* a farewell is not an answer; an answer followed by
    # one keeps its substance ("...is 4999 rupees. Goodbye.").
    if agent_spoke_terminal_farewell(answer) and len(answer.split()) <= 8:
        return None
    from server.services.voice_pipeline_limits import (
        clamp_live_spoken_reply,
        is_incomplete_spoken_crumb,
    )

    answer = clamp_live_spoken_reply(answer)
    if not answer or is_incomplete_spoken_crumb(answer):
        return None
    bare = answer.casefold().strip(" .!?")
    if bare in {"of course", "please go ahead", "go ahead", "okay", "sure", "thanks"}:
        return None
    return answer


def opt_out_evidence(text: str) -> bool:
    """True only when the words themselves ask to stop being contacted.

    "Call cut చేయకండి" and "call करने के लिए नहीं कह रहा" contain a call word
    next to a negative but ask the opposite; they are not opt-outs.
    """
    from server.call.caller_intent import caller_revoked_callback, is_negated_end

    raw = text or ""
    if is_negated_end(raw) or caller_revoked_callback(raw):
        return False
    return bool(_OPT_OUT_EVIDENCE.search(raw.casefold()))


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
