"""Sentence buffering for streaming PSTN TTS (brain deltas → speakable chunks)."""
from __future__ import annotations

import re

# End sentence on Latin or Telugu punctuation, or newline.
_SENTENCE_END = re.compile(r"(?<=[.!?।\n])\s*")


def drain_complete_sentences(buffer: str, *, min_chars: int = 12) -> tuple[list[str], str]:
    """Return complete sentences from buffer; keep trailing partial text."""
    if not buffer.strip():
        return [], buffer
    parts = _SENTENCE_END.split(buffer)
    if len(parts) <= 1:
        # Force flush long clauses without punctuation (voice agents use short lines).
        if len(buffer.strip()) >= 72:
            return [buffer.strip()], ""
        return [], buffer
    complete = [p.strip() for p in parts[:-1] if p.strip() and len(p.strip()) >= min_chars]
    remainder = parts[-1]
    return complete, remainder


def extract_opening_greeting(compiled_brain: str | None, language: str = "te-IN") -> str | None:
    """Best-effort opening line from compiled brain OPENING section."""
    if not compiled_brain:
        return _default_greeting(language)
    text = compiled_brain
    for header in ("--- OPENING ---", "OPENING", "## OPENING"):
        idx = text.upper().find(header.upper())
        if idx >= 0:
            chunk = text[idx + len(header) : idx + len(header) + 400]
            for line in chunk.splitlines():
                line = line.strip().strip("-").strip()
                if not line or line.upper().startswith(("VOICE", "CONVERSATION", "GUARD")):
                    continue
                if len(line) >= 8 and not line.endswith(":"):
                    return line[:200]
            break
    return _default_greeting(language)


def _default_greeting(language: str) -> str:
    if language.startswith("te"):
        return "నమస్కారం! నేను మీకు ఎలా సహాయం చేయగలను?"
    return "Hello! How can I help you today?"
