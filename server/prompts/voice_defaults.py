"""
Default prompting when a session has no saved prompts.
Language-specific spoken style is selected by default_style_for().
"""

DEFAULT_RESPONSE_STYLES: dict[str, str] = {
    "te-IN": "very brief, 1-2 sentences, spoken Telugu",
    "en-IN": "warm, brief, 1-2 sentences, spoken Indian English like a person on a phone",
    "en-US": "warm, brief, 1-2 sentences, natural spoken English like a person on a phone",
    "hi-IN": "very brief, 1-2 sentences, spoken Hinglish",
}

# Back-compat: factory sessions with no language still Telugu.
DEFAULT_RESPONSE_STYLE = DEFAULT_RESPONSE_STYLES["te-IN"]

_STYLE_ALIASES = {
    "te": "te-IN",
    "te-in": "te-IN",
    "en": "en-IN",
    "en-in": "en-IN",
    "en-us": "en-US",
    "en-gb": "en-US",
    "en-au": "en-US",
    "en-ca": "en-US",
    "english": "en-IN",
    "hi": "hi-IN",
    "hi-in": "hi-IN",
    "hindi": "hi-IN",
}


def canonical_language(language: str | None) -> str:
    raw = (language or "te-IN").strip()
    if raw in DEFAULT_RESPONSE_STYLES:
        return raw
    mapped = _STYLE_ALIASES.get(raw.lower())
    if mapped:
        return mapped
    if raw.lower().startswith("en-us") or raw.lower() in {"en-gb", "en-au", "en-ca", "en-uk"}:
        return "en-US"
    if raw.lower().startswith("en"):
        return "en-IN"
    if raw.lower().startswith("hi"):
        return "hi-IN"
    return "te-IN"


def default_style_for(language: str | None) -> str:
    return DEFAULT_RESPONSE_STYLES[canonical_language(language)]


_LANG_STYLE_MARKERS = {
    "te-IN": ("spoken telugu", "tanglish"),
    "en-IN": ("spoken indian english",),
    "en-US": ("natural spoken english", "us/uk"),
    "hi-IN": ("spoken hinglish",),
}


def style_for_language(style: str | None, language: str | None) -> str:
    """Use an explicit style only when it matches the compile language.

    Fine-tune can resend a previously stored 'spoken Telugu' tag after the
    user switches the picker to English. That must not leak into the brain.
    """
    wanted = default_style_for(language)
    raw = (style or "").strip()
    if not raw:
        return wanted
    lowered = raw.lower()
    target = canonical_language(language)
    for code, markers in _LANG_STYLE_MARKERS.items():
        if code != target and any(m in lowered for m in markers):
            return wanted
    return raw[:100]


DEFAULT_BEHAVIOUR_INSTRUCTIONS = """VOICE CALL MODE — spoken assistant
- You represent this business on a live phone call. For sales/lead work, act as its sales representative — warm, clear, on-brand.
- Reply in the call language with everyday words the caller uses. Sound like a helpful colleague, not a policy page.
- 1–2 short sentences. Ask a question only when you still need a fact — never a qualification checklist.
- Never use bullet lists, markdown, or numbered steps in voice replies.
- Never say you are an AI unless asked. Never say goodbye unless you are actually hanging up.
- If they object, are busy, want WhatsApp, or say don't call — honor that. Do not keep selling.
- Do not claim you sent a message, opened a ticket, made a booking, changed a contact preference, or handed work to a team unless it really happened.
- Keep implementation details private. Never mention tools, connections, system access, capability, or "on this call"; state the honest business outcome.
- If transcript is unclear, ask them to repeat once — do not guess.
- Hesitation (hmm, umm, let me think) is not a cue to pitch or ask another question.
- Sarcasm is not a buying signal. Missing facts: I'll check and get back to you.
- If corrected, own it briefly and use the corrected fact. Harmless small talk gets one natural beat; do not leave the business role.
- Greet with name + company + brief call purpose only on the first turn. A later hello means they are checking you are there — answer briefly and continue; do not restart the pitch.
- Do not repeat the same pitch, facts, or next-step line every turn. When enough is known and next step is agreed, close professionally."""

DEFAULT_BUSINESS_INSTRUCTIONS = """You are a helpful voice assistant for this business.
- Prefer practical, accurate answers grounded in the brief and what the user said.
- Keep domain facts conservative — if unsure, say so briefly in the call language.
- Never invent prices, policies, salaries, capabilities, completed actions, or prior conversations."""

CACHE_FLOOR_PAD = """--- PLATFORM CACHE FLOOR ---
You are a live-call sales representative of this business. Stay inside the brief.
Answer the last customer utterance first. A question must earn its place.
Greet once (name + company + brief purpose). Later hello = availability — continue, do not re-greet.
Never repeat the same pitch or facts every turn. Never invent prices, policies, salaries, availability, or prior conversations.
Honor busy and send-details briefly. For an explicit call-me-later request, acknowledge it and end this call with end_call reason goal_complete.
When enough is known and next step is agreed, close professionally with farewell + end_call.
Do not hang up on maybe, frustration, objections, or silence.
Firm no or don't-call: one farewell and end_call.should_end true.
Hesitation is not a request to pitch. This call has no history from earlier calls.
"""

