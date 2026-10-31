"""Ephemeral per-turn hints for live voice — not archived as caller speech."""
from __future__ import annotations

import time
from typing import Any

from server.services.transcript_gate import effective_word_count

# One long breath / fast monologue — ask once to slow down, then continue naturally.
VERBOSE_USER_WORD_THRESHOLD = 38
INTERRUPTION_WINDOW_SEC = 30.0
INTERRUPTION_NUDGE_COUNT = 3


def note_caller_interruption(ctx: Any) -> None:
    """Count committed speech interruptions, never acknowledgements or raw VAD."""
    now = time.monotonic()
    recent = [t for t in getattr(ctx, "interruption_times", []) if now - t < INTERRUPTION_WINDOW_SEC]
    ctx.interruption_times = [*recent, now][-INTERRUPTION_NUDGE_COUNT:]
    if len(ctx.interruption_times) >= INTERRUPTION_NUDGE_COUNT and not getattr(ctx, "slow_down_nudged", False):
        ctx.interruption_nudge_pending = True


def should_nudge_slow_down(transcript: str) -> bool:
    return effective_word_count(transcript or "") >= VERBOSE_USER_WORD_THRESHOLD


def build_slow_down_turn_hint(language: str, *, slow_down_line: str, interrupted: bool = False, server_owned: bool = False) -> str:
    reason = "several confirmed interruptions" if interrupted else "caller spoke at length in one turn"
    if server_owned:
        return (
            f"[Internal — {reason}. The platform will prepend one localized polite request "
            "to slow down. Do not say or paraphrase that request yourself. Answer the "
            "caller's actual question briefly, without blaming them or demanding silence.]"
        )
    return (
        f"[Internal — {reason}. "
        "Politely ask them once to slow down so you can follow, using this exact line: "
        f"\"{slow_down_line}\" — then address their point briefly. "
        "Give a short answer and let them respond. Do not lecture, blame them, "
        "demand silence or tell them they talk too much.]"
    )
