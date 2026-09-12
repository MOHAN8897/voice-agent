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

# OpenAI Realtime GA voices (audio output). Voice is locked after first audio reply.
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
DEFAULT_REALTIME_VAD_EAGERNESS = "medium"
DEFAULT_REALTIME_NOISE_REDUCTION = "far_field"
DEFAULT_REALTIME_SPEED = 1.0
DEFAULT_REALTIME_SILENCE_MS = 500
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
        "Judge the call and hang up when appropriate. Call this in the SAME turn as your "
        "spoken farewell. Use firm_refusal when the caller is not interested; goodbye when "
        "they say bye/don't-call/that's-all; goal_complete when the script objective is done "
        "(details collected + next step set, e.g. team will contact them). "
        "Use goodbye for 'can you cut the call please'. For 'call me later/again/tomorrow', "
        "first ensure callback phone, caller name, and requested day/time are known, asking one "
        "missing detail per turn. Only then use goal_complete after professionally confirming "
        "that our team will call; never invent a manager. Put the complete short closing line "
        "with confirmation, thanks, and goodbye in farewell; the server "
        "speaks it before disconnecting even if you produce only this tool call. "
        "Do NOT call for information questions, uncertainty, or busy without an end/callback request."
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


def resolve_realtime_voice_model(
    stack_override: dict[str, Any] | None = None,
    runtime_model: str | None = None,
) -> str:
    """Prefer the dial-stack Realtime slug, then Fine-tune runtime, then mini."""
    if isinstance(stack_override, dict):
        llm = stack_override.get("llm")
        if isinstance(llm, dict) and is_realtime_llm_model(llm.get("model")):
            return str(llm.get("model")).strip()
        if is_realtime_llm_model(stack_override.get("model")):
            return str(stack_override.get("model")).strip()
    if is_realtime_llm_model(runtime_model):
        return str(runtime_model).strip()
    return live_openai_model(runtime_model)


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
    slug = str(voice or "").strip().lower()
    return slug if slug in REALTIME_VOICES else DEFAULT_REALTIME_VOICE


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
        "noise_reduction": normalize_realtime_noise_reduction(block.get("noise_reduction")),
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
    """Live realtime path is OpenAI Realtime only — never Gemini or HTTP-only slugs."""
    live = uses_realtime_text(settings=settings, stack_override=stack_override) or uses_realtime_voice(
        settings=settings, stack_override=stack_override
    )
    if not live:
        if str(provider or "").strip().lower() == "gemini":
            return "openai", http_openai_model(settings)
        return provider, model
    return "openai", live_openai_model(model, settings)
