"""Model capabilities for call-owned prompts and the final speech boundary.

Gnani: https://docs.gnani.ai/api/TTS/tts-audio-tags
Sarvam: https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/best-practices
Gemini: https://ai.google.dev/gemini-api/docs/speech-generation
Gemini and Sarvam intentionally use plain transcripts in this application.
"""
from __future__ import annotations

import re

from server.prompts.spoken_locale_style import SPOKEN_LOCALES

GNANI_V3_TAGS = frozenset({
    "laugh", "giggle", "sigh", "exhales", "sniffles", "yawns", "coughs",
    "clears throat", "whispers", "shouting", "excited", "slow", "pauses",
})
_MARKUP = re.compile(r"</?[A-Za-z][^<>]{0,80}>")
_BRACKET_CUE = re.compile(r"\[(?:laugh(?:s|ing)?|giggle|sigh|whispers?|excited|exhales?|yawns?|coughs?|sniffles|clears throat|pauses?|short pause|slow|shouting)\]", re.IGNORECASE)
_AUDIO_CUE = re.compile(r"</?(?:" + "|".join(re.escape(tag) for tag in GNANI_V3_TAGS) + r")>", re.IGNORECASE)


def strip_inline_audio_cues(text: str) -> str:
    """Remove old speech cues at render time without changing prompt structure."""
    return _BRACKET_CUE.sub("", _AUDIO_CUE.sub("", text))


def supports_inline_audio_tags(provider: str | None, model: str | None) -> bool:
    return str(provider or "").strip().lower() == "gnani" and str(model or "").strip().lower() == "timbre-v3.0"


def sanitize_tts_tags(text: str, *, provider: str | None = None, model: str | None = None) -> str:
    """Never speak markup. Only documented, case-sensitive v3 cues survive."""
    allowed = supports_inline_audio_tags(provider, model)

    def replace(match: re.Match[str]) -> str:
        tag = match.group()[1:-1]
        return f" <{tag}> " if allowed and tag in GNANI_V3_TAGS else " "

    cleaned = _BRACKET_CUE.sub(" ", _MARKUP.sub(replace, text or ""))
    # A truncated generated cue must not be read out as its name.
    cleaned = re.sub(r"<[A-Za-z][^<>]*$", "", cleaned)
    # A trailing cue has no following speech to direct; never send cue-only requests.
    cleaned = re.sub(r"(?:\s*<[a-z ]+>)+\s*([.!?।]?)$", r"\1", cleaned)
    if not re.search(r"\w", _MARKUP.sub("", cleaned)):
        return ""
    return re.sub(r"\s+([,.!?।])", r"\1", re.sub(r"\s{2,}", " ", cleaned)).strip()


def tts_delivery_rules(provider: str | None, model: str | None, locale: str) -> str:
    provider = str(provider or "").strip().lower()
    model = str(model or "").strip().lower()
    head = "[Selected speech delivery]\n"
    if supports_inline_audio_tags(provider, model):
        example = SPOKEN_LOCALES[locale].clarification
        return head + (
            "[Gnani Audio Tags Expressive Guidelines]\n"
            "The admitted speech model is Timbre v3.0. Plain speech is the default; audio tags are optional. "
            "Use at most one tag in a turn, only when it helps: <pauses> for a real thought boundary, "
            "<slow> when the caller needs slower delivery, or <excited> for genuinely positive context. "
            "Put the cue before the phrase it modifies, with whitespace around it, at a clause or sentence boundary. "
            "Tags are case-sensitive, use angle brackets and have no closing tag; a delivery cue lasts until "
            "the next cue or the end of this synthesis input, not across later TTS requests. "
            "Do not send tags alone or at the end of a sentence with no following speech. "
            "Do not add performative laughter, giggles, sighs, coughing, throat-clearing, whispering or shouting "
            "to ordinary business calls. Do not add a pause before every number. Never invent good news or approvals. "
            f"Only if asked to slow down, a {locale} delivery example is: <slow> {example} "
            "This is a style example, not a question you must ask. Tags belong only in spoken_response, "
            "never in facts, memory updates or tool arguments."
        )
    detail = (
        "Gemini TTS receives a plain transcript; voice and delivery metadata control sound. " if provider == "gemini" else
        "Sarvam Bulbul v4 Flash uses native-script mixed text and punctuation; API pace, pitch and loudness control delivery. " if provider == "sarvam" and model == "bulbul:v4-flash" else
        "Sarvam Bulbul v3 uses native-script mixed text and punctuation; API pace and temperature control delivery. " if provider == "sarvam" else
        "Gnani Timbre v2.5 uses plain punctuated text and does not support v3 audio tags. " if provider == "gnani" and model == "timbre-v2.5" else
        "Use the selected voice's plain punctuated speech format. "
    )
    return head + detail + (
        "Write only the words to speak, with commas and sentence punctuation for natural pauses. "
        "No inline audio tags, SSML, bracketed emotions, stage directions or delivery instructions in spoken_response. "
        "Do not copy tags from old examples or history. Keep local words in their native script and English words in Latin script."
    )


def native_audio_delivery_rules() -> str:
    return (
        "[Native audio delivery]\nSpeak warmly at a comfortable conversational pace with natural intonation. "
        "Use the selected locale's everyday register and code-mixing; no announcer voice or forced disfluencies. "
        "Generate speech directly: do not emit or read inline TTS tags, SSML, stage directions or bracketed emotions. "
        "The native voice model handles expression; any separate TTS slots in a stored stack are inactive."
    )
