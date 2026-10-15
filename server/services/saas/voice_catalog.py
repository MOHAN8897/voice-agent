"""Subscriber-facing phone voice list (OpenAI Realtime + Gemini Live mappings)."""
from __future__ import annotations

from typing import Any

from server.config.env import get_settings
from server.realtime.models import GEMINI_LIVE_LIBRARY_VOICES, GEMINI_LIVE_VOICES, REALTIME_VOICES

# OpenAI Realtime GA voices — display metadata for SaaS UI.
_OPENAI_VOICE_META: dict[str, dict[str, str]] = {
    "marin": {"label": "Marin", "gender": "female", "tone": "Warm & conversational", "category": "support", "useCase": "Customer Care, Hospitality & Appointments"},
    "cedar": {"label": "Cedar", "gender": "male", "tone": "Calm & steady", "category": "operations", "useCase": "Field Operations, Home Services & Dispatch"},
    "alloy": {"label": "Alloy", "gender": "neutral", "tone": "Balanced & empathetic", "category": "support", "useCase": "Healthcare Clinics, Patient Triage & Intake"},
    "ash": {"label": "Ash", "gender": "male", "tone": "Grounded & thoughtful", "category": "operations", "useCase": "Technical Operations, Diagnostics & Advisory"},
    "ballad": {"label": "Ballad", "gender": "male", "tone": "Proactive & direct", "category": "sales", "useCase": "Automotive Sales, Direct Outreach & Inquiries"},
    "coral": {"label": "Coral", "gender": "female", "tone": "Friendly & trustworthy", "category": "support", "useCase": "Banking Verification, Fintech & Onboarding"},
    "echo": {"label": "Echo", "gender": "male", "tone": "Bright & confident", "category": "sales", "useCase": "Sales Inquiries, Real Estate & Outbound"},
    "sage": {"label": "Sage", "gender": "female", "tone": "Crisp & professional", "category": "operations", "useCase": "Enterprise IT, B2B SaaS & Tech Helpdesk"},
    "shimmer": {"label": "Shimmer", "gender": "female", "tone": "Encouraging & pleasant", "category": "support", "useCase": "Academic Admissions, Travel & Concierge"},
    "verse": {"label": "Verse", "gender": "male", "tone": "Dynamic & adaptable", "category": "sales", "useCase": "Retail Ordering, Commercial Outreach & Reservations"},
}

_GEMINI_BY_OPENAI: dict[str, str] = {
    "marin": "Aoede",
    "cedar": "Charon",
    "alloy": "Kore",
    "ash": "Orus",
    "ballad": "Puck",
    "coral": "Aoede",
    "echo": "Fenrir",
    "sage": "Kore",
    "shimmer": "Leda",
    "verse": "Puck",
}

