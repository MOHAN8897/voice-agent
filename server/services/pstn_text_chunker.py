"""Sentence buffering for streaming PSTN TTS (brain deltas → speakable chunks)."""
from __future__ import annotations

import re

from server.services.voice_pipeline_limits import (
    CLAUSE_FLUSH_AT,
    FIRST_CHUNK_MIN_CHARS,
    FORCE_FLUSH_AT,
    MIN_CHUNK_CHARS,
)

# End sentence on Latin or Telugu punctuation, or newline.
_SENTENCE_END = re.compile(r"(?<=[.!?।\n])\s*")
_CLAUSE_END = re.compile(r"(?<=[;:])\s*")


def _word_count(text: str) -> int:
    return len((text or "").strip().split())


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
    first_chunk = allow_first_fast

    while remainder.strip():
        parts = _SENTENCE_END.split(remainder, maxsplit=1)
        if len(parts) > 1:
            piece = parts[0].strip()
            if piece and len(piece) >= min_chars:
                complete.append(piece)
                first_chunk = False
            remainder = parts[1]
            continue

        stripped = remainder.strip()
        if len(stripped) >= FORCE_FLUSH_AT:
            complete.append(stripped)
            remainder = ""
            break

        clause_parts = _CLAUSE_END.split(remainder, maxsplit=1)
        if (
            clause_parts
            and len(clause_parts) > 1
            and len(clause_parts[0].strip()) >= min_chars
            and len(stripped) >= CLAUSE_FLUSH_AT
        ):
            complete.append(clause_parts[0].strip())
            first_chunk = False
            remainder = clause_parts[1]
            continue

        if "," in remainder and len(stripped) >= CLAUSE_FLUSH_AT:
            idx = remainder.rfind(",")
            if idx >= min_chars - 1:
                piece = remainder[: idx + 1].strip()
                if piece and len(piece) >= min_chars and _word_count(piece) >= 2:
                    complete.append(piece)
                    first_chunk = False
                    remainder = remainder[idx + 1 :].lstrip()
                    continue

        if first_chunk and len(stripped) >= FIRST_CHUNK_MIN_CHARS:
            boundary = _last_word_boundary(stripped, len(stripped))
            if boundary >= min_chars:
                piece = stripped[:boundary].strip()
                if piece and len(piece) >= min_chars and _word_count(piece) >= 2:
                    complete.append(piece)
                    first_chunk = False
                    remainder = stripped[boundary:].lstrip()
                    continue

        break

    return complete, remainder


def resolve_stream_tts_tail(pending: str, full_text: str, *, spoke_from_stream: bool) -> str | None:
    """Return remaining PSTN TTS text after streaming deltas; avoid replaying full_text."""
    tail = pending.strip()
    if tail:
        return tail
    if spoke_from_stream:
        return None
    return (full_text or "").strip() or None


def extract_opening_greeting(compiled_brain: str | None, language: str = "te-IN") -> str | None:
    """Best-effort opening line from compiled brain OPENING section."""
    if not compiled_brain:
        return _default_greeting(language)
    text = compiled_brain
    quoted = re.search(
        r'opening_line(?:_te)?\s*:\s*"([^"]+)"',
        text,
        flags=re.IGNORECASE,
    )
    if quoted:
        line = quoted.group(1).strip()
        if len(line) >= 8:
            return line[:200]
    for header in ("--- OPENING ---", "OPENING", "## OPENING"):
        idx = text.upper().find(header.upper())
        if idx >= 0:
            chunk = text[idx + len(header) : idx + len(header) + 400]
            for line in chunk.splitlines():
                line = line.strip().strip("-").strip()
                if not line or line.upper().startswith(("VOICE", "CONVERSATION", "GUARD")):
                    continue
                if line.lower().startswith("opening_line"):
                    continue
                if len(line) >= 8 and not line.endswith(":"):
                    return line[:200]
            break
    return _default_greeting(language)


def _default_greeting(language: str) -> str:
    if language.startswith("te"):
        return "నమస్కారం! నేను మీకు ఎలా సహాయం చేయగలను?"
    return "Hello! How can I help you today?"
