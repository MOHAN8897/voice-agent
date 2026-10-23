"""Resolve offline script generation from the persisted primary call stack."""
from server.config.env import get_settings
from server.providers.base import LLMConfig
from server.services.saas.platform_phone_stack import resolve_platform_phone_stack_sync


def generation_provider() -> str:
    stack = resolve_platform_phone_stack_sync()
    return str((stack.get("llm") or {}).get("provider") or "gemini").lower()


def generation_target_metadata() -> tuple[str, str | None]:
    """Identify the selected generation target even if its adapter later fails."""
    settings = get_settings()
    provider = generation_provider()
    if provider == "gemini":
        model = (settings.gemini_model or "gemini-3.5-flash-lite").removeprefix("models/")
        return provider, "gemini-3.5-flash-lite" if "live" in model.lower() else model
    model = getattr(settings, f"{provider}_model", None)
    if provider == "openai" and (not model or "realtime" in str(model).lower()):
        from server.realtime.models import DEFAULT_HTTP_LLM_MODEL

        model = DEFAULT_HTTP_LLM_MODEL
    return provider, model


def generation_target():
    """A selected provider failing never authorizes a different provider."""
    provider, model = generation_target_metadata()
    if provider == "gemini":
        from server.providers.gemini_llm import GeminiLLMAdapter
        return GeminiLLMAdapter(), LLMConfig(provider="gemini", model=model, temperature=0.0)
    # Explicit admin selections keep their existing adapter. There is no retry chain.
    from server.providers.registry import get_provider_registry
    adapter = get_provider_registry().get_llm(provider)
    if adapter is None:
        raise RuntimeError("The selected script generation provider is unavailable")
    return adapter, LLMConfig(provider=provider, model=model)
