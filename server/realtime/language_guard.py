"""Drop unrelated scripts from live Realtime text (Tamil/Korean/CJK, etc.)."""
from __future__ import annotations

import re

# Product languages: Latin + Telugu + Devanagari + common punctuation.
_ALLOWED = (
    (0x0000, 0x024F),
    (0x0900, 0x097F),
    (0x0C00, 0x0C7F),
    (0x2000, 0x206F),
    (0x20A0, 0x20CF),
    (0xFE00, 0xFE0F),
)

# Explicit contaminants from the critical audit (Tamil, Hangul) plus nearby scripts.
_UNEXPECTED = (
    (0x0400, 0x04FF),  # Cyrillic
    (0x0A80, 0x0AFF),  # Gujarati
    (0x0B80, 0x0BFF),  # Tamil
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x3040, 0x30FF),  # Hiragana / Katakana
    (0x4E00, 0x9FFF),  # CJK
    (0xAC00, 0xD7AF),  # Hangul syllables
)

_WS = re.compile(r"[ \t]{2,}")


def _in_ranges(cp: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


def filter_unrelated_scripts(
    text: str,
    language: str = "te-IN",
    *,
    streaming: bool = False,
) -> str:
    """Remove unexpected scripts; keep Telugu/Hindi/English product scripts.

    Streaming deltas must not be stripped (that glues tokens) and must never
    fall back to the original contaminant-only chunk.
    """
    del language  # product is te/hi/en; the same allowlist applies
    if not text:
        return text
    if text.isascii():
        return text
    kept: list[str] = []
    dropped = False
    for ch in text:
        cp = ord(ch)
        if _in_ranges(cp, _UNEXPECTED) or not _in_ranges(cp, _ALLOWED):
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
