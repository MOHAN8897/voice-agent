"""PSTN provider handshake + status helpers."""
from __future__ import annotations

from typing import Any

from server.config.env import get_settings
from server.config.urls import public_api_base
from server.services.dev_secrets_store import dev_secrets_store
from server.services.telephony import TelephonyProviderId, VALID_PROVIDERS


def webhook_base_url() -> str:
    settings = get_settings()
    override = dev_secrets_store.effective("exotel_webhook_base_url", settings.exotel_webhook_base_url)
    if override:
        return str(override).rstrip("/")
    return public_api_base()


def _ws_base(http_base: str) -> str:
    if http_base.startswith("https://"):
        return "wss://" + http_base[8:]
    if http_base.startswith("http://"):
        return "ws://" + http_base[7:]
    return http_base


async def provider_status(provider: TelephonyProviderId) -> dict[str, Any]:
    if provider == "exotel":
        return await _exotel_status()
    if provider == "telnyx":
        return await _telnyx_status()
    if provider == "plivo":
        return await _plivo_status()
    return {"id": provider, "configured": False, "handshake_ok": False}


async def all_provider_status() -> list[dict[str, Any]]:
    return [await provider_status(p) for p in VALID_PROVIDERS]


async def _exotel_status() -> dict[str, Any]:
    from server.services.exotel_client import ExotelClient, cached_handshake, exotel_enabled, public_webhook_urls

    settings = get_settings()
    enabled = exotel_enabled()
    configured = False
    handshake_ok = False
    handshake_error: str | None = None
    balance: str | None = None
    try:
        client = ExotelClient()
        configured = True
        hs = await cached_handshake(client)
        handshake_ok = bool(hs.get("ok"))
        balance = hs.get("balance")
    except Exception as e:
        handshake_error = str(e)[:300]
    urls = public_webhook_urls()
    return {
        "id": "exotel",
        "label": "Exotel",
        "enabled": enabled,
        "configured": configured,
        "handshake_ok": handshake_ok,
        "handshake_error": handshake_error,
        "balance": balance,
        "phone_number": settings.exotel_exophone,
        "webhook_base": webhook_base_url(),
        **urls,
        "ready": enabled and configured and handshake_ok,
    }


async def _telnyx_status() -> dict[str, Any]:
    from server.services.telnyx_client import TelnyxClient, telnyx_enabled
    from server.services.telnyx_provisioning import telnyx_setup_status

    settings = get_settings()
    enabled = telnyx_enabled()
    configured = False
    handshake_ok = False
    handshake_error: str | None = None
    phone: str | None = None
    checklist: dict[str, Any] = {}
    try:
        client = TelnyxClient()
        configured = True
        hs = await client.handshake()
        handshake_ok = bool(hs.get("ok"))
        phone = hs.get("phone_number") or settings.telnyx_phone_number
        checklist = await telnyx_setup_status(client)
    except Exception as e:
        handshake_error = str(e)[:300]
    base = webhook_base_url()
    return {
        "id": "telnyx",
        "label": "Telnyx",
        "enabled": enabled,
        "configured": configured,
        "handshake_ok": handshake_ok,
        "handshake_error": handshake_error,
        "phone_number": phone or settings.telnyx_phone_number,
        "connection_id": settings.telnyx_connection_id,
        "webhook_url": f"{base}/api/telnyx/webhook",
        "stream_ws": f"{_ws_base(base)}/ws/telnyx-stream",
        "checklist": checklist,
        "ready": enabled and configured and handshake_ok and bool(checklist.get("ready_for_us_ca")),
        "ready_for_india": bool(checklist.get("ready_for_india")),
        "upgrade_required_for_india": bool(checklist.get("upgrade_required_for_india")),
    }


async def _plivo_status() -> dict[str, Any]:
    from server.services.plivo_client import PlivoClient, plivo_enabled

    settings = get_settings()
    enabled = plivo_enabled()
    configured = False
    handshake_ok = False
    handshake_error: str | None = None
    try:
        client = PlivoClient()
        configured = True
        hs = await client.handshake()
        handshake_ok = bool(hs.get("ok"))
    except Exception as e:
        handshake_error = str(e)[:300]
    base = webhook_base_url()
    return {
        "id": "plivo",
        "label": "Plivo",
        "enabled": enabled,
        "configured": configured,
        "handshake_ok": handshake_ok,
        "handshake_error": handshake_error,
        "phone_number": settings.plivo_phone_number,
        "answer_url": f"{base}/api/plivo/answer",
        "stream_ws": f"{_ws_base(base)}/ws/plivo-stream",
        "ready": enabled and configured and handshake_ok,
    }
