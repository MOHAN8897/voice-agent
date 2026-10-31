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
# U+0900-U+0D7F spans Devanagari, Bengali, Gurmukhi, Gujarati, Tamil, Telugu, Kannada and Malayalam.
_NAME = re.compile(
    r"\b(?:my name is|this is|i am|i'm|name(?:'s| is)|నా పేరు|పేరు|"
    r"मेरा नाम|नाम है|माझं नाव|माझे नाव|என் பெயர்|என் பேர்|ನನ್ನ ಹೆಸರು|എന്റെ പേര്|"
    r"আমার নাম|મારું નામ|ਮੇਰਾ ਨਾਮ)\s+([A-Za-z\u0900-\u0D7F][\w\u0900-\u0D7F.'\-]{1,40})",
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
        "private",
        "secret",
        "confidential",
        "unknown",
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


# Only "my name is X" in any language, never "this is" / "I am" ("I am busy").
_EXPLICIT_NAME = re.compile(
    r"(?:\bmy name is|నా పేరు|मेरा नाम|माझं नाव|माझे नाव|என் பெயர்|என் பேர்|ನನ್ನ ಹೆಸರು|എന്റെ പേര്|"
    r"আমার নাম|મારું નામ|ਮੇਰਾ ਨਾਮ)\s+([A-Za-z][A-Za-z.'\-]{1,40}(?:\s+[A-Z][A-Za-z.'\-]{1,40})?)",
    re.I,
)


def extract_explicit_name(text: str) -> str | None:
    """A Latin-script name after "my name is" (STT spells names in Latin inside Indic speech).

    Safe without a semantic check: a refusal ("నా పేరు చెప్పను") is not Latin script,
    and "my name is not ..." fails the usable-name check.
    """
    from server.call.memory_guard import slot_value_error

    m = _EXPLICIT_NAME.search(text or "")
    if not m:
        return None
    name = m.group(1).strip(" .,!?")
    return name[:80] if slot_value_error("caller_name", name) is None else None


# Numbers that are a price, a time, a date, a duration or a phone, not an order count.
_NOT_A_COUNT = re.compile(
    r"(?:₹|rs\.?|inr|rupees?|రూపాయ|रुपये|रुपए|ரூபாய்|ರೂಪಾಯಿ|രൂപ|টাকা|রুপি|રૂપિયા|ਰੁਪਏ)\s*\d[\d,]*|"
    r"\d[\d,]*\s*(?:rs\b|rupees?|రూపాయ|रुपये|रुपए|ரூபாய்|ರೂಪಾಯಿ|രൂപ|টাকা|રૂપિયા|ਰੁਪਏ|%|percent|"
    r"am\b|pm\b|o'?clock|baje|బజే|గంట|घंटे|बजे|மணி|ಗಂಟೆ|മണി|वाजता|টায়|টা বাজে|વાગ્યે|ਵਜੇ|"
    r"mins?\b|minutes?|seconds?|hours?|hrs?\b|days?\b|weeks?|months?|years?|"
    r"నిమిష|రోజు|రోజుల|వారం|నెల|సంవత్సర|మంది వయస్సు|"
    r"मिनट|दिन|हफ्ते|महीने|साल|நிமிட|நாள்|வாரம்|மாதம்|வருட|ನಿಮಿಷ|ದಿನ|ವಾರ|ತಿಂಗಳು|ವರ್ಷ|"
    r"മിനിറ്റ്|ദിവസ|ആഴ്ച|മാസ|വർഷ|मिनिट|दिवस|आठवड|महिन|वर्ष|মিনিট|দিন|সপ্তাহ|মাস|বছর|"
    r"મિનિટ|દિવસ|અઠવાડિય|મહિન|વર્ષ|ਮਿੰਟ|ਦਿਨ|ਹਫ਼ਤ|ਮਹੀਨ|ਸਾਲ|st\b|nd\b|rd\b|th\b)|"
    r"\d{1,2}[:.]\d{2}|\d{5,}",
    re.I,
)
# The caller wants or orders something, so the number says how many.
_WANTS = re.compile(
    r"\b(?:need|want|order|buy|take|book|require)\b|"
    r"కావాలి|కావాలండి|కావాలంట|తీసుకుంటా|ఆర్డర్|"
    r"चाहिए|चाहिये|लेना|लूंगा|लूँगा|लेंगे|ऑर्डर|खरीद|"
    r"வேணும்|வேண்டும்|ஆர்டர்|வாங்க|ಬೇಕು|ಆರ್ಡರ್|ತಗೋತೀನಿ|വേണം|ഓർഡർ|വാങ്ങ|"
    r"हवे|हवंय|हवेत|पाहिजे|লাগবে|চাই|অর্ডার|જોઈએ|ઓર્ડર|ਚਾਹੀਦ|ਆਰਡਰ",
    re.I,
)


def extract_requested_quantity(text: str, *, quantity_asked: bool = False) -> str | None:
    """The count in "I need 100 cards" / "ఒక 500 కావాలి", never a price, time, duration or phone.

    A bare number counts only right after the agent asked how many.
    """
    raw = text or ""
    if not (quantity_asked or _WANTS.search(raw)):
        return None
    cleaned = _NOT_A_COUNT.sub(" ", raw)
    numbers = re.findall(r"(?<![\d.,])\d[\d,]*(?![\d.])", cleaned)
    if not numbers:
        return None
    try:
        # The caller's latest number wins ("100 కాదు, 500").
        value = int(numbers[-1].replace(",", ""))
    except ValueError:
        return None
    return str(value) if value > 0 else None


def caller_detail_memory_operations(user_text: str, *, quantity_asked: bool = False) -> list[dict[str, Any]]:
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
    contact = bool(ops)
    quantity = extract_requested_quantity(user_text, quantity_asked=quantity_asked)
    if quantity:
        ops.append({"op": "set_fact", "key": "quantity", "value": quantity})
    if contact:
        ops.append(
            {
                "op": "append_context",
                "value": "Caller provided contact details in this call.",
            }
        )
    return ops
