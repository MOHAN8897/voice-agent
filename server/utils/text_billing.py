"""Billing character counts — Unicode code points (Sarvam TTS bills per character)."""
from __future__ import annotations


def billing_char_count(text: str | None) -> int:
    """Count Unicode code points. Python len(str) matches Sarvam per-character TTS billing."""
    if not text:
        return 0
    return len(text)
