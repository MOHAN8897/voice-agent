"""
OpenAI model capability helpers — which request params each model family supports.
Voice-agent tuned: low reasoning effort on GPT-5 family for faster time-to-first-token.
"""
from __future__ import annotations

# Reasoning / GPT-5 family models reject `temperature` on the Responses API.
_NO_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def supports_temperature(model: str | None) -> bool:
    m = (model or "").strip().lower()
    if not m:
        return True
    return not any(m.startswith(p) for p in _NO_TEMPERATURE_PREFIXES)


def voice_reasoning_effort(model: str | None) -> str | None:
    """Pick fastest stable reasoning tier per model (OpenAI voice-agent guidance)."""
    m = (model or "").strip().lower()
    if not m.startswith("gpt-5"):
        return None
    if "luna" in m or "nano" in m or "mini" in m:
        return "none"
    if m in ("gpt-5", "gpt-5.4"):
        return "low"
    return "low"  # gpt-5.5 / gpt-5.6-* — low balances speed + quality for voice


def apply_generation_params(
    create_kwargs: dict,
    *,
    model: str,
    temperature: float | None,
    default_temperature: float,
    voice_optimized: bool = True,
) -> dict:
    """Mutates create_kwargs in place; omits temperature when unsupported."""
    if supports_temperature(model):
        use_temp = temperature if temperature is not None else default_temperature
        create_kwargs["temperature"] = max(0.0, min(2.0, float(use_temp)))
    elif "temperature" in create_kwargs:
        del create_kwargs["temperature"]

    if voice_optimized:
        effort = voice_reasoning_effort(model)
        if effort:
            create_kwargs["reasoning"] = {"effort": effort}
    return create_kwargs