_GEMINI_VOICE_META: dict[str, dict[str, str]] = {
    "Zephyr": {"label": "Zephyr", "gender": "female", "tone": "Bright", "category": "support", "useCase": "Reception & Booking"},
    "Kore": {"label": "Kore", "gender": "female", "tone": "Firm", "category": "operations", "useCase": "Executive & Systems Advisory"},
    "Orus": {"label": "Orus", "gender": "male", "tone": "Firm", "category": "operations", "useCase": "Operations & Technical Dispatch"},
    "Autonoe": {"label": "Autonoe", "tone": "Bright", "category": "support", "useCase": "Reception & Booking"},
    "Umbriel": {"label": "Umbriel", "tone": "Easy-going", "category": "support", "useCase": "Customer Care & Hospitality"},
    "Erinome": {"label": "Erinome", "tone": "Clear", "category": "operations", "useCase": "Instructions & Helpdesk"},
    "Laomedeia": {"label": "Laomedeia", "tone": "Upbeat", "category": "sales", "useCase": "Sales & Reservations"},
    "Schedar": {"label": "Schedar", "tone": "Even", "category": "operations", "useCase": "Operations & Scheduling"},
    "Achird": {"label": "Achird", "tone": "Friendly", "category": "support", "useCase": "Customer Care & Hospitality"},
    "Sadachbia": {"label": "Sadachbia", "tone": "Lively", "category": "sales", "useCase": "Sales & Reservations"},
    "Puck": {"label": "Puck", "gender": "male", "tone": "Upbeat", "category": "sales", "useCase": "Sales & Retail"},
    "Fenrir": {"label": "Fenrir", "gender": "male", "tone": "Excitable", "category": "sales", "useCase": "High Energy Outreach"},
    "Aoede": {"label": "Aoede", "gender": "female", "tone": "Breezy", "category": "support", "useCase": "Customer Care & Hospitality"},
    "Enceladus": {"label": "Enceladus", "tone": "Breathy", "category": "support", "useCase": "Warm Customer Care"},
    "Algieba": {"label": "Algieba", "tone": "Smooth", "category": "operations", "useCase": "Professional Services"},
    "Algenib": {"label": "Algenib", "tone": "Gravelly", "category": "sales", "useCase": "Sales & Outreach"},
    "Achernar": {"label": "Achernar", "tone": "Soft", "category": "support", "useCase": "Customer Care & Hospitality"},
    "Gacrux": {"label": "Gacrux", "tone": "Mature", "category": "operations", "useCase": "Professional Services"},
    "Zubenelgenubi": {"label": "Zubenelgenubi", "tone": "Casual", "category": "support", "useCase": "Customer Care & Hospitality"},
    "Sadaltager": {"label": "Sadaltager", "tone": "Lively", "category": "sales", "useCase": "Sales & Reservations"},
    "Charon": {"label": "Charon", "gender": "male", "tone": "Informative", "category": "operations", "useCase": "Technical & Diagnostics"},
    "Leda": {"label": "Leda", "gender": "female", "tone": "Youthful", "category": "support", "useCase": "Friendly Support & Admissions"},
    "Callirrhoe": {"label": "Callirrhoe", "tone": "Easy-going", "category": "support", "useCase": "Customer Care & Hospitality"},
    "Iapetus": {"label": "Iapetus", "tone": "Clear", "category": "operations", "useCase": "Instructions & Helpdesk"},
    "Despina": {"label": "Despina", "tone": "Smooth", "category": "support", "useCase": "Professional Customer Care"},
    "Rasalgethi": {"label": "Rasalgethi", "tone": "Informative", "category": "operations", "useCase": "Technical & Diagnostics"},
    "Alnilam": {"label": "Alnilam", "tone": "Firm", "category": "operations", "useCase": "Executive & Systems Advisory"},
    "Pulcherrima": {"label": "Pulcherrima", "tone": "Forward", "category": "sales", "useCase": "Sales & Outreach"},
    "Vindemiatrix": {"label": "Vindemiatrix", "tone": "Gentle", "category": "support", "useCase": "Customer Care & Hospitality"},
    "Sulafat": {"label": "Sulafat", "tone": "Warm", "category": "support", "useCase": "Customer Care & Hospitality"},
}

