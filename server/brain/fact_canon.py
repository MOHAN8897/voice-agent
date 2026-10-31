"""Remove superseded facts from operational instructions.

A brief that corrects an old price ("3999 is WRONG, the fee is 4999") must
compile to the current value only. Leaving the obsolete number in the brain
gives the model two facts and a contradiction to resolve on every call.
"""
from __future__ import annotations

import re

_OLD_CLAUSE = re.compile(
    r"(?:,?\s*(?:and|but|also)?\s*)?(?:an?\s+)?old\s+"
    r"(?:[\w-]+\s+){0,2}?(?:note|notes|fee|fees|price|prices|rate|rates|amount|amounts|quote|quotes)\b"
    r"[^.!?।;]*?(?:wrong|incorrect|obsolete|discarded?|invalid|outdated|"
    r"not\s+valid|no\s+longer)[^,.;!?।]*"
    r"|(?:,?\s*)(?:please\s+)?discard\s+(?:the\s+|any\s+)?old\s+"
    r"(?:fee|price|rate|quote|note)s?[^,.;!?।]*"
    r"|\b(?:please\s+)?(?:do\s+not|don'?t|never)\s+use\s+"
    r"(?:the\s+)?old\s+[^.!?।;]*[.!?।]?",
    re.I,
)
_MARKER = re.compile(
    r"\bold\s+(?:[\w-]+\s+){0,2}?(?:note|notes|fee|fees|price|prices|rate|rates|amount|amounts|quote|quotes)\b"
    r"|\bdiscard\s+(?:the\s+)?old\b",
    re.I,
)
# Generated scripts are already translated when they are compiled, so the
# English-only marker above cannot see a corrected fact in an Indic script.
# A sentence that names an old source, calls a number wrong, and carries the
# obsolete number is historical provenance, not an operational fact.
_LOCALIZED_OLD = r"(?:పాత|पुरान[ाीे]|பழைய|ಹಳೆಯ)"
_LOCALIZED_WRONG = (
    r"(?:తప్పు|తప్పైన|ग[़]?लत|தவறு|தவறானது|ತಪ್ಪು|ತಪ್ಪಾಗಿದೆ)"
)
_SUPERSEDED_LOCALIZED = re.compile(
    rf"(?=.*\d)(?=.*{_LOCALIZED_OLD})(?=.*{_LOCALIZED_WRONG}).+",
    re.I,
)
_LOCALIZED_OLD_ONLY = re.compile(_LOCALIZED_OLD, re.I)


def _words(text: str) -> int:
    return len(re.findall(r"\w", text or "", re.UNICODE))


def canonicalize_superseded_facts(text: str) -> str:
    """Drop corrected/obsolete fact phrases while keeping the rest of the sentence."""
    raw = (text or "").strip()
    if not raw or not (_MARKER.search(raw) or _LOCALIZED_OLD_ONLY.search(raw)):
        return raw
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?।])\s+", raw):
        if _SUPERSEDED_LOCALIZED.search(sentence):
            continue
        if not _MARKER.search(sentence):
            kept.append(sentence)
            continue
        cleaned = _OLD_CLAUSE.sub("", sentence)
        cleaned = re.sub(r"\s+([.!?।,;])", r"\1", cleaned)
        cleaned = re.sub(r",\s*,", ",", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;\n\t")
        cleaned = re.sub(r"^(?:please\s+)?discard\s+it\s*[,;:]?\s*", "", cleaned, flags=re.IGNORECASE)
        if re.fullmatch(r"-{2,}\s*[^-]{1,60}?\s*-{2,}", cleaned):
            kept.append(cleaned)
            continue
        if _words(cleaned) < 4:
            continue
        if cleaned[-1] not in ".!?।":
            cleaned += "."
        kept.append(cleaned)
    return " ".join(kept)
