"""Realtime live LLM constants and helpers."""
from __future__ import annotations

from typing import Any

from server.services.voice_pipeline_limits import LIVE_MAX_OUTPUT_TOKENS as _LIVE_MAX_OUTPUT_TOKENS
from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE

DEFAULT_REALTIME_MODEL = "gpt-realtime-2.1-mini"
DEFAULT_HTTP_LLM_MODEL = "gpt-5.6-luna"
LIVE_MAX_OUTPUT_TOKENS = _LIVE_MAX_OUTPUT_TOKENS
# Audio E2E bills output as audio tokens (~dozens per second of speech). The text
# live cap (240) truncates greetings mid-word. OpenAI default for audio is 4096.
REALTIME_VOICE_MAX_OUTPUT_TOKENS = 4096
CANCEL_DRAIN_TIMEOUT_SEC = 0.4
# Hard ceiling for a single Realtime turn collect loop (network hang / rate limit).
REALTIME_TURN_TIMEOUT_SEC = 18.0
REALTIME_PCM_RATE = 24000
DEFAULT_REALTIME_VOICE = "marin"
DEFAULT_REALTIME_TURN_DETECTION = "semantic_vad"

REALTIME_MODEL_IDS: tuple[str, ...] = (
    "gpt-realtime-2.1-mini",
    "gpt-realtime-2.1",
    "gpt-realtime-2",
)

DEFAULT_GEMINI_LIVE_MODEL = "gemini-3.8-live"
GEMINI_LIVE_MODEL_IDS: tuple[str, ...] = (
    "gemini-3.8-live",
    "gemini-2.5-flash-native-audio-latest",
)

GEMINI_LIVE_VOICES: tuple[str, ...] = (
    "Puck",
    "Charon",
    "Kore",
    "Fenrir",
    "Aoede",
    "Leda",
    "Orus",
    "Zephyr",
)
_GEMINI_VOICE_BY_LOWER = {name.lower(): name for name in GEMINI_LIVE_VOICES}
REALTIME_VOICES: tuple[str, ...] = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
)

REALTIME_TURN_DETECTION: tuple[str, ...] = ("semantic_vad", "server_vad")
REALTIME_VAD_EAGERNESS: tuple[str, ...] = ("low", "medium", "high", "auto")
REALTIME_NOISE_REDUCTION: tuple[str, ...] = ("near_field", "far_field", "off")
DEFAULT_REALTIME_VAD_EAGERNESS = "high"
DEFAULT_REALTIME_NOISE_REDUCTION = "far_field"
DEFAULT_REALTIME_SPEED = 1.0
DEFAULT_REALTIME_SILENCE_MS = 250
PIPELINE_MODES: tuple[str, ...] = ("classic", "realtime_text", "realtime_voice")

END_CALL_REASONS: tuple[str, ...] = (
    "goodbye",
    "firm_refusal",
    "goal_complete",
    "abuse",
    "out_of_scope",
)

END_CALL_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "end_call",
    "description": (
        "Judge the call and hang up when the caller has confirmed they are done. "
        "Call this in the SAME turn as your spoken farewell. "
        "Use firm_refusal when they are not interested; goodbye when they say bye/hang up/"
        "cut the call/that's-all/don't-call/'can you call this call' (ASR for cut)/I'm sleeping/"
        "I have to go. Use goal_complete only after they confirmed a callback/visit and any "
        "name/phone they asked you to record is captured — never on okay/thanks alone. "
        "For 'call me tomorrow' or 'record my name and phone', ask only a still-missing field, "
        "then confirm and close. Never invent a manager. "
        "The server waits after farewell and disconnects only if they stay silent; "
        "if they speak again, stay on the line. "
        "Do NOT call for information questions, uncertainty, busy without an end/callback, "
        "or a bare okay/thanks."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "should_end": {"type": "boolean"},
            "reason": {"type": "string", "enum": list(END_CALL_REASONS)},
            "farewell": {"type": "string"},
        },
        "required": ["should_end", "reason", "farewell"],
    },
}

