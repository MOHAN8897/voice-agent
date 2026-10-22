"""Drop unrelated scripts from live Realtime text (Tamil/Korean/CJK, etc.)."""
from __future__ import annotations

import re

# Core shared ranges: Latin, ASCII, common punctuation, Indic digits/currency (Rupee \u20B9).
_BASE_ALLOWED = (
    (0x0000, 0x024F),  # Basic Latin, Latin-1, Extended-A/B
    (0x2000, 0x206F),  # General Punctuation
    (0x20A0, 0x20CF),  # Currency Symbols (including ₹ INR)
    (0xFE00, 0xFE0F),  # Variation Selectors
)

# Specific script Unicode blocks:
_SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "te": ((0x0C00, 0x0C7F),),  # Telugu
    "hi": ((0x0900, 0x097F),),  # Devanagari (Hindi, Marathi)
    "mr": ((0x0900, 0x097F),),  # Devanagari
    "ta": ((0x0B80, 0x0BFF),),  # Tamil
    "kn": ((0x0C80, 0x0CFF),),  # Kannada
    "ml": ((0x0D00, 0x0D7F),),  # Malayalam
    "gu": ((0x0A80, 0x0AFF),),  # Gujarati
    "bn": ((0x0980, 0x09FF),),  # Bengali / Assamese
    "pa": ((0x0A00, 0x0A7F),),  # Gurmukhi / Punjabi
    "or": ((0x0B00, 0x0B7F),),  # Odia
}

# Non-Indic contaminants that Gemini Live or other LLMs hallucinate:
_GLOBAL_UNEXPECTED = (
    (0x0400, 0x04FF),  # Cyrillic
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x3040, 0x30FF),  # Hiragana / Katakana
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xAC00, 0xD7AF),  # Hangul Syllables
)

_WS = re.compile(r"[ \t]{2,}")


def _in_ranges(cp: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


def _get_allowed_ranges_for_lang(language: str) -> tuple[tuple[int, int], ...]:
    prefix = (language or "te-IN").strip()[:2].lower()
    allowed = list(_BASE_ALLOWED)
    if prefix in _SCRIPT_RANGES:
        allowed.extend(_SCRIPT_RANGES[prefix])
    else:
        # Default fallback (e.g. te-IN or general Indic): include Telugu + Devanagari
        allowed.extend(_SCRIPT_RANGES["te"])
        if prefix != "te":
            allowed.extend(_SCRIPT_RANGES["hi"])
    return tuple(allowed)


def enforce_output_language_script(text: str, language: str = "te-IN") -> str:
    """Strip script leakage on live calls (e.g. Hindi Devanagari on te-IN Tanglish)."""
    if not (text or "").strip():
        return text
    lang = (language or "te-IN").strip().lower()
    if lang.startswith("te"):
        cleaned = re.sub(r"[\u0900-\u097F]+", " ", text)
        cleaned = _WS.sub(" ", cleaned).strip()
        return cleaned if cleaned else text
    if lang.startswith("hi"):
        cleaned = re.sub(r"[\u0C00-\u0C7F]+", " ", text)
        cleaned = _WS.sub(" ", cleaned).strip()
        return cleaned if cleaned else text
    return text


def filter_unrelated_scripts(
    text: str,
    language: str = "te-IN",
    *,
    streaming: bool = False,
) -> str:
    """Remove unexpected scripts; keep configured product language scripts.

    Streaming deltas must not be stripped (that glues tokens) and must never
    fall back to the original contaminant-only chunk.
    """
    if not text:
        return text
    if text.isascii():
        return text

    allowed_ranges = _get_allowed_ranges_for_lang(language)
    lang_prefix = (language or "te-IN").strip()[:2].lower()

    # Additional unexpected script filter: if te-IN, Tamil/Gujarati/etc. are contaminants.
    # If ta-IN, Telugu/Hangul/CJK are contaminants.
    extra_unexpected: list[tuple[int, int]] = []
    for code, rng in _SCRIPT_RANGES.items():
        if code != lang_prefix and not (lang_prefix not in _SCRIPT_RANGES and code in ("te", "hi")):
            extra_unexpected.extend(rng)
    unexpected = _GLOBAL_UNEXPECTED + tuple(extra_unexpected)

    kept: list[str] = []
    dropped = False
    for ch in text:
        cp = ord(ch)
        if _in_ranges(cp, unexpected) or not _in_ranges(cp, allowed_ranges):
            if not ch.isspace():
                dropped = True
            continue
        kept.append(ch)
    if not dropped:
        return text
    cleaned = _WS.sub(" ", "".join(kept))
    if streaming:
        return cleaned if cleaned.strip() else ""
    return cleaned.strip()
