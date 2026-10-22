"""Subscriber-facing phone voice list (OpenAI Realtime + Gemini Live mappings)."""
from __future__ import annotations

from typing import Any

from server.realtime.models import GEMINI_LIVE_LIBRARY_VOICES, GEMINI_LIVE_VOICES, REALTIME_VOICES

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
    "Zephyr": {"label": "Zephyr", "gender": "female", "accent": "General American", "tone": "Bright", "category": "sales", "useCase": "Advertising & Commerce"},
    "Kore": {"label": "Kore", "gender": "female", "accent": "General American", "tone": "Firm", "category": "operations", "useCase": "News & Podcast"},
    "Orus": {"label": "Orus", "gender": "male", "accent": "General American", "tone": "Firm", "category": "operations", "useCase": "High-Trust Advisor"},
    "Autonoe": {"label": "Autonoe", "gender": "female", "accent": "General American", "tone": "Bright", "category": "sales", "useCase": "Advertising & Commerce"},
    "Umbriel": {"label": "Umbriel", "gender": "male", "accent": "General American", "tone": "Easy-going", "category": "support", "useCase": "Companion & Peer"},
    "Erinome": {"label": "Erinome", "gender": "female", "accent": "General American", "tone": "Clear", "category": "operations", "useCase": "Educational Tutor"},
    "Laomedeia": {"label": "Laomedeia", "gender": "female", "accent": "General American", "tone": "Upbeat", "category": "sales", "useCase": "Advertising & Commerce"},
    "Schedar": {"label": "Schedar", "gender": "male", "accent": "General American", "tone": "Even", "category": "operations", "useCase": "Tech Support"},
    "Achird": {"label": "Achird", "gender": "male", "accent": "General American", "tone": "Friendly", "category": "support", "useCase": "Companion & Peer"},
    "Sadachbia": {"label": "Sadachbia", "gender": "male", "accent": "General American", "tone": "Lively", "category": "operations", "useCase": "News & Podcast"},
    "Puck": {"label": "Puck", "gender": "male", "accent": "General American", "tone": "Upbeat", "category": "sales", "useCase": "Advertising & Commerce"},
    "Fenrir": {"label": "Fenrir", "gender": "male", "accent": "General American", "tone": "Excitable", "category": "sales", "useCase": "Advertising & Commerce"},
    "Aoede": {"label": "Aoede", "gender": "female", "accent": "General American", "tone": "Breezy", "category": "sales", "useCase": "Video Voiceover & Hosting"},
    "Enceladus": {"label": "Enceladus", "gender": "male", "accent": "General American", "tone": "Breathy", "category": "support", "useCase": "Storyteller & Narrator"},
    "Algieba": {"label": "Algieba", "gender": "male", "accent": "General American", "tone": "Smooth", "category": "operations", "useCase": "High-Trust Advisor"},
    "Algenib": {"label": "Algenib", "gender": "male", "accent": "General American", "tone": "Gravelly", "category": "support", "useCase": "Storyteller & Narrator"},
    "Achernar": {"label": "Achernar", "gender": "female", "accent": "General American", "tone": "Soft", "category": "support", "useCase": "Storyteller & Narrator"},
    "Gacrux": {"label": "Gacrux", "gender": "female", "accent": "General American", "tone": "Mature", "category": "operations", "useCase": "High-Trust Advisor"},
    "Zubenelgenubi": {"label": "Zubenelgenubi", "gender": "male", "accent": "General American", "tone": "Casual", "category": "support", "useCase": "Companion & Peer"},
    "Sadaltager": {"label": "Sadaltager", "gender": "male", "accent": "General American", "tone": "Lively", "category": "operations", "useCase": "Educational Tutor"},
    "Charon": {"label": "Charon", "gender": "male", "accent": "General American", "tone": "Informative", "category": "operations", "useCase": "Educational Tutor"},
    "Leda": {"label": "Leda", "gender": "female", "accent": "General American", "tone": "Youthful", "category": "sales", "useCase": "Advertising & Commerce"},
    "Callirrhoe": {"label": "Callirrhoe", "gender": "female", "accent": "General American", "tone": "Easy-going", "category": "support", "useCase": "Companion & Peer"},
    "Iapetus": {"label": "Iapetus", "gender": "male", "accent": "General American", "tone": "Clear", "category": "operations", "useCase": "Tech Support"},
    "Despina": {"label": "Despina", "gender": "female", "accent": "General American", "tone": "Smooth", "category": "operations", "useCase": "Educational Tutor"},
    "Rasalgethi": {"label": "Rasalgethi", "gender": "male", "accent": "General American", "tone": "Informative", "category": "operations", "useCase": "Educational Tutor"},
    "Alnilam": {"label": "Alnilam", "gender": "male", "accent": "General American", "tone": "Firm", "category": "operations", "useCase": "High-Trust Advisor"},
    "Pulcherrima": {"label": "Pulcherrima", "gender": "neutral", "accent": "General American", "tone": "Forward", "category": "support", "useCase": "Customer Support"},
    "Vindemiatrix": {"label": "Vindemiatrix", "gender": "female", "accent": "General American", "tone": "Gentle", "category": "support", "useCase": "Coach & Motivational Guide"},
    "Sulafat": {"label": "Sulafat", "gender": "female", "accent": "General American", "tone": "Warm", "category": "support", "useCase": "Customer Support"},
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
        "id": "te-in-csagent-1", "label": "Telugu Support · Female 1", "languageCode": "te-IN",
        "accent": "Telugu (India)", "gender": "female", "tone": "Steady & warm",
        "useCase": "Customer support agent · low pitch", "category": "support",
        "sampleText": "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?", "description": "Native Telugu customer support voice.",
    },
    {
        "id": "te-in-csagent-4", "label": "Telugu Support · Male", "languageCode": "te-IN",
        "accent": "Telugu (India)", "gender": "male", "tone": "Steady & clear",
        "useCase": "Customer support agent · low pitch", "category": "support",
        "sampleText": "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?", "description": "Native Telugu customer support voice.",
    },
    {
        "id": "te-in-csagent-5", "label": "Telugu Support · Female", "languageCode": "te-IN",
        "accent": "Telugu (India)", "gender": "female", "tone": "Warm & engaging",
        "useCase": "Customer support agent · high pitch", "category": "support",
        "sampleText": "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?", "description": "Native Telugu customer support voice.",
        "defaultForLanguage": True,
    },
    {
        "id": "te-in-csagent-7", "label": "Telugu Support · Neutral", "languageCode": "te-IN",
        "accent": "Telugu (India)", "gender": "neutral", "tone": "Balanced & natural",
        "useCase": "Customer support agent · medium pitch", "category": "support",
        "sampleText": "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?", "description": "Native Telugu customer support voice.",
    },
    {
        "id": "te-in-concierge-2", "label": "Telugu Concierge · Male", "languageCode": "te-IN",
        "accent": "Telugu (India)", "gender": "male", "tone": "Calm & attentive",
        "useCase": "Concierge and executive assistant · low pitch", "category": "support",
        "sampleText": "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?", "description": "Native Telugu concierge voice.",
    },
    {
        "id": "te-in-concierge-7", "label": "Telugu Concierge · Female", "languageCode": "te-IN",
        "accent": "Telugu (India)", "gender": "female", "tone": "Warm & composed",
        "useCase": "Concierge and executive assistant · medium pitch", "category": "support",
        "sampleText": "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?", "description": "Native Telugu concierge voice.",
    },
    {
        "id": "te-in-techagent-1", "label": "Telugu Tech Support · Female", "languageCode": "te-IN",
        "accent": "Telugu (India)", "gender": "female", "tone": "Clear & knowledgeable",
        "useCase": "Technical support and advice · low pitch", "category": "operations",
        "sampleText": "నమస్కారం. మీ సాంకేతిక సమస్యను పరిష్కరించడంలో సహాయం చేస్తాను.",
        "description": "Native Telugu technical support voice.",
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


_CURATED_GEMINI_VOICES: dict[str, dict[str, str]] = {
    "Zephyr": {"label": "Zephyr", "gender": "female", "accent": "General American", "tone": "Bright & clear", "category": "conversational", "useCase": "Conversational Assistant & Inquiries"},
    "Puck": {"label": "Puck", "gender": "male", "accent": "General American", "tone": "Upbeat & conversational", "category": "conversational", "useCase": "Conversational Outreach & Bookings"},
    "Aoede": {"label": "Aoede", "gender": "female", "accent": "General American", "tone": "Breezy & engaging", "category": "conversational", "useCase": "Conversational Host & Dialogues"},
    "Leda": {"label": "Leda", "gender": "female", "accent": "General American", "tone": "Youthful & pleasant", "category": "conversational", "useCase": "Conversational Care & Hospitality"},
    "Kore": {"label": "Kore", "gender": "female", "accent": "General American", "tone": "Firm & authoritative", "category": "promotional", "useCase": "Commercial Promotions & Direct Announcements"},
    "Charon": {"label": "Charon", "gender": "male", "accent": "General American", "tone": "Informative & calm", "category": "promotional", "useCase": "Commercial Broadcasts & Operations"},
    "Fenrir": {"label": "Fenrir", "gender": "male", "accent": "General American", "tone": "Confident & excitable", "category": "promotional", "useCase": "Commercial Outreach & Sales Inquiries"},
    "Sulafat": {"label": "Sulafat", "gender": "female", "accent": "General American", "tone": "Warm & persuasive", "category": "promotional", "useCase": "Commercial Outreach & Customer Promotions"},
    "Pulcherrima": {"label": "Pulcherrima", "gender": "female", "accent": "General American", "tone": "Forward & dynamic", "category": "promotional", "useCase": "Commercial Announcements & Brand Outreach"},
}

_SARVAM_VOICE_META: tuple[dict[str, Any], ...] = (
    {"id": "shubh", "label": "Shubh · Male", "gender": "male", "languageCode": "te-IN", "accent": "Telugu (India)", "tone": "Conversational & crisp", "category": "conversational", "useCase": "Conversational Support & Telugu Queries", "sampleText": "నమస్కారం, నేను మీకు ఎలా సహాయం చేయగలను?"},
    {"id": "priya", "label": "Priya · Female", "gender": "female", "languageCode": "te-IN", "accent": "Telugu (India)", "tone": "Warm & conversational", "category": "conversational", "useCase": "Conversational Care & Appointments", "sampleText": "నమస్కారం, నేను మీకు ఎలా సహాయం చేయగలను?", "defaultForLanguage": True},
    {"id": "pooja", "label": "Pooja · Female", "gender": "female", "languageCode": "te-IN", "accent": "Telugu (India)", "tone": "Gentle & conversational", "category": "conversational", "useCase": "Conversational Intake & Triage", "sampleText": "నమస్కారం, మీ వివరాలను సరిచూసేందుకు సహాయపడతాను."},
    {"id": "simran", "label": "Simran · Female", "gender": "female", "languageCode": "te-IN", "accent": "Telugu (India)", "tone": "Cheerful & welcoming", "category": "conversational", "useCase": "Conversational Reception & Services", "sampleText": "నమస్కారం, స్వాగతం! మీకు ఎలా సహాయపడగలను?"},
    {"id": "neha", "label": "Neha · Female", "gender": "female", "languageCode": "te-IN", "accent": "Telugu (India)", "tone": "Friendly & persuasive", "category": "promotional", "useCase": "Commercial / Promotional & Sales Outreach", "sampleText": "నమస్కారం, మా ఆఫర్ల గురించి మీకు వివరించడానికి సిద్ధంగా ఉన్నాను."},
    {"id": "rahul", "label": "Rahul · Male", "gender": "male", "languageCode": "te-IN", "accent": "Telugu (India)", "tone": "Energetic & dynamic", "category": "promotional", "useCase": "Commercial / Promotional & Direct Booking", "sampleText": "నమస్కారం, మీ అపాయింట్‌మెంట్ బుకింగ్ కోసం నేను సహాయం చేయగలను."},
)


def phone_voice_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for vid in REALTIME_VOICES:
        meta = _OPENAI_VOICE_META.get(vid, {})
        gemini_name = _GEMINI_BY_OPENAI.get(vid, "Aoede")
        gmeta = _GEMINI_VOICE_META.get(gemini_name, {})
        rows.append(
            {
                "id": vid,
                "label": meta.get("label") or vid.title(),
                "gender": meta.get("gender") or "",
                "tone": meta.get("tone") or "",
                "category": meta.get("category") or "support",
                "useCase": meta.get("useCase") or "",
                "provider": "openai",
                "providerLabel": "OpenAI Realtime",
                "geminiVoice": gemini_name,
                "geminiLabel": gmeta.get("label") or gemini_name,
                "geminiGender": gmeta.get("gender") or "",
            }
        )
    for gid, gmeta in _CURATED_GEMINI_VOICES.items():
        rows.append(
            {
                "id": gid.lower(),
                "label": gmeta.get("label") or gid,
                "gender": gmeta.get("gender") or "female",
                "accent": gmeta.get("accent") or "General American",
                "tone": gmeta.get("tone") or "",
                "category": gmeta.get("category") or "conversational",
                "useCase": gmeta.get("useCase") or "",
                "provider": "gemini",
                "providerLabel": "Gemini Live",
                "geminiVoice": gid,
                "geminiLabel": gmeta.get("label") or gid,
                "geminiGender": gmeta.get("gender") or "female",
                "sampleUrl": f"/audio/voxly/samples/{gid.lower()}.wav",
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
                "sampleUrl": f"/audio/voxly/samples/{gid.lower()}.wav",
            }
        )
    for meta in _SARVAM_VOICE_META:
        sid = str(meta["id"])
        rows.append(
            {
                **meta,
                "provider": "sarvam",
                "providerLabel": "Sarvam Bulbul",
                "geminiVoice": sid,
                "geminiLabel": meta["label"],
                "geminiGender": meta["gender"],
                "sampleUrl": f"/audio/voxly/samples/{sid.lower()}.wav",
            }
        )
    return rows
