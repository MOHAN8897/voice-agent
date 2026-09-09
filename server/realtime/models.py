"""Realtime text-only live LLM constants and helpers."""
from __future__ import annotations

from typing import Any

from server.services.voice_pipeline_limits import LIVE_MAX_OUTPUT_TOKENS as _LIVE_MAX_OUTPUT_TOKENS
from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE

DEFAULT_REALTIME_MODEL = "gpt-realtime-2.1-mini"
DEFAULT_HTTP_LLM_MODEL = "gpt-5.6-luna"
LIVE_MAX_OUTPUT_TOKENS = _LIVE_MAX_OUTPUT_TOKENS
CANCEL_DRAIN_TIMEOUT_SEC = 0.4
# Hard ceiling for a single Realtime turn collect loop (network hang / rate limit).
REALTIME_TURN_TIMEOUT_SEC = 18.0

REALTIME_MODEL_IDS: tuple[str, ...] = (
    "gpt-realtime-2.1-mini",
    "gpt-realtime-2.1",
    "gpt-realtime-2",
)

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
        "Do NOT call while the caller is interested and still gathering info, or for maybe/"
        "later/busy/soft not-now/frustration/a question."
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
    """Live-call OpenAI model when the realtime text pipeline is active."""
    if is_realtime_llm_model(model):
        return str(model).strip()
    if settings is None:
        from server.config.env import get_settings

        settings = get_settings()
    preferred = (settings.openai_model or "").strip()
    if is_realtime_llm_model(preferred):
        return preferred
    return DEFAULT_REALTIME_MODEL


def pipeline_mode(*, settings=None, stack_override: dict[str, Any] | None = None) -> str:
    override = None
    if isinstance(stack_override, dict):
        override = str(stack_override.get("pipeline") or "").strip().lower()
    if override in ("classic", "realtime_text"):
        return override
    if settings is None:
        from server.config.env import get_settings

        settings = get_settings()
    mode = str(getattr(settings, "voice_pipeline_mode", "realtime_text") or "realtime_text").strip().lower()
    return mode if mode in ("classic", "realtime_text") else "realtime_text"


def uses_realtime_text(*, settings=None, stack_override: dict[str, Any] | None = None) -> bool:
    return pipeline_mode(settings=settings, stack_override=stack_override) == "realtime_text"


def coerce_live_llm_selection(
    provider: str,
    model: str,
    *,
    settings=None,
    stack_override: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Live realtime path is OpenAI Realtime only — never Gemini or HTTP-only slugs."""
    if not uses_realtime_text(settings=settings, stack_override=stack_override):
        if str(provider or "").strip().lower() == "gemini":
            return "openai", http_openai_model(settings)
        return provider, model
    return "openai", live_openai_model(model, settings)
