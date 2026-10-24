"""Subscriber-facing phone voice list (OpenAI Realtime + Gemini Live mappings)."""
from __future__ import annotations

from typing import Any

from server.realtime.models import REALTIME_VOICES

# OpenAI Realtime GA voices — display metadata for SaaS UI.
_OPENAI_VOICE_META: dict[str, dict[str, str]] = {
    "marin": {"label": "Marin", "gender": "female", "tone": "Warm & conversational", "category": "support", "useCase": "Customer Care, Hospitality & Appointments"},
    "cedar": {"label": "Cedar", "gender": "male", "tone": "Calm & steady", "category": "operations", "useCase": "Field Operations, Home Services & Dispatch"},
    "alloy": {"label": "Alloy", "gender": "female", "tone": "Balanced & empathetic", "category": "support", "useCase": "Healthcare Clinics, Patient Triage & Intake"},
    "ash": {"label": "Ash", "gender": "male", "tone": "Grounded & thoughtful", "category": "operations", "useCase": "Technical Operations, Diagnostics & Advisory"},
    "ballad": {"label": "Ballad", "gender": "male", "tone": "Proactive & direct", "category": "sales", "useCase": "Automotive Sales, Direct Outreach & Inquiries"},
    "coral": {"label": "Coral", "gender": "female", "tone": "Friendly & trustworthy", "category": "support", "useCase": "Banking Verification, Fintech & Onboarding"},
    "echo": {"label": "Echo", "gender": "male", "tone": "Bright & confident", "category": "sales", "useCase": "Sales Inquiries, Real Estate & Outbound"},
    "sage": {"label": "Sage", "gender": "female", "tone": "Crisp & professional", "category": "operations", "useCase": "Enterprise IT, B2B SaaS & Tech Helpdesk"},
    "shimmer": {"label": "Shimmer", "gender": "female", "tone": "Encouraging & pleasant", "category": "support", "useCase": "Academic Admissions, Travel & Concierge"},
    "verse": {"label": "Verse", "gender": "male", "tone": "Dynamic & adaptable", "category": "sales", "useCase": "Retail Ordering, Commercial Outreach & Reservations"},
}

def phone_voice_catalog() -> list[dict[str, Any]]:
    """Published provider voices only; callers must still select a model."""
    from server.providers.voice_inventory import inventory, voices_for_model

    rows: list[dict[str, Any]] = []
    for voice in REALTIME_VOICES:
        rows.append({"id": voice, "providerVoiceId": voice, "label": voice.title(), "provider": "openai", **_OPENAI_VOICE_META.get(voice, {})})
    source = inventory()
    for provider in ("sarvam", "gnani", "gemini", "cartesia"):
        if provider == "gemini":
            models = source.get(provider, {}).get("ttsModels", [])
        elif provider == "cartesia":
            from server.config.constants import constants
            models = list(constants.CARTESIA_TTS_MODELS)
        else:
            models = list(source.get(provider, {}).get("models", {}))
        seen: set[str] = set()
        for model in models:
            for row in voices_for_model(provider, model):
                voice = row["providerVoiceId"]
                if voice in seen:
                    continue
                seen.add(voice)
                rows.append({**row, "id": voice.lower() if provider == "gemini" else voice,
                    "provider": provider, "model": model,
                    **({"geminiVoice": voice} if provider == "gemini" else {})})
    return rows
