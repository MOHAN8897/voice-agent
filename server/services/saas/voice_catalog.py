"""Subscriber-facing phone voice list (OpenAI Realtime + Gemini Live mappings)."""
from __future__ import annotations

from server.config.env import get_settings
from server.realtime.models import REALTIME_VOICES

# OpenAI Realtime GA voices — display metadata for SaaS UI.
_OPENAI_VOICE_META: dict[str, dict[str, str]] = {
    "marin": {"label": "Marin", "gender": "female", "tone": "Warm & clear"},
    "cedar": {"label": "Cedar", "gender": "male", "tone": "Calm & steady"},
    "alloy": {"label": "Alloy", "gender": "neutral", "tone": "Balanced"},
    "ash": {"label": "Ash", "gender": "male", "tone": "Soft"},
    "ballad": {"label": "Ballad", "gender": "male", "tone": "Expressive"},
    "coral": {"label": "Coral", "gender": "female", "tone": "Friendly"},
    "echo": {"label": "Echo", "gender": "male", "tone": "Bright"},
    "sage": {"label": "Sage", "gender": "female", "tone": "Professional"},
    "shimmer": {"label": "Shimmer", "gender": "female", "tone": "Light"},
    "verse": {"label": "Verse", "gender": "male", "tone": "Crisp"},
}

_GEMINI_BY_OPENAI: dict[str, str] = {
    "ash": "Aoede",
    "marin": "Puck",
    "cedar": "Charon",
    "alloy": "Kore",
    "echo": "Fenrir",
    "shimmer": "Leda",
    "sage": "Orus",
    "ballad": "Zephyr",
    "coral": "Aoede",
    "verse": "Puck",
}

_GEMINI_VOICE_META: dict[str, dict[str, str]] = {
    "Puck": {"label": "Puck", "gender": "male", "tone": "Upbeat"},
    "Charon": {"label": "Charon", "gender": "male", "tone": "Informative"},
    "Kore": {"label": "Kore", "gender": "female", "tone": "Firm"},
    "Fenrir": {"label": "Fenrir", "gender": "male", "tone": "Excitable"},
    "Aoede": {"label": "Aoede", "gender": "female", "tone": "Breezy"},
    "Leda": {"label": "Leda", "gender": "female", "tone": "Youthful"},
    "Orus": {"label": "Orus", "gender": "male", "tone": "Firm"},
    "Zephyr": {"label": "Zephyr", "gender": "female", "tone": "Bright"},
}


def phone_voice_catalog() -> list[dict[str, str]]:
    settings = get_settings()
    gemini_on = bool(settings.gemini_api_key or getattr(settings, "enable_gemini", False))
    rows: list[dict[str, str]] = []
    for vid in REALTIME_VOICES:
        meta = _OPENAI_VOICE_META.get(vid, {})
        gemini_name = _GEMINI_BY_OPENAI.get(vid, "Puck")
        gmeta = _GEMINI_VOICE_META.get(gemini_name, {})
        rows.append(
            {
                "id": vid,
                "label": meta.get("label") or vid.title(),
                "gender": meta.get("gender") or "neutral",
                "tone": meta.get("tone") or "",
                "provider": "openai",
                "providerLabel": "OpenAI (default phone AI)",
                "geminiVoice": gemini_name,
                "geminiLabel": gmeta.get("label") or gemini_name,
                "geminiGender": gmeta.get("gender") or "",
            }
        )
    if gemini_on:
        for gid, gmeta in _GEMINI_VOICE_META.items():
            if any(r.get("geminiVoice") == gid for r in rows):
                continue
            rows.append(
                {
                    "id": gid.lower(),
                    "label": gmeta.get("label") or gid,
                    "gender": gmeta.get("gender") or "neutral",
                    "tone": gmeta.get("tone") or "",
                    "provider": "gemini",
                    "providerLabel": "Gemini Live",
                    "geminiVoice": gid,
                    "geminiLabel": gmeta.get("label") or gid,
                    "geminiGender": gmeta.get("gender") or "",
                }
            )
    return rows
