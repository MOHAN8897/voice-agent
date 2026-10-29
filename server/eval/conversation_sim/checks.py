"""Deterministic speech checks applied to every delivered reply (hard fails and warnings)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from server.prompts.tts_delivery_rules import GNANI_V3_TAGS, supports_inline_audio_tags
from server.services.voice_pipeline_limits import LIVE_REPLY_MAX_CHARS as LIVE_REPLY_HARD_CHARS, LIVE_REPLY_SOFT_MAX_CHARS as LIVE_REPLY_SOFT_CHARS

SCRIPTS = {
    "te": (0x0C00, 0x0C7F), "hi": (0x0900, 0x097F), "mr": (0x0900, 0x097F),
    "ta": (0x0B80, 0x0BFF), "kn": (0x0C80, 0x0CFF), "ml": (0x0D00, 0x0D7F),
    "bn": (0x0980, 0x09FF), "gu": (0x0A80, 0x0AFF), "pa": (0x0A00, 0x0A7F),
}
_MARKDOWN = re.compile(r"(\*\*|__|^#{1,6}\s|^\s*[-*•]\s|`|\[[^\]]+\]\([^)]+\)|^\s*\d+\.\s)", re.M)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_JSON = re.compile(r"^\s*[\[{]|\"\w+\"\s*:")
_TAG = re.compile(r"<\s*/?\s*([A-Za-z][^<>]{0,40})>")
_BRACKET_CUE = re.compile(r"\[[a-z ]{3,20}\]", re.I)
_SENTENCE_END = re.compile(r"[.?!।](?=\s|$)")
_ENGLISH_NUMBER_WORDS = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred|thousand|lakh|crore)\b", re.I)


@dataclass
class CheckResult:
    hard: list[str] = field(default_factory=list)
    warn: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.hard


def _letters(text: str) -> list[str]:
    return [c for c in text if c.isalpha()]


def script_profile(text: str) -> dict[str, int]:
    counts: dict[str, int] = {"latin": 0}
    for ch in _letters(text):
        code = ord(ch)
        if ch.isascii():
            counts["latin"] += 1
            continue
        for name, (low, high) in SCRIPTS.items():
            if low <= code <= high:
                counts[name] = counts.get(name, 0) + 1
                break
    # Hindi and Marathi share Devanagari; report it once under the call's name.
    return counts


def check_reply(text: str, *, language: str, tts_provider: str | None, tts_model: str | None) -> CheckResult:
    result = CheckResult()
    reply = (text or "").strip()
    if not reply:
        result.hard.append("empty_reply")
        return result
    if _MARKDOWN.search(reply):
        result.hard.append("markdown")
    if _EMOJI.search(reply):
        result.hard.append("emoji")
    if _JSON.search(reply):
        result.hard.append("json_or_control_text")
    tags = [m.group(1).strip() for m in _TAG.finditer(reply)]
    if tags and not supports_inline_audio_tags(tts_provider, tts_model):
        result.hard.append(f"audio_tag_for_plain_tts:{tags[0]}")
    elif any(tag not in GNANI_V3_TAGS for tag in tags):
        result.hard.append("undocumented_audio_tag")
    if re.search(r"<[a-z ]+>\s*[.!?।]?\s*$", reply):
        result.hard.append("trailing_audio_tag")
    if _BRACKET_CUE.search(reply):
        result.hard.append("bracketed_stage_direction")
    if reply[-1] not in ".?!।":
        result.hard.append("no_terminal_punctuation")
    if len(reply) > LIVE_REPLY_HARD_CHARS:
        result.hard.append(f"over_hard_length:{len(reply)}")
    elif len(reply) > LIVE_REPLY_SOFT_CHARS:
        result.warn.append(f"over_soft_length:{len(reply)}")
    sentences = len(_SENTENCE_END.findall(_TAG.sub("", reply)))
    if sentences > 3:
        result.hard.append(f"too_many_sentences:{sentences}")
    elif sentences == 3:
        result.warn.append("three_sentences")

    base = language.split("-")[0]
    profile = script_profile(reply)
    native = profile.get("hi" if base == "mr" else base, 0) if base in SCRIPTS else 0
    if base == "mr":
        native = profile.get("hi", 0)
    foreign = sum(v for k, v in profile.items() if k not in {"latin", base} and not (base == "mr" and k == "hi")
                  and not (base == "hi" and k == "mr"))
    total = sum(profile.values()) or 1
    if base in SCRIPTS:
        if foreign:
            result.hard.append("wrong_indic_script")
        # English business words in Latin script are allowed; a reply with no
        # native words at all has switched language.
        if native == 0:
            result.hard.append("no_native_script")
        elif native / total < 0.3:
            result.warn.append(f"heavy_english_mixing:{native}/{total}")
    elif base == "en" and total - profile["latin"] > 0:
        result.hard.append("indic_script_in_english_call")
    if any(ch.isdigit() for ch in reply):
        result.warn.append("digits_reach_tts")
    if base in SCRIPTS and _ENGLISH_NUMBER_WORDS.search(reply):
        result.warn.append("english_number_words_in_indic_reply")
    return result
