"""Effective dev overlay values — single place for runtime reads after UI changes."""
from __future__ import annotations

from typing import Any

from server.config.env import Settings, get_settings
from server.services.dev_secrets_store import dev_secrets_store


def effective(field: str, default: Any = None) -> Any:
    settings = get_settings()
    return dev_secrets_store.effective(field, getattr(settings, field, default))


def effective_secret(field: str) -> str | None:
    return dev_secrets_store.effective_secret(field)


def effective_app_environment() -> str:
    settings = get_settings()
    return str(dev_secrets_store.effective("app_environment", settings.app_environment))


def effective_config_mode() -> str:
    settings = get_settings()
    return str(dev_secrets_store.effective("voice_agent_config_mode", settings.voice_agent_config_mode))


def effective_voice_tier() -> str:
    settings = get_settings()
    return str(dev_secrets_store.effective("voice_agent_tier", settings.voice_agent_tier))


def benchmarks_enabled() -> bool:
    settings = get_settings()
    return bool(dev_secrets_store.effective("enable_benchmarks", settings.enable_benchmarks))


def openai_enabled() -> bool:
    settings = get_settings()
    return bool(dev_secrets_store.effective("enable_openai", settings.enable_openai))


def voice_provider_enabled(provider_id: str) -> bool:
    """STT/LLM/TTS provider toggle from dev overlay."""
    settings = get_settings()
    field_map = {
        "sarvam": "enable_sarvam",
        "openai": "enable_openai",
        "deepseek": "enable_deepseek",
        "gemini": "enable_gemini",
        "cartesia": "enable_cartesia",
    }
    field = field_map.get(provider_id)
    if not field:
        return False
    return bool(dev_secrets_store.effective(field, getattr(settings, field, False)))


def telephony_provider_enabled(provider_id: str) -> bool:
    """PSTN trunk toggle from dev overlay."""
    from server.services.telephony import VALID_PROVIDERS, provider_enabled

    if provider_id not in VALID_PROVIDERS:
        return False
    return provider_enabled(provider_id)  # type: ignore[arg-type]


def notify_dev_overlay_changed() -> None:
    """Reload cached settings/clients after dev_secrets.json changes."""
    from server.providers import init_provider_registry
    from server.utils.http_clients import reset_http_clients

    get_settings.cache_clear()
    reset_http_clients()
    init_provider_registry()
