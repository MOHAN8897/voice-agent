"""Validated text transports for the models used by composed voice calls."""
from __future__ import annotations

from typing import Any

#: Content refusals repeat byte-for-byte; every other early stop gets one retry.
NON_RETRYABLE_FINISH_REASONS = frozenset(
    {"content_filter", "safety", "recitation", "blocked", "prohibited_content"}
)


class IncompleteTurnError(RuntimeError):
    """The provider stopped before a usable turn completed.

    Carries the stop reason and whatever was already produced so the caller can
    retry once, preserve diagnostics, or fall back without guessing.
    """

    def __init__(
        self,
        *,
        provider: str,
        finish_reason: str | None,
        partial_text: str = "",
        usage: dict[str, Any] | None = None,
        retry_used: bool = False,
        raw_finish_reason: str | None = None,
    ) -> None:
        self.provider = provider
        self.raw_finish_reason = str(raw_finish_reason or finish_reason or "unknown").strip()
        # Providers disagree on casing ("SAFETY" vs "safety"); the retry policy is
        # decided on the normalized value so a refusal is never retried.
        self.finish_reason = self.raw_finish_reason.lower()
        self.partial_text = partial_text or ""
        self.usage = dict(usage or {})
        self.retry_used = retry_used
        super().__init__(f"{provider} did not complete the turn ({self.finish_reason})")

    @property
    def retryable(self) -> bool:
        return self.finish_reason not in NON_RETRYABLE_FINISH_REASONS


def sarvam_chat_modes(model: str) -> list[str]:
    if model == "sarvam-105b-conversations":
        return ["chat_completions_v1"]
    if model == "sarvam-105b":
        return ["chat_completions_v1", "chat_completions_v2"]
    if model in {"glm5.3", "gemma4", "deepseekv4.1-flash"}:
        return ["chat_completions_v2"]
    return []


def text_llm_api_mode(provider: str, model: str, mode: str | None = None) -> str:
    """Validate the selected tuple, never replace its provider or model."""
    selected = str(mode or "").strip().lower()
    if provider == "sarvam":
        modes = sarvam_chat_modes(model)
        if not modes or (selected and selected not in modes):
            raise ValueError("The selected Sarvam model is unavailable on this chat API mode (V1/V2)")
        return selected or modes[0]
    if provider == "gemini":
        from server.realtime.models import is_gemini_live_voice_model, is_realtime_llm_model

        if not model.startswith("gemini-") or is_gemini_live_voice_model(model) or is_realtime_llm_model(model) or "-tts" in model:
            raise ValueError("The selected Gemini model is not a text-generation model")
        # Older saved profiles labelled Gemini's text transport with the shared
        # chat-v1 picker value. The wire protocol is GenerateContent, not OpenAI.
        if selected in {"", "chat_completions_v1"}:
            return "streaming_rest"
        if selected in {"streaming_rest", "unary_rest"}:
            return selected
        raise ValueError("The selected Gemini text model requires a REST API mode")
    raise ValueError("The selected composed text provider has no supported tool protocol")


def native_audio_provider(provider: str, model: str, mode: str | None) -> str | None:
    from server.realtime.models import is_gemini_live_voice_model, is_realtime_llm_model

    if not is_gemini_live_voice_model(model) and not is_realtime_llm_model(model):
        if mode == "websocket":
            raise ValueError("The selected text model does not use a native audio socket")
        return None
    expected = "gemini" if is_gemini_live_voice_model(model) else "openai"
    if provider != expected or mode != "websocket":
        raise ValueError("The native audio model, provider and transport do not match")
    return expected