LANGUAGE_OUTPUT_RULES = """
OUTPUT LANGUAGE RULES
- Reply only in the agent's configured call language. Do not switch languages mid-call.
- If the caller uses another language, politely ask them to repeat in the agent language.
- Never insert Tamil, Korean, Chinese, Japanese, Cyrillic, or other unrelated scripts.
""".strip()


def is_gemini_live_voice_model(model: str | None) -> bool:
    slug = str(model or "").strip().lower()
    if not slug:
        return False
    if slug in GEMINI_LIVE_MODEL_IDS:
        return True
    if slug.endswith("-live") and slug.startswith("gemini-"):
        return True
    return "native-audio" in slug and slug.startswith("gemini-")


def is_realtime_llm_model(model: str | None) -> bool:
    slug = str(model or "").strip().lower()
    if not slug:
        return False
    if slug in REALTIME_MODEL_IDS:
        return True
    return slug.startswith("gpt-realtime") and "whisper" not in slug and "translate" not in slug


def http_openai_model(settings=None) -> str:
    """Model for compile, post-call, and ephemeral HTTP brain — never a Realtime slug."""
    if settings is None:
        from server.config.env import get_settings

        settings = get_settings()
    model = (settings.post_call_llm_model or DEFAULT_HTTP_LLM_MODEL).strip()
    if is_realtime_llm_model(model):
        return DEFAULT_HTTP_LLM_MODEL
    return model or DEFAULT_HTTP_LLM_MODEL


def live_gemini_model(model: str | None, settings=None) -> str:
    if is_gemini_live_voice_model(model):
        return str(model).strip()
    if settings is None:
        from server.config.env import get_settings

        settings = get_settings()
    preferred = (settings.gemini_model or "").strip()
    if is_gemini_live_voice_model(preferred):
        return preferred
    return DEFAULT_GEMINI_LIVE_MODEL


def live_openai_model(model: str | None, settings=None) -> str:
    """Live-call OpenAI Realtime model (text PSTN or audio E2E)."""
    if is_realtime_llm_model(model):
        return str(model).strip()
    if settings is None:
        from server.config.env import get_settings

        settings = get_settings()
    preferred = (settings.openai_model or "").strip()
    if is_realtime_llm_model(preferred):
        return preferred
    return DEFAULT_REALTIME_MODEL


def realtime_voice_llm_provider(
    stack_override: dict[str, Any] | None,
    runtime_model: str | None = None,
    *,
    settings=None,
) -> tuple[str, str]:
    """Return (provider, model) for speech-to-speech PSTN."""
    if isinstance(stack_override, dict):
        llm = stack_override.get("llm")
        if isinstance(llm, dict):
            provider = str(llm.get("provider") or "").strip().lower()
            model = str(llm.get("model") or "").strip()
            if provider == "gemini" and is_gemini_live_voice_model(model):
                return "gemini", live_gemini_model(model, settings)
            if is_gemini_live_voice_model(model):
                return "gemini", live_gemini_model(model, settings)
            if provider == "openai" and is_realtime_llm_model(model):
                return "openai", live_openai_model(model, settings)
            if is_realtime_llm_model(model):
                return "openai", live_openai_model(model, settings)
        raw = str(stack_override.get("model") or "").strip()
        if is_gemini_live_voice_model(raw):
            return "gemini", live_gemini_model(raw, settings)
        if is_realtime_llm_model(raw):
            return "openai", live_openai_model(raw, settings)
    if is_gemini_live_voice_model(runtime_model):
        return "gemini", live_gemini_model(runtime_model, settings)
    if is_realtime_llm_model(runtime_model):
        return "openai", live_openai_model(runtime_model, settings)
    return "openai", live_openai_model(runtime_model, settings)


def resolve_realtime_voice_model(
    stack_override: dict[str, Any] | None = None,
    runtime_model: str | None = None,
) -> str:
    """Prefer the dial-stack Realtime slug, then Fine-tune runtime, then mini."""
    _, model = realtime_voice_llm_provider(stack_override, runtime_model)
    return model


def _stack_voice_flow(stack_override: dict[str, Any] | None) -> str:
    if not isinstance(stack_override, dict):
        return ""
    return str(stack_override.get("voice_flow") or "").strip().lower()


