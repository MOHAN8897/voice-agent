"""Deterministic capture of caller-provided contact details into working memory.

Realtime turns do not emit memory_update ops; without this, spoken phones/names are lost
and the model often invents a "can't record" refusal from the speak-ban.
"""
from __future__ import annotations

import re
from typing import Any

# Indian mobile (optional +91 / 0) or general 10–12 digit runs near contact words.
_PHONE = re.compile(
    r"(?:(?:\+|00)?91[\s\-]*)?(?:0)?([6-9]\d{9})"
    r"|(?<!\d)(\d{10,12})(?!\d)",
)
_PHONE_CUE = re.compile(
    r"\b(?:phone|mobile|number|whatsapp|callback|call\s*me|reach\s*me|"
    r"contact|నంబర్|నెంబర|फोन|नंबर)\b",
    re.I,
)
_EMAIL = re.compile(r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b")
_NAME = re.compile(
    r"\b(?:my name is|this is|i am|i'm|name(?:'s| is)|నా పేరు|పేరు|"
    r"मेरा नाम|नाम है)\s+([A-Za-z\u0C00-\u0C7F\u0900-\u097F][\w\u0C00-\u0C7F\u0900-\u097F.'\-]{1,40})",
    re.I,
)
_JUNK_NAME_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "this",
        "that",
        "it",
        "my",
        "name",
        "recording",
        "looking",
        "calling",
        "interested",
        "busy",
        "here",
        "there",
        "not",
        "i",
        "i'm",
        "im",
        "yeah",
        "yes",
        "ok",
        "okay",
        "hello",
        "hi",
        "hey",
        "hallo",
        "who",
        "sleeping",
        "sleep",
        "guessing",
        "understood",
        "going",
        "done",
        "good",
        "fine",
        "sorry",
        "calling",
        "nothing",
    }
)


def _digits_only(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def extract_caller_phone(text: str) -> str | None:
    raw = text or ""
    if not raw.strip():
        return None
    has_cue = bool(_PHONE_CUE.search(raw))
    # Normalize separators so "+91 88979 08470" still matches.
    compact = re.sub(r"[\s\-().]+", "", raw)
    for m in _PHONE.finditer(compact):
        indian = m.group(1)
        general = m.group(2)
        digits = _digits_only(indian or general or "")
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if len(digits) != 10:
            continue
        # Indian mobiles (6–9…) are trusted; other 10-digit runs need a contact cue.
        if indian or (has_cue and digits[0] in "6789"):
            return digits
    return None


def extract_caller_email(text: str) -> str | None:
    m = _EMAIL.search(text or "")
    if not m:
        return None
    return m.group(1).strip()[:120]


_NAME_GIVE = re.compile(
    r"\b(?:my name is|name(?:'s| is)|నా పేరు|मेरा नाम|नाम है)\b",
    re.I,
)


def is_usable_lead_name(name: str | None) -> bool:
    """True when a captured name is a real person, not STT junk like 'the recording'."""
    cleaned = re.sub(r"[^\w\s'\-]", "", (name or "").strip(), flags=re.UNICODE).strip()
    if len(cleaned) < 2:
        return False
    words = [w for w in re.split(r"\s+", cleaned.lower()) if w]
    if not words:
        return False
    if any(w in _JUNK_NAME_WORDS for w in words):
        return False
    return True


def is_usable_lead_phone(phone: str | None) -> bool:
    """True for a spoken Indian mobile — not a US DID / outbound from-number."""
    raw = (phone or "").strip()
    if not raw:
        return False
    extracted = extract_caller_phone(raw)
    if extracted:
        return True
    digits = _digits_only(raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return len(digits) == 10 and digits[0] in "6789"


def unclear_name_phrase(text: str) -> bool:
    """Caller tried to give a name but STT captured junk (e.g. 'my name is the recording')."""
    if not _NAME_GIVE.search(text or ""):
        return False
    return extract_caller_name(text) is None


def extract_caller_name(text: str) -> str | None:
    m = _NAME.search(text or "")
    if not m:
        return None
    name = (m.group(1) or "").strip(" .,!?")
    if not is_usable_lead_name(name):
        return None
    return name[:80]


def caller_detail_memory_operations(user_text: str) -> list[dict[str, Any]]:
    """Return set_fact ops for details the caller just provided."""
    ops: list[dict[str, Any]] = []
    phone = extract_caller_phone(user_text)
    if phone:
        ops.append({"op": "set_fact", "key": "callback_phone", "value": phone})
        ops.append({"op": "set_fact", "key": "phone", "value": phone})
    email = extract_caller_email(user_text)
    if email:
        ops.append({"op": "set_fact", "key": "caller_email", "value": email})
    name = extract_caller_name(user_text)
    if name:
        ops.append({"op": "set_fact", "key": "caller_name", "value": name})
    if ops:
        ops.append(
            {
                "op": "append_context",
                "value": "Caller shared contact details for the team to follow up.",
            }
        )
    return ops
