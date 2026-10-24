"""Model-specific Sarvam voices; official catalog checked 2026-10-24.

Source: https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices
No network request is needed to validate a call.
"""

from __future__ import annotations

def sarvam_speakers_for_model(model: str) -> frozenset[str]:
    from server.providers.voice_inventory import voices_for_model

    return frozenset(row["providerVoiceId"] for row in voices_for_model("sarvam", model))


def validate_sarvam_voice(model: str, speaker: str, language: str | None = None) -> None:
    from server.providers.voice_inventory import validate_voice

    validate_voice("sarvam", model, speaker, language)
