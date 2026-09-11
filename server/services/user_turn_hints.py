"""Ephemeral per-turn hints for live voice — not archived as caller speech."""
from __future__ import annotations

from server.services.transcript_gate import effective_word_count

# One long breath / fast monologue — ask once to slow down, then continue naturally.
VERBOSE_USER_WORD_THRESHOLD = 38


def should_nudge_slow_down(transcript: str) -> bool:
    return effective_word_count(transcript or "") >= VERBOSE_USER_WORD_THRESHOLD


def build_slow_down_turn_hint(language: str, *, slow_down_line: str) -> str:
    return (
        "[Internal — caller spoke at length in one turn. "
        "Politely ask them once to slow down so you can follow, using this exact line: "
        f"\"{slow_down_line}\" — then address their point briefly. "
        "Do not lecture or tell them they talk too much.]"
    )
