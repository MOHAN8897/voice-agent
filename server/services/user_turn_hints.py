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


# --- the caller asks the agent to be quick ------------------------------------------------
# "Please hurry, answer fast" (call 029B33, Telugu) got an "I didn't catch that" line.
# Latin entries match whole words (also romanised Indic); native-script entries are stems,
# so inflected forms (త్వరగానే, जल्दी से, சீக்கிரமா) still match.
_HURRY_LATIN = (
    "hurry", "quick", "quickly", "quicker", "fast", "faster", "be brief", "briefly", "in short",
    "to the point", "get to the point", "speed up", "short ga", "fast ga", "twaraga", "tondaraga",
    "jaldi", "jldi", "fatafat", "seekiram", "sikiram", "vegama", "bega", "begane", "vegam",
    "lavkar", "patkan", "taratari", "chheti",
)
_HURRY_NATIVE = (
    # Telugu
    "త్వరగా", "తొందరగా", "ఫాస్ట్", "స్పీడ్", "షార్ట్", "క్లుప్తంగా", "హర్రీ",
    # Hindi / Marathi (Devanagari)
    "जल्दी", "फटाफट", "फास्ट", "शॉर्ट में", "संक्षेप", "लवकर", "पटकन", "थोडक्यात",
    # Tamil
    "சீக்கிரம்", "சீக்கிரமா", "வேகமா", "ஃபாஸ்ட்", "சுருக்கமா",
    # Kannada
    "ಬೇಗ", "ಫಾಸ್ಟ್", "ಚುಟುಕಾಗಿ",
    # Malayalam
    "വേഗം", "പെട്ടെന്ന്", "ചുരുക്കി", "ഫാസ്റ്റ്",
    # Bengali
    "তাড়াতাড়ি", "জলদি", "ফাস্ট", "সংক্ষেপে",
    # Gujarati
    "જલ્દી", "ઝડપથી", "ફાસ્ટ", "ટૂંકમાં",
    # Punjabi
    "ਜਲਦੀ", "ਛੇਤੀ", "ਫਾਸਟ",
)


def asks_to_hurry(transcript: str | None) -> bool:
    """The caller asks the agent to be quicker or shorter, in any supported language."""
    import re

    text = (transcript or "").strip()
    if not text:
        return False
    lower = text.casefold()
    if any(stem in text for stem in _HURRY_NATIVE):
        return True
    return any(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lower) for word in _HURRY_LATIN)


def build_hurry_turn_hint(*, just_asked: bool) -> str:
    if just_asked:
        return (
            "[Internal — the caller just asked you to be quick. Give what they need now in one or two "
            "short sentences: no greeting, no recap, no apology speech. Do not ask them to repeat or "
            "slow down, and do not ask what details they want when the conversation already shows it. "
            "Keep every later reply this short.]"
        )
    return "[Internal — the caller asked earlier for quick answers: keep this reply to one or two short sentences.]"