# OpenAI model catalog shown in Fine-tune Console (slug → UI label)
OPENAI_MODEL_CATALOG: list[dict[str, str]] = [
    {"id": "gpt-realtime-2.1-mini", "label": "GPT Realtime 2.1 Mini — Live voice (text) ⭐", "tier": "realtime"},
    {"id": "gpt-realtime-2.1", "label": "GPT Realtime 2.1 — Live voice (text)", "tier": "realtime"},
    {"id": "gpt-realtime-2", "label": "GPT Realtime 2 — Live voice (text)", "tier": "realtime"},
    {"id": "gpt-5.5", "label": "GPT-5.5 — Frontier intelligence ⭐⭐⭐⭐⭐", "tier": "flagship"},
    {"id": "gpt-5.4", "label": "GPT-5.4 — Professional workhorse ⭐⭐⭐⭐⭐", "tier": "balanced"},
    {"id": "gpt-5", "label": "GPT-5 — Earlier flagship ⭐⭐⭐⭐", "tier": "legacy"},
    {"id": "gpt-5.6-luna", "label": "GPT-5.6 Luna — HTTP compile & post-call 🥉", "tier": "fast"},
]

OPENAI_MODEL_IDS: list[str] = [m["id"] for m in OPENAI_MODEL_CATALOG]

DEFAULT_OPENAI_MODEL = "gpt-realtime-2.1-mini"

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
            "bargeMinWords": 4,
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
    "speakerphone": {
        "name": "Mobile speakerphone",
        "hint": "Phone on loudspeaker — long echo tail, strict barge-in, slower endpointing.",
        "values": {
            "ttsPace": 1.0,
            "ttsTemperature": 0.75,
            "sttSilenceMs": 650,
            "sttThreshold": 0.34,
            "sttStreamType": "fast",
            "bargeMinWords": 5,
            "bargeRequireVad": False,
            "ttsMinBuffer": 30,
            "ttsMaxChunk": 80,
        },
    },
    "mobile_handset": {
        "name": "Mobile handset (direct mic)",
        "hint": "Hold phone to ear — balanced VAD and barge-in; default for mobile browser.",
        "values": {
            "ttsPace": 1.0,
            "ttsTemperature": 0.80,
            "sttSilenceMs": 550,
            "sttThreshold": 0.31,
            "sttStreamType": "fast",
            "bargeMinWords": 4,
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
    "gpt-realtime-2.1-mini": {
        "name": "Realtime Voice",
        "openaiReasoningEffort": "none",
        "openaiMaxTokens": 96,
            "brainPromptBudgetTokens": 6000,
        "hint": "Default live path — persistent OpenAI Realtime text session. STT/TTS stay independently selected.",
    },
    "gpt-realtime-2.1": {
        "name": "Realtime Quality",
        "openaiReasoningEffort": "none",
        "openaiMaxTokens": 96,
            "brainPromptBudgetTokens": 6000,
        "hint": "Full Realtime 2.1 text session. Use mini unless you need the larger live model.",
    },
    "gpt-realtime-2": {
        "name": "Realtime 2",
        "openaiReasoningEffort": "none",
        "openaiMaxTokens": 96,
            "brainPromptBudgetTokens": 6000,
        "hint": "Previous Realtime generation. Prefer gpt-realtime-2.1-mini for live voice.",
    },
    "gpt-5.6-luna": {
        "name": "Voice Fast",
        "openaiReasoningEffort": "none",
        "openaiMaxTokens": 96,
            "brainPromptBudgetTokens": 6000,
        "hint": "Best for live Telugu voice — lowest latency. OpenAI recommends reasoning effort 'none' for voice.",
    },
    "gpt-5.5": {
        "name": "Quality",
        "openaiReasoningEffort": "low",
        "openaiMaxTokens": 360,
            "brainPromptBudgetTokens": 6000,
        "hint": "Highest answer quality with modest latency. Reasoning 'low' balances speed and depth.",
    },
    "gpt-5.4": {
        "name": "Balanced",
        "openaiReasoningEffort": "low",
        "openaiMaxTokens": 320,
            "brainPromptBudgetTokens": 6000,
        "hint": "Professional workhorse — good for longer explanations when latency is less critical.",
    },
    "gpt-5": {
        "name": "Legacy",
        "openaiReasoningEffort": "low",
        "openaiMaxTokens": 300,
            "brainPromptBudgetTokens": 6000,
        "hint": "Earlier GPT-5 flagship. Use gpt-5.6-luna for voice or gpt-5.5 for max quality.",
    },
}
