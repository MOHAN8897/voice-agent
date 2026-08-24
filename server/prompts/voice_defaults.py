"""
Default prompting for Telugu voice agent — applied when session has no saved prompts.
Tuned for spoken Telugu, low latency (short replies), and natural phone-call register.
"""

DEFAULT_RESPONSE_STYLE = "very brief, 1-2 sentences, spoken Telugu"

DEFAULT_BEHAVIOUR_INSTRUCTIONS = """VOICE CALL MODE — Telugu-first assistant
- Reply in natural SPOKEN Telugu (మాట్లాడే టోన్). Mix English words the user uses (plot, flat, budget, loan, Python).
- STRICT: 1–2 short sentences only. Max 25 words unless the user explicitly asks for detail.
- One idea per turn. One question maximum — only when you truly need clarification.
- Start with a tiny backchannel when natural: "అవునా…", "సరే…", "ఓ కదా…"
- Never use bullet lists, markdown, or numbered steps in voice replies.
- Never say you are an AI unless asked. Sound like a helpful Telugu-speaking human on a call.
- If transcript is unclear, ask them to repeat once — do not guess."""

DEFAULT_BUSINESS_INSTRUCTIONS = """You are a helpful Telugu voice assistant for general conversation, learning, and everyday questions.
- Prefer practical, accurate answers grounded in what the user said.
- For property/business topics: ask one clarifying question before long explanations.
- Keep domain facts conservative — if unsure, say so briefly in Telugu."""

# OpenAI model catalog shown in Fine-tune Console (slug → UI label)
OPENAI_MODEL_CATALOG: list[dict[str, str]] = [
    {"id": "gpt-5.5", "label": "GPT-5.5 — Frontier intelligence ⭐⭐⭐⭐⭐", "tier": "flagship"},
    {"id": "gpt-5.4", "label": "GPT-5.4 — Professional workhorse ⭐⭐⭐⭐⭐", "tier": "balanced"},
    {"id": "gpt-5", "label": "GPT-5 — Earlier flagship ⭐⭐⭐⭐", "tier": "legacy"},
    {"id": "gpt-5.6-luna", "label": "GPT-5.6 Luna — Fast & low-cost (voice) 🥉", "tier": "fast"},
]

OPENAI_MODEL_IDS: list[str] = [m["id"] for m in OPENAI_MODEL_CATALOG]

DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"  # lowest latency for live voice; user can switch to gpt-5.5 for max quality

# Per-model recommended brain settings (OpenAI voice-agent guidance, Feb 2026).
# GPT-5 family uses reasoning.effort instead of temperature on the Responses API.
OPENAI_REASONING_EFFORTS = ("none", "low", "medium", "high")

# Curated voice-pipeline bundles — STT/VAD/barge-in/TTS tuned together.
# Users pick a profile; individual sliders are intentionally not exposed in the UI.
DEFAULT_VOICE_PRESET_ID = "natural"

VOICE_PIPELINE_PRESETS: dict[str, dict] = {
    "natural": {
        "name": "Natural (recommended)",
        "hint": "Pace 1.0×, temperature 0.80 — balanced Telugu voice with reliable barge-in.",
        "values": {
            "ttsPace": 1.0,
            "ttsTemperature": 0.80,
            "sttSilenceMs": 500,
            "sttThreshold": 0.30,
            "sttStreamType": "fast",
            "bargeMinWords": 3,
            "bargeRequireVad": True,
            "ttsMinBuffer": 30,
            "ttsMaxChunk": 80,
        },
    },
    "fast": {
        "name": "Fast response",
        "hint": "Slightly quicker speech and tighter endpointing for short back-and-forth.",
        "values": {
            "ttsPace": 1.1,
            "ttsTemperature": 0.60,
            "sttSilenceMs": 400,
            "sttThreshold": 0.30,
            "sttStreamType": "fast",
            "bargeMinWords": 3,
            "bargeRequireVad": True,
            "ttsMinBuffer": 30,
            "ttsMaxChunk": 80,
        },
    },
    "calm": {
        "name": "Calm & clear",
        "hint": "Slower pace, lower TTS variation — good for explanations.",
        "values": {
            "ttsPace": 0.95,
            "ttsTemperature": 0.50,
            "sttSilenceMs": 600,
            "sttThreshold": 0.28,
            "sttStreamType": "fast",
            "bargeMinWords": 3,
            "bargeRequireVad": True,
            "ttsMinBuffer": 30,
            "ttsMaxChunk": 80,
        },
    },
    "expressive": {
        "name": "Expressive",
        "hint": "More vocal variety at pace 1.0× — still safe barge-in defaults.",
        "values": {
            "ttsPace": 1.0,
            "ttsTemperature": 0.90,
            "sttSilenceMs": 500,
            "sttThreshold": 0.30,
            "sttStreamType": "fast",
            "bargeMinWords": 3,
            "bargeRequireVad": True,
            "ttsMinBuffer": 30,
            "ttsMaxChunk": 80,
        },
    },
}

VOICE_PIPELINE_PRESET_IDS: list[str] = list(VOICE_PIPELINE_PRESETS.keys())


def voice_preset_values(preset_id: str | None) -> dict:
    pid = preset_id if preset_id in VOICE_PIPELINE_PRESETS else DEFAULT_VOICE_PRESET_ID
    return dict(VOICE_PIPELINE_PRESETS[pid]["values"])


OPENAI_MODEL_PRESETS: dict[str, dict] = {
    "gpt-5.6-luna": {
        "name": "Voice Fast",
        "openaiReasoningEffort": "none",
        "openaiMaxTokens": 280,
        "brainPromptBudgetTokens": 2500,
        "hint": "Best for live Telugu voice — lowest latency. OpenAI recommends reasoning effort 'none' for voice.",
    },
    "gpt-5.5": {
        "name": "Quality",
        "openaiReasoningEffort": "low",
        "openaiMaxTokens": 360,
        "brainPromptBudgetTokens": 2500,
        "hint": "Highest answer quality with modest latency. Reasoning 'low' balances speed and depth.",
    },
    "gpt-5.4": {
        "name": "Balanced",
        "openaiReasoningEffort": "low",
        "openaiMaxTokens": 320,
        "brainPromptBudgetTokens": 2500,
        "hint": "Professional workhorse — good for longer explanations when latency is less critical.",
    },
    "gpt-5": {
        "name": "Legacy",
        "openaiReasoningEffort": "low",
        "openaiMaxTokens": 300,
        "brainPromptBudgetTokens": 2500,
        "hint": "Earlier GPT-5 flagship. Use gpt-5.6-luna for voice or gpt-5.5 for max quality.",
    },
}
