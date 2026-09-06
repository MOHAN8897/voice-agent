"""Telephony overlay toggle and guard tests."""
from __future__ import annotations

from server.services.dev_secrets_store import dev_secrets_store
from server.services.telephony import (
    active_telephony_provider,
    provider_configured,
    provider_enabled,
    telephony_guard_error,
)


def test_telephony_enable_flags_respect_overlay():
    dev_secrets_store.update({"enable_telnyx": True, "enable_exotel": False, "enable_plivo": False})
    assert provider_enabled("telnyx") is True
    assert provider_enabled("exotel") is False
    assert provider_enabled("plivo") is False
    dev_secrets_store.remove_overlay_key("enable_telnyx")
    dev_secrets_store.remove_overlay_key("enable_exotel")
    dev_secrets_store.remove_overlay_key("enable_plivo")


def test_telephony_guard_blocks_disabled_active_provider():
    dev_secrets_store.update({"telephony_provider": "telnyx", "enable_telnyx": False})
    assert active_telephony_provider() == "telnyx"
    assert telephony_guard_error("telnyx") == "Telnyx is disabled in Dev Environment"
    dev_secrets_store.remove_overlay_key("telephony_provider")
    dev_secrets_store.remove_overlay_key("enable_telnyx")


def test_provider_configured_uses_overlay_strings():
    dev_secrets_store.update(
        {
            "enable_exotel": True,
            "exotel_api_key": "key",
            "exotel_api_token": "token",
            "exotel_account_sid": "sid123",
        }
    )
    assert provider_configured("exotel") is True
    dev_secrets_store.update({"exotel_account_sid": ""})
    assert provider_configured("exotel") is False
    for field in ("exotel_api_key", "exotel_api_token", "exotel_account_sid", "enable_exotel"):
        dev_secrets_store.remove_overlay_key(field)
