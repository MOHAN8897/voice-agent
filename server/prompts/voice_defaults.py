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
