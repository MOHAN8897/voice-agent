"""Gate STT finals before launching a brain turn — mirrors web transcript-gate.ts."""
from __future__ import annotations

import re

# Devanagari + Telugu (same ranges as web).
_INDIC_SCRIPT = re.compile(r"[\u0900-\u097F\u0C00-\u0C7F]")
_WS = re.compile(r"\s+")
_SHORT_RESPONSE = re.compile(
    r"^(?:yes|no|yeah|yep|nope|wait|stop|కాదు|లేదు|లేదండి|అవును|వద్దు|नहीं|हाँ|रुको|ठीक)[.!?,]*$",
    re.I,
)


def effective_word_count(text: str) -> int:
    """Count words; Indic scripts often lack spaces — use char clusters as fallback."""
    trimmed = (text or "").strip()
    if not trimmed:
        return 0
    spaced = len([w for w in _WS.split(trimmed) if w])
    if spaced >= 2:
        return spaced
    if _INDIC_SCRIPT.search(trimmed):
        clusters = len(_WS.sub("", trimmed))
        if clusters >= 6:
            return max(2, (clusters + 3) // 4)
    return spaced


def is_substantive_transcript(
    text: str,
    *,
    after_barge: bool = False,
    from_speech_queue: bool = False,
) -> bool:
    """True when a final is worth a brain turn (blocks junk / echo fragments)."""
    t = (text or "").strip()
    if not t:
        return False
    if _SHORT_RESPONSE.fullmatch(t):
        return True
    words = effective_word_count(t)
    chars = len(_WS.sub("", t))
    if after_barge:
        return words >= 1 and chars >= 3
    if from_speech_queue:
        return words >= 3 or chars >= 12
    return words >= 2 or chars >= 8
