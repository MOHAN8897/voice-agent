"""Transcript echo filter — dual-rail barge vs final drop (mirrors web echo-guard)."""
from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")

# Barge reject while agent is playing (slightly looser so real interrupts still win).
BARGE_ECHO_OVERLAP = 0.55
# Final drop in echo-tail / intro queue (stricter).
FINAL_ECHO_OVERLAP = 0.65
# Near-copy only — barge-committed finals still pass unless almost identical.
BARGE_FINAL_ECHO_OVERLAP = 0.85


def _normalize(text: str) -> str:
    return _WS.sub(" ", _NON_ALNUM.sub(" ", (text or "").lower())).strip()


def echo_overlap_ratio(stt_text: str, assistant_text: str) -> float:
    """Combined unigram + bigram overlap for better echo detection.

    Bag-of-words alone is order-insensitive (issue 4.1) — adding bigram
    sequence matching reduces false positives for short Telugu utterances
    where common words overlap heavily but word order differs.
    """
    user = _normalize(stt_text)
    agent = _normalize(assistant_text)
    if not user or not agent or len(user) < 4:
        return 0.0
    # A short question repeating a place/name is a clarification, not sufficient
    # evidence of acoustic echo. STT supplies punctuation; pitch is unavailable here.
    if stt_text.rstrip().endswith("?") and len(user.split()) <= 2:
        return 0.0
    if user in agent or (agent in user and len(agent) > 8):
        return 1.0
    user_words = [w for w in user.split(" ") if len(w) > 1]
    if len(user_words) < 2:
        return 0.0
    agent_list = [w for w in agent.split(" ") if len(w) > 1]
    agent_words = set(agent_list)
    # Unigram alone is order-blind (false positives on shared vocabulary).
    unigram_overlap = sum(1 for w in user_words if w in agent_words) / len(user_words)
    if len(user_words) < 3 or len(agent_list) < 2:
        return unigram_overlap
    user_bigrams = {f"{user_words[i]} {user_words[i + 1]}" for i in range(len(user_words) - 1)}
    agent_bigrams = {f"{agent_list[i]} {agent_list[i + 1]}" for i in range(len(agent_list) - 1)}
    bigram_overlap = (
        len(user_bigrams & agent_bigrams) / len(user_bigrams) if user_bigrams else 0.0
    )
    # Weight sequence evidence higher so reordered shared words score lower.
    return 0.35 * unigram_overlap + 0.65 * bigram_overlap


def window_assistant_text(assistant_text: str, *, max_chars: int = 420) -> str:
    """Keep last ~N chars / last few sentences for echo compare."""
    text = (assistant_text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def is_likely_echo(
    stt_text: str,
    assistant_text: str,
    *,
    threshold: float = FINAL_ECHO_OVERLAP,
) -> bool:
    ref = window_assistant_text(assistant_text)
    return echo_overlap_ratio(stt_text, ref) >= threshold


def is_barge_echo(stt_text: str, assistant_text: str) -> bool:
    return is_likely_echo(stt_text, assistant_text, threshold=BARGE_ECHO_OVERLAP)


# Listening finals (outside echo tail) — only drop near-copies.
LISTENING_FINAL_ECHO_OVERLAP = 0.80


def is_final_echo(stt_text: str, assistant_text: str, *, in_echo_tail: bool = False) -> bool:
    # Stricter in echo-tail (agent just stopped); looser while fully listening.
    thr = FINAL_ECHO_OVERLAP if in_echo_tail else LISTENING_FINAL_ECHO_OVERLAP
    return is_likely_echo(stt_text, assistant_text, threshold=thr)


def is_barge_final_echo(stt_text: str, assistant_text: str) -> bool:
    """Only drop a post-barge final if it is nearly a copy of agent speech."""
    return is_likely_echo(stt_text, assistant_text, threshold=BARGE_FINAL_ECHO_OVERLAP)