# These entries come from Google's language-filtered Gemini Voice Library.
# Hindi voices are regional dialects, so no Hindi voice is marked as a default.
_GEMINI_INDIC_VOICE_META: tuple[dict[str, Any], ...] = (
    {
        "id": "hi-in-csagent-1", "label": "Haryanvi Hindi · Female", "languageCode": "hi-IN",
        "accent": "Haryanvi Hindi", "gender": "female", "tone": "Confident & clear",
        "useCase": "Regional Hindi dialect · Customer support", "category": "support",
        "sampleText": "नमस्ते। मैं आपकी कैसे मदद कर सकती हूँ?", "description": "Customer support voice from Haryana.",
    },
    {
        "id": "hi-in-csagent-2", "label": "Awadhi Hindi · Male", "languageCode": "hi-IN",
        "accent": "Awadhi Hindi", "gender": "male", "tone": "Warm & helpful",
        "useCase": "Regional Hindi dialect · Customer support", "category": "support",
        "sampleText": "नमस्ते। मैं आपकी कैसे मदद कर सकता हूँ?", "description": "Awadhi Hindi voice from Uttar Pradesh.",
    },
    {
        "id": "ta-in-csagent-2", "label": "Tamil · Male", "languageCode": "ta-IN",
        "accent": "Tamil", "gender": "male", "tone": "Natural & clear",
        "useCase": "Native Tamil accent · Customer support", "category": "support",
        "sampleText": "வணக்கம். உங்களுக்கு எப்படி உதவலாம்?", "description": "Native Tamil customer support voice.",
    },
    {
        "id": "ta-in-csagent-3", "label": "Tamil · Female", "languageCode": "ta-IN",
        "accent": "Tamil", "gender": "female", "tone": "Conversational & warm",
        "useCase": "Native Tamil accent · Customer support", "category": "support",
        "sampleText": "வணக்கம். உங்களுக்கு எப்படி உதவலாம்?", "description": "Native Tamil customer support voice.",
        "defaultForLanguage": True,
    },
    {
        "id": "te-in-csagent-4", "label": "Telugu · Male", "languageCode": "te-IN",
        "accent": "Telugu", "gender": "male", "tone": "Steady & soothing",
        "useCase": "Native Telugu accent · Customer support", "category": "support",
        "sampleText": "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?", "description": "Native Telugu customer support voice.",
    },
    {
        "id": "te-in-csagent-5", "label": "Telugu · Female", "languageCode": "te-IN",
        "accent": "Telugu", "gender": "female", "tone": "Warm & engaging",
        "useCase": "Native Telugu accent · Customer support", "category": "support",
        "sampleText": "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?", "description": "Native Telugu customer support voice.",
        "defaultForLanguage": True,
    },
    {
        "id": "en-in-csagent-1", "label": "Indian English · Male", "languageCode": "en-IN",
        "accent": "Indian English", "gender": "male", "tone": "Natural & clear",
        "useCase": "Indian English accent · Customer support", "category": "support",
        "sampleText": "Hello. How can I help you today?", "description": "Indian English customer support voice.",
    },
    {
        "id": "en-in-csagent-3", "label": "Indian English · Female", "languageCode": "en-IN",
        "accent": "Indian English", "gender": "female", "tone": "Confident & clear",
        "useCase": "Indian English accent · Customer support", "category": "support",
        "sampleText": "Hello. How can I help you today?", "description": "Indian English customer support voice.",
        "defaultForLanguage": True,
    },
)


def phone_voice_catalog() -> list[dict[str, Any]]:
    settings = get_settings()
    gemini_on = bool(settings.gemini_api_key or getattr(settings, "enable_gemini", False))
    rows: list[dict[str, str]] = []
    for vid in REALTIME_VOICES:
        meta = _OPENAI_VOICE_META.get(vid, {})
        gemini_name = _GEMINI_BY_OPENAI.get(vid, "Aoede")
        gmeta = _GEMINI_VOICE_META.get(gemini_name, {})
        rows.append(
            {
                "id": vid,
                "label": meta.get("label") or vid.title(),
                "gender": meta.get("gender") or "neutral",
                "tone": meta.get("tone") or "",
                "category": meta.get("category") or "support",
                "useCase": meta.get("useCase") or "",
                "provider": "openai",
                "providerLabel": "OpenAI (default phone AI)",
                "geminiVoice": gemini_name,
                "geminiLabel": gmeta.get("label") or gemini_name,
                "geminiGender": gmeta.get("gender") or "",
            }
        )
    if gemini_on:
        for gid in GEMINI_LIVE_VOICES:
            gmeta = _GEMINI_VOICE_META[gid]
            rows.append(
                {
                    "id": gid.lower(),
                    "label": gmeta.get("label") or gid,
                    "gender": gmeta.get("gender") or "neutral",
                    "tone": gmeta.get("tone") or "",
                    "category": gmeta.get("category") or "support",
                    "useCase": gmeta.get("useCase") or "",
                    "provider": "gemini",
                    "providerLabel": "Gemini Live",
                    "geminiVoice": gid,
                    "geminiLabel": gmeta.get("label") or gid,
                    "geminiGender": gmeta.get("gender") or "",
                }
            )
        for meta in _GEMINI_INDIC_VOICE_META:
            gid = str(meta["id"])
            if gid not in GEMINI_LIVE_LIBRARY_VOICES:
                continue
            rows.append(
                {
                    **meta,
                    "provider": "gemini",
                    "providerLabel": "Gemini Live · Indic",
                    "geminiVoice": gid,
                    "geminiLabel": meta["label"],
                    "geminiGender": meta["gender"],
                }
            )
    return rows
