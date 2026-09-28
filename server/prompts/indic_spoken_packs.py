"""Dedicated spoken-language packs for Indic locales (telecaller audit B8)."""
from __future__ import annotations

from server.prompts.agent_voice_rules import (
    LANGUAGE_LOCK,
    LANGUAGE_MISMATCH_FALLBACK,
    SOFT_BREVITY,
    UNCLEAR_FALLBACK,
)


def _pack(locale: str, intro: str) -> str:
    lock = LANGUAGE_LOCK[locale]
    mismatch = LANGUAGE_MISMATCH_FALLBACK[locale]
    unclear = UNCLEAR_FALLBACK[locale]
    return f"""--- SPOKEN LANGUAGE ({locale}) ---
You are on a live phone call. {intro}
{lock}
If the caller speaks another language you cannot follow: use the language-mismatch line once, then wait.
Language mismatch (once): `{mismatch}`
{SOFT_BREVITY}
Unclear audio: `{unclear}`
Never switch your spoken language to match the caller. Use request_language_callback for handoff — do not reply in their language.
"""


INDIC_SPOKEN_PACKS: dict[str, str] = {
    "ta-IN": _pack(
        "ta-IN",
        "Speak natural Tamil (Tamil script) with everyday English business loanwords where normal.",
    ),
    "kn-IN": _pack(
        "kn-IN",
        "Speak natural Kannada (Kannada script) with everyday English business loanwords where normal.",
    ),
    "ml-IN": _pack(
        "ml-IN",
        "Speak natural Malayalam (Malayalam script) with everyday English business loanwords where normal.",
    ),
    "mr-IN": _pack(
        "mr-IN",
        "Speak natural Marathi (Devanagari) with everyday English business loanwords where normal.",
    ),
    "bn-IN": _pack(
        "bn-IN",
        "Speak natural Bengali (Bengali script) with everyday English business loanwords where normal.",
    ),
    "gu-IN": _pack(
        "gu-IN",
        "Speak natural Gujarati (Gujarati script) with everyday English business loanwords where normal.",
    ),
    "pa-IN": _pack(
        "pa-IN",
        "Speak natural Punjabi (Gurmukhi) with everyday English business loanwords where normal.",
    ),
}
