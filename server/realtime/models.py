"""Realtime live LLM constants and helpers."""
from __future__ import annotations

from typing import Any

from server.call.call_end_policy import CLOSING_TOOL_DESCRIPTION
from server.services.voice_pipeline_limits import LIVE_MAX_OUTPUT_TOKENS as _LIVE_MAX_OUTPUT_TOKENS
from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE

DEFAULT_REALTIME_MODEL = "gpt-realtime-2.1-mini"
DEFAULT_HTTP_LLM_MODEL = "gpt-6-luna"
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
DEFAULT_GEMINI_LIVE_VOICE = "Puck"
GEMINI_LIVE_MODEL_IDS: tuple[str, ...] = (
    "gemini-3.8-live",
    "gemini-2.5-flash-native-audio-latest",
)

GEMINI_LIVE_VOICES: tuple[str, ...] = (
    "Zephyr",
    "Kore",
    "Orus",
    "Autonoe",
    "Umbriel",
    "Erinome",
    "Laomedeia",
    "Schedar",
    "Achird",
    "Sadachbia",
    "Puck",
    "Fenrir",
    "Aoede",
    "Enceladus",
    "Algieba",
    "Algenib",
    "Achernar",
    "Gacrux",
    "Zubenelgenubi",
    "Sadaltager",
    "Charon",
    "Leda",
    "Callirrhoe",
    "Iapetus",
    "Despina",
    "Rasalgethi",
    "Alnilam",
    "Pulcherrima",
    "Vindemiatrix",
    "Sulafat",
)
# Curated regional voices from the Gemini Voice Library. These IDs are passed
# directly to Gemini Live; they are intentionally separate from the base voice
# names so callers can distinguish locale-specific voices from multilingual ones.
GEMINI_LIVE_LIBRARY_VOICES: tuple[str, ...] = (
    "hi-in-csagent-1",
    "hi-in-csagent-2",
    "ta-in-csagent-2",
    "ta-in-csagent-3",
    "te-in-csagent-1",
    "te-in-csagent-4",
    "te-in-csagent-5",
    "te-in-csagent-7",
    "te-in-concierge-2",
    "te-in-concierge-7",
    "te-in-techagent-1",
    "en-in-csagent-1",
    "en-in-csagent-3",
)
GEMINI_LIVE_DEFAULT_VOICE_BY_LANGUAGE: dict[str, str] = {
    "te-in": "te-in-csagent-5",
    "hi-in": "hi-in-csagent-1",
    "ta-in": "ta-in-csagent-3",
    "en-in": "en-in-csagent-3",
}
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
DEFAULT_REALTIME_VAD_EAGERNESS = "low"
DEFAULT_REALTIME_NOISE_REDUCTION = "far_field"
DEFAULT_REALTIME_SPEED = 1.0
DEFAULT_REALTIME_SILENCE_MS = 250
PIPELINE_MODES: tuple[str, ...] = ("classic", "realtime_text", "realtime_voice", "composed_voice")

END_CALL_REASONS: tuple[str, ...] = (
    "goodbye",
    "firm_refusal",
    "not_interested",
    "goal_complete",
    "abuse",
    "out_of_scope",
)

END_CALL_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "end_call",
    "description": CLOSING_TOOL_DESCRIPTION,
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "should_end": {"type": "boolean"},
            "reason": {"type": "string", "enum": list(END_CALL_REASONS)},
            "contact_preference": {
                "type": "string",
                "enum": ["none", "end_call", "do_not_call", "callback"],
                "description": (
                    "do_not_call only when the caller asked to stop being contacted; "
                    "end_call when they only want this call to end."
                ),
            },
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


def default_gemini_live_voice(language: str | None = None) -> str:
    """Choose a verified India voice for supported Indian locales, else Puck."""
    lang = str(language or "").strip().replace("_", "-").lower()
    return GEMINI_LIVE_DEFAULT_VOICE_BY_LANGUAGE.get(lang, DEFAULT_GEMINI_LIVE_VOICE)


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
            from server.providers.llm_protocol import native_audio_provider

            if not native_audio_provider(provider, model, "websocket"):
                raise ValueError("The selected native audio provider and model do not match")
            return provider, model
        raw = str(stack_override.get("model") or "").strip()
        if is_gemini_live_voice_model(raw):
            return "gemini", live_gemini_model(raw, settings)
        if is_realtime_llm_model(raw):
            return "openai", live_openai_model(raw, settings)
        if raw:
            raise ValueError("The selected model does not support native audio")
    if is_gemini_live_voice_model(runtime_model):
        return "gemini", live_gemini_model(runtime_model, settings)
    if is_realtime_llm_model(runtime_model):
        return "openai", live_openai_model(runtime_model, settings)
    if runtime_model:
        raise ValueError("The selected model does not support native audio")
    return "gemini", live_gemini_model(runtime_model, settings)


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
    if override:
        raise ValueError("The selected voice pipeline is unsupported")
    if settings is None:
        from server.config.env import get_settings

        settings = get_settings()
    mode = str(getattr(settings, "voice_pipeline_mode", "realtime_text") or "realtime_text").strip().lower()
    if mode not in ("classic", "realtime_text"):
        raise ValueError("The configured voice pipeline requires an explicit approved profile")
    return mode


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
    llm = stack_override.get("llm") if isinstance(stack_override, dict) else None
    model = str(llm.get("model") or "") if isinstance(llm, dict) else ""
    if not model and isinstance(stack_override, dict):
        model = str(stack_override.get("model") or "")
    provider = str(llm.get("provider") or "").strip().lower() if isinstance(llm, dict) else ""
    if provider == "gemini" or is_gemini_live_voice_model(model):
        from server.realtime.providers.gemini_voice import normalize_gemini_live_voice

        voice = normalize_gemini_live_voice(block.get("voice"))
    else:
        voice = normalize_realtime_voice(block.get("voice"))
    return {
        "voice": voice,
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
    """Validate the selected transport without replacing a supplied model."""
    if isinstance(stack_override, dict) and stack_override.get("pipeline") == "composed_voice":
        return provider, model
    if uses_realtime_voice(settings=settings, stack_override=stack_override):
        from server.providers.llm_protocol import native_audio_provider

        if not native_audio_provider(provider, model, "websocket"):
            raise ValueError("The selected native audio provider and model do not match")
        prov, slug = realtime_voice_llm_provider(stack_override, model, settings=settings)
        if (prov, slug) != (provider, model):
            raise ValueError("The selected native audio model does not match the resolved profile")
        return provider, model
    if uses_realtime_text(settings=settings, stack_override=stack_override):
        if provider != "openai" or not is_realtime_llm_model(model):
            raise ValueError("The selected model does not support the realtime text pipeline")
        return provider, model
    return provider, model
