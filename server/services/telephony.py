"""Active PSTN / SIP trunk provider selection (Exotel, Telnyx, Plivo)."""
from __future__ import annotations

from typing import Any, Literal

from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store

TelephonyProviderId = Literal["exotel", "telnyx", "plivo"]
VALID_PROVIDERS: tuple[TelephonyProviderId, ...] = ("exotel", "telnyx", "plivo")


def _effective_str(field: str, default: str | None = None) -> str:
    settings = get_settings()
    return str(dev_secrets_store.effective(field, getattr(settings, field, default)) or "").strip()


def active_telephony_provider() -> TelephonyProviderId:
    raw = str(
        dev_secrets_store.effective("telephony_provider", get_settings().telephony_provider) or "exotel"
    ).strip().lower()
    if raw not in VALID_PROVIDERS:
        return "exotel"
    return raw  # type: ignore[return-value]


def provider_enabled(provider: TelephonyProviderId) -> bool:
    settings = get_settings()
    if provider == "exotel":
        return bool(dev_secrets_store.effective("enable_exotel", settings.enable_exotel))
    if provider == "telnyx":
        return bool(dev_secrets_store.effective("enable_telnyx", settings.enable_telnyx))
    if provider == "plivo":
        return bool(dev_secrets_store.effective("enable_plivo", settings.enable_plivo))
    return False


def provider_configured(provider: TelephonyProviderId) -> bool:
    """Keys + required IDs present (overlay-aware). Does not check handshake."""
    settings = get_settings()
    if provider == "exotel":
        key = dev_secrets_store.effective_secret("exotel_api_key") or settings.exotel_api_key
        token = dev_secrets_store.effective_secret("exotel_api_token") or settings.exotel_api_token
        sid = _effective_str("exotel_account_sid", settings.exotel_account_sid)
        return bool(key and token and sid)
    if provider == "telnyx":
        key = dev_secrets_store.effective_secret("telnyx_api_key") or settings.telnyx_api_key
        conn = _effective_str("telnyx_connection_id", settings.telnyx_connection_id)
        return bool(key and conn)
    if provider == "plivo":
        auth = dev_secrets_store.effective_secret("plivo_auth_id") or settings.plivo_auth_id
        token = dev_secrets_store.effective_secret("plivo_auth_token") or settings.plivo_auth_token
        return bool(auth and token)
    return False


def active_provider_ready() -> bool:
    """Sync check — enabled, configured keys present for active provider."""
    pid = active_telephony_provider()
    return provider_enabled(pid) and provider_configured(pid)


def require_active_provider() -> TelephonyProviderId | None:
    """Return active provider when enabled; None when disabled in Environment."""
    pid = active_telephony_provider()
    if not provider_enabled(pid):
        return None
    return pid


def telephony_guard_error(provider: TelephonyProviderId) -> str | None:
    if not provider_enabled(provider):
        return f"{provider.title()} is disabled in Dev Environment"
    if not provider_configured(provider):
        return f"{provider.title()} is enabled but missing API keys or required IDs in Environment"
    return None


async def telephony_summary_async() -> dict[str, Any]:
    from server.services.telephony_status import all_provider_status

    active = active_telephony_provider()
    providers = await all_provider_status()
    active_st = next((p for p in providers if p.get("id") == active), {})
    enabled_providers = [p for p in providers if p.get("enabled")]
    return {
        "active_provider": active,
        "active_enabled": bool(active_st.get("enabled")),
        "active_ready": bool(active_st.get("ready")),
        "providers": providers,
        "enabled_providers": [p.get("id") for p in enabled_providers],
    }