def pipeline_mode(*, settings=None, stack_override: dict[str, Any] | None = None) -> str:
    override = None
    if isinstance(stack_override, dict):
        override = str(stack_override.get("pipeline") or "").strip().lower()
        flow = _stack_voice_flow(stack_override)
        if not override and flow in ("realtime_e2e", "realtime_voice"):
            override = "realtime_voice"
    if override in PIPELINE_MODES:
        return override
    if settings is None:
        from server.config.env import get_settings

        settings = get_settings()
    mode = str(getattr(settings, "voice_pipeline_mode", "realtime_text") or "realtime_text").strip().lower()
    return mode if mode in ("classic", "realtime_text") else "realtime_text"


def uses_realtime_text(*, settings=None, stack_override: dict[str, Any] | None = None) -> bool:
    return pipeline_mode(settings=settings, stack_override=stack_override) == "realtime_text"


def uses_realtime_voice(*, settings=None, stack_override: dict[str, Any] | None = None) -> bool:
    return pipeline_mode(settings=settings, stack_override=stack_override) == "realtime_voice"


def normalize_realtime_voice(voice: str | None) -> str:
    slug = str(voice or "").strip()
    gemini = _GEMINI_VOICE_BY_LOWER.get(slug.lower())
    if gemini:
        return gemini
    lower = slug.lower()
    return lower if lower in REALTIME_VOICES else DEFAULT_REALTIME_VOICE


def normalize_realtime_turn_detection(kind: str | None) -> str:
    slug = str(kind or "").strip().lower()
    return slug if slug in REALTIME_TURN_DETECTION else DEFAULT_REALTIME_TURN_DETECTION


def normalize_realtime_vad_eagerness(kind: str | None) -> str:
    slug = str(kind or "").strip().lower()
    return slug if slug in REALTIME_VAD_EAGERNESS else DEFAULT_REALTIME_VAD_EAGERNESS


def normalize_realtime_noise_reduction(kind: str | None) -> str:
    slug = str(kind or "").strip().lower()
    return slug if slug in REALTIME_NOISE_REDUCTION else DEFAULT_REALTIME_NOISE_REDUCTION


def normalize_realtime_speed(value: Any) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_REALTIME_SPEED
    return max(0.25, min(1.5, round(speed, 2)))


def normalize_realtime_silence_ms(value: Any) -> int:
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return DEFAULT_REALTIME_SILENCE_MS
    return max(200, min(2000, ms))


def resolve_realtime_voice_max_output_tokens(raw: Any) -> int:
    """Audio responses need thousands of tokens; ignore the text-turn 240 cap."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return REALTIME_VOICE_MAX_OUTPUT_TOKENS
    if n < 1024:
        return REALTIME_VOICE_MAX_OUTPUT_TOKENS
    return min(n, 16384)


def realtime_voice_config(stack_override: dict[str, Any] | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {}
    if isinstance(stack_override, dict):
        raw = stack_override.get("realtime_voice")
        if isinstance(raw, dict):
            block = raw
    return {
        "voice": normalize_realtime_voice(block.get("voice")),
        "turn_detection": normalize_realtime_turn_detection(block.get("turn_detection")),
        "vad_eagerness": normalize_realtime_vad_eagerness(block.get("vad_eagerness")),
        "noise_reduction": normalize_realtime_noise_reduction(
            block.get("noise_reduction")
            or (stack_override.get("noise_reduction") if isinstance(stack_override, dict) else None)
        ),
        "speed": normalize_realtime_speed(block.get("speed")),
        "silence_ms": normalize_realtime_silence_ms(block.get("silence_ms")),
    }


def coerce_live_llm_selection(
    provider: str,
    model: str,
    *,
    settings=None,
    stack_override: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Live voice E2E may use OpenAI Realtime or Gemini Live; text PSTN stays OpenAI Realtime."""
    if uses_realtime_voice(settings=settings, stack_override=stack_override):
        prov, slug = realtime_voice_llm_provider(stack_override, model, settings=settings)
        if prov == "gemini":
            return prov, slug
        return "openai", slug
    if uses_realtime_text(settings=settings, stack_override=stack_override):
        return "openai", live_openai_model(model, settings)
    if str(provider or "").strip().lower() == "gemini":
        return "openai", http_openai_model(settings)
    return provider, model
