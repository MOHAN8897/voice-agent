"""Sentence buffering for streaming PSTN TTS (brain deltas → speakable chunks)."""
from __future__ import annotations

import re

from server.services.voice_pipeline_limits import (
    FORCE_FLUSH_AT,
    MIN_CHUNK_CHARS,
)

# End sentence on Latin/Telugu punctuation (not decimal points like 80.5), or newline.
_SENTENCE_END = re.compile(r"(?<=[.!?।])(?!\d)\s*|\n+")


def _last_word_boundary(text: str, max_index: int) -> int:
    slice_ = text[:max_index]
    sp = slice_.rfind(" ")
    return sp if sp > 0 else max_index


def drain_complete_sentences(
    buffer: str,
    *,
    min_chars: int = MIN_CHUNK_CHARS,
    allow_first_fast: bool = False,
) -> tuple[list[str], str]:
    """Return complete sentences from buffer; keep trailing partial text."""
    if not buffer.strip():
        return [], buffer

    complete: list[str] = []
    remainder = buffer
    # Kept for API compatibility. A first chunk now follows the same prosody-safe
    # boundaries as every other chunk: punctuation, a substantial clause, or the
    # force-flush guard. Arbitrary token arrival boundaries are not speech boundaries.
    _ = allow_first_fast

    while remainder.strip():
        parts = _SENTENCE_END.split(remainder, maxsplit=1)
        if len(parts) > 1:
            piece = parts[0].strip()
            if piece and len(piece) >= min_chars:
                complete.append(piece)
            remainder = parts[1]
            continue

        stripped = remainder.strip()
        if len(stripped) >= FORCE_FLUSH_AT:
            # Prefer a word/space boundary so compounds are not sliced mid-token.
            # If there is no space at all, flush the whole buffer (legacy safe path).
            if " " not in stripped[:FORCE_FLUSH_AT]:
                complete.append(stripped)
                remainder = ""
                break
            cut = _last_word_boundary(stripped, FORCE_FLUSH_AT)
            if cut < min_chars:
                complete.append(stripped)
                remainder = ""
                break
            piece = stripped[:cut].strip()
            if piece:
                complete.append(piece)
            remainder = stripped[cut:].lstrip()
            if not remainder:
                break
            continue

        break

    return complete, remainder


def join_speakable_chunks(chunks: list[str]) -> str:
    """One TTS utterance from sentences drained in the same token batch."""
    return " ".join(piece.strip() for piece in chunks if piece and piece.strip())


def resolve_stream_tts_tail(pending: str, full_text: str, *, spoke_from_stream: bool) -> str | None:
    """Return remaining PSTN TTS text after streaming deltas; avoid replaying full_text."""
    tail = pending.strip()
    if tail:
        return tail
    if spoke_from_stream:
        return None
    return (full_text or "").strip() or None


_OPENING_POLICY_HINT = re.compile(
    r"(?:never paste|spoken reply per turn|if you speak first|if the caller already|"
    r"do not dump|pstn/outbound|still identifies? you|canned opening|"
    r"one spoken reply|say that opening once)",
    re.IGNORECASE,
)
_EXAMPLE_OPENING = re.compile(
    r"^(?:example\s+(?:opening|first\s+line)|opening(?:_line(?:_te)?)?)\s*:\s*[\"']?(.+?)[\"']?\s*$",
    re.IGNORECASE,
)
_OPENING_SECTION = re.compile(
    r"(?:^|\n)---\s*OPENING(?:\s+HINT)?\s*---\s*\n(.*?)(?=\n---\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _spoken_opening_candidate(line: str) -> str | None:
    """Return a single speakable greeting line, or None for policy / junk."""
    raw = (line or "").strip().strip("-").strip()
    if not raw or raw.endswith(":"):
        return None
    upper = raw.upper()
    if upper.startswith(
        (
            "VOICE",
            "CONVERSATION",
            "GUARD",
            "SAY THIS",
            "WORK SCOPE",
            "--- ",
            "LIVE CALL",
            "SPEAK NATURAL",
            "INTRODUCE YOURSELF",
        )
    ):
        return None
    m = _EXAMPLE_OPENING.match(raw)
    if m:
        raw = m.group(1).strip().strip('"').strip("'")
    low = raw.lower()
    if low.startswith(("opening_line", "say this", "one spoken", "if you speak", "if the caller")):
        return None
    if _OPENING_POLICY_HINT.search(raw):
        return None
    if len(raw) < 8:
        return None
    # One utterance only — cut at a second question if a bad script stacked beats.
    parts = re.split(r"(?<=[.!?])\s+", raw)
    if len(parts) > 2:
        raw = " ".join(parts[:2]).strip()
    return raw[:280]


def extract_opening_greeting(compiled_brain: str | None, language: str = "te-IN") -> str | None:
    """Best-effort single opening line from compiled brain (intro + offer help only)."""
    if not compiled_brain:
        return _default_greeting(language)
    text = compiled_brain
    quoted = re.search(
        r'opening_line(?:_te)?\s*:\s*"([^"]+)"',
        text,
        flags=re.IGNORECASE,
    )
    if quoted:
        line = _spoken_opening_candidate(quoted.group(1))
        if line:
            return line
    section = _OPENING_SECTION.search(text)
    if section:
        for line in section.group(1).splitlines():
            candidate = _spoken_opening_candidate(line)
            if candidate:
                return candidate
    for header in ("--- OPENING ---", "## OPENING"):
        idx = text.upper().find(header.upper())
        if idx >= 0:
            chunk = text[idx + len(header) : idx + len(header) + 600]
            for line in chunk.splitlines():
                candidate = _spoken_opening_candidate(line)
                if candidate:
                    return candidate
            break
    return _default_greeting(language)


def _default_greeting(language: str) -> str:
    if language.startswith("te"):
        return "నమస్కారం! నేను మీకు సహాయం చేస్తాను. మీకు ఎలా సహాయం కావాలి?"
    if language.startswith("hi"):
        return "Namaste! Main aapki madad ke liye yahan hoon. Main aapki kaise madad karun?"
    return "Hi, thanks for taking my call. How can I help you today?"
