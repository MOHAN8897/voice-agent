"""
Lightweight session summarizer — compacts older turns without an extra API call.
Optional API summarization can be added later; default is local compaction.
"""
from __future__ import annotations

from server.agent.brain_prompt_composer import estimate_tokens

_MAX_SUMMARY_CHARS = 320  # ~80 tokens


def compact_history_summary(history: list[dict]) -> str:
    """Build a short fact-oriented summary from user turns (no API call)."""
    if not history:
        return ""
    user_lines: list[str] = []
    for msg in history:
        if msg.get("role") != "user":
            continue
        text = str(msg.get("content", "")).strip()
        if text:
            user_lines.append(text)
    if not user_lines:
        return ""
    joined = " | ".join(user_lines[-6:])
    if len(joined) > _MAX_SUMMARY_CHARS:
        joined = joined[:_MAX_SUMMARY_CHARS] + "…"
    return f"Earlier in this call the user said: {joined}"


def should_update_summary(turn_count: int, every_n: int) -> bool:
    return every_n > 0 and turn_count > 0 and turn_count % every_n == 0


def summary_token_estimate(summary: str) -> int:
    return estimate_tokens(summary) if summary else 0
