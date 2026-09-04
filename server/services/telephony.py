"""Active PSTN / SIP trunk provider selection (Exotel, Telnyx, Plivo)."""
from __future__ import annotations

from typing import Any, Literal

from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store

TelephonyProviderId = Literal["exotel", "telnyx", "plivo"]
VALID_PROVIDERS: tuple[TelephonyProviderId, ...] = ("exotel", "telnyx", "plivo")


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


def active_provider_ready() -> bool:
    """Sync check — configured keys present for active provider."""
    pid = active_telephony_provider()
    if not provider_enabled(pid):
        return False
    settings = get_settings()
    if pid == "exotel":
        key = dev_secrets_store.effective_secret("exotel_api_key") or settings.exotel_api_key
        return bool(key and settings.exotel_account_sid)
    if pid == "telnyx":
        key = dev_secrets_store.effective_secret("telnyx_api_key") or settings.telnyx_api_key
        return bool(key and settings.telnyx_connection_id)
    if pid == "plivo":
        auth = dev_secrets_store.effective_secret("plivo_auth_id") or settings.plivo_auth_id
        token = dev_secrets_store.effective_secret("plivo_auth_token") or settings.plivo_auth_token
        return bool(auth and token)
    return False


async def telephony_summary_async() -> dict[str, Any]:
    from server.services.telephony_status import all_provider_status

    active = active_telephony_provider()
    providers = await all_provider_status()
    active_st = next((p for p in providers if p.get("id") == active), {})
    return {
        "active_provider": active,
        "active_ready": bool(active_st.get("ready")),
        "providers": providers,
    }
