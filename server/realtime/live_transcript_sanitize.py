"""Drop Gemini Live monologue / placeholder text from PSTN transcripts."""
from __future__ import annotations

import re

_UNDERSCORE_ONLY = re.compile(r"^_+\s*$")
_INTERNAL_MONOLOGUE = re.compile(
    r"(?:"
    r"conversation has already been completed|"
    r"session has concluded|"
    r"nothing further to discuss|"
    r"i(?:'ve| have) already ended the call|"
    r"i will now end the call|"
    r"the user provided|"
    r"the user explicitly stated|"
    r"per the instructions|"
    r"call the end_call tool|"
    r"must accept the firm refusal|"
    r"i have confirmed the callback|"
    r"goal is complete"
    r")",
    re.I,
)
_REASONING_LINE = re.compile(
    r"^\s*(?:the user |i have confirmed|i will now|this conversation )",
    re.I | re.M,
)
_MARKDOWN_GARBAGE = re.compile(
    r"\*\*|^---\s*$|living merchandising|\*\d+\.\s",
    re.I | re.M,
)


def sanitize_live_assistant_transcript(text: str) -> str:
    """Return spoken line for ledger/transcript; empty when internal-only."""
    raw = (text or "").strip()
    if not raw or _UNDERSCORE_ONLY.match(raw):
        return ""
    if _INTERNAL_MONOLOGUE.search(raw):
        return ""
    if _MARKDOWN_GARBAGE.search(raw):
        return ""
    if _REASONING_LINE.search(raw) and ("\n" in raw or len(raw) > 120):
        return ""
    if re.search(r"\b(?:end_call|firm_refusal|should_end)\b", raw, re.I) and re.search(
        r"\b(?:per the instructions|explicitly stated|terminate the conversation)\b",
        raw,
        re.I,
    ):
        return ""
    from server.call.hangup_judge import is_generic_inbound_greeting

    if is_generic_inbound_greeting(raw):
        return ""
    return raw
