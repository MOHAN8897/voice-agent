"""Telnyx Voice API v2 — https://developers.telnyx.com"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from server.config.env import get_settings
from server.config.urls import public_api_base
from server.services.dev_secrets_store import dev_secrets_store

logger = logging.getLogger(__name__)

# Telnyx bidirectional RTP — L16 @ 16 kHz (recommended for AI; matches Sarvam linear16).
TELNYX_RTP_CODEC = "L16"
TELNYX_RTP_SAMPLE_RATE = 16000

TELNYX_API = "https://api.telnyx.com/v2"


class TelnyxConfigError(Exception):
    pass


class TelnyxApiError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def telnyx_enabled() -> bool:
    return bool(dev_secrets_store.effective("enable_telnyx", get_settings().enable_telnyx))


def _resolve_config() -> dict[str, str]:
    settings = get_settings()
    api_key = dev_secrets_store.effective_secret("telnyx_api_key") or settings.telnyx_api_key or ""
    connection_id = dev_secrets_store.effective("telnyx_connection_id", settings.telnyx_connection_id) or ""
    phone = dev_secrets_store.effective("telnyx_phone_number", settings.telnyx_phone_number) or ""
    if not api_key:
        raise TelnyxConfigError("TELNYX_API_KEY is not configured")
    return {
        "api_key": api_key,
        "connection_id": str(connection_id),
        "phone_number": str(phone),
    }


class TelnyxClient:
    def __init__(self, cfg: dict[str, str] | None = None) -> None:
        self.cfg = cfg or _resolve_config()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.cfg['api_key']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{TELNYX_API}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.request(method, url, headers=self._headers(), **kwargs)
        if r.status_code >= 400:
            raise TelnyxApiError(f"Telnyx API {r.status_code}", status=r.status_code, body=r.text[:800])
        if not r.content:
            return {}
        return r.json()

    async def handshake(self) -> dict[str, Any]:
        """List account phone numbers — validates API key."""
        data = await self._request("GET", "/phone_numbers", params={"page[size]": 5})
        numbers = (data.get("data") or []) if isinstance(data.get("data"), list) else []
        phone = self.cfg.get("phone_number") or ""
        if not phone and numbers:
            phone = str((numbers[0] or {}).get("phone_number") or "")
        return {
            "ok": True,
            "phone_number": phone,
            "numbers_count": len(numbers),
            "connection_id": self.cfg.get("connection_id"),
        }

    async def list_phone_numbers(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/phone_numbers", params={"page[size]": 50})
        return list(data.get("data") or [])

    async def get_balance(self) -> dict[str, Any]:
        data = await self._request("GET", "/balance")
        return data.get("data") or data

    async def list_outbound_voice_profiles(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/outbound_voice_profiles")
        return list(data.get("data") or [])

    async def get_outbound_voice_profile(self, ovp_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/outbound_voice_profiles/{ovp_id}")
        return data.get("data") or data

    async def create_outbound_voice_profile(self, name: str) -> dict[str, Any]:
        data = await self._request("POST", "/outbound_voice_profiles", json={"name": name, "enabled": True})
        return data.get("data") or data

    async def update_outbound_voice_profile(self, ovp_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("PATCH", f"/outbound_voice_profiles/{ovp_id}", json=patch)
        return data.get("data") or data

    async def get_call_control_application(self, app_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/call_control_applications/{app_id}")
        return data.get("data") or data

    async def create_call_control_application(
        self,
        *,
        application_name: str,
        webhook_event_url: str,
    ) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/call_control_applications",
            json={
                "application_name": application_name,
                "webhook_event_url": webhook_event_url,
                "webhook_api_version": "2",
                "active": True,
            },
        )
        return data.get("data") or data

    async def update_call_control_application(self, app_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("PATCH", f"/call_control_applications/{app_id}", json=patch)
        return data.get("data") or data

    async def update_phone_number(self, phone_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("PATCH", f"/phone_numbers/{phone_id}", json=patch)
        return data.get("data") or data

    async def list_verified_numbers(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/verified_numbers")
        return list(data.get("data") or [])

    async def request_number_verification(
        self,
        phone_number: str,
        method: str = "sms",
        verification_webhook_url: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"phone_number": phone_number, "verification_method": method}
        if verification_webhook_url:
            payload["verification_webhook_url"] = verification_webhook_url
        data = await self._request("POST", "/verified_numbers", json=payload)
        return data.get("data") or data

    async def confirm_number_verification(self, phone_number: str, code: str) -> dict[str, Any]:
        encoded = phone_number.replace("+", "%2B")
        data = await self._request(
            "POST",
            f"/verified_numbers/{encoded}/actions/verify",
            json={"verification_code": code},
        )
        return data.get("data") or data

    async def search_available_numbers(self, country: str = "IN", limit: int = 5) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/available_phone_numbers",
            params={
                "filter[country_code]": country,
                "filter[features]": "voice",
                "filter[limit]": limit,
            },
        )
        return list(data.get("data") or [])

    async def place_number_order(self, phone_number: str) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/number_orders",
            json={
                "phone_numbers": [{"phone_number": phone_number}],
                "connection_id": self.cfg.get("connection_id") or None,
            },
        )
        return data.get("data") or data

    async def order_phone_number(self, phone_number: str) -> dict[str, Any]:
        from server.services.telnyx_provisioning import provision_ordered_number

        result = await provision_ordered_number(self, phone_number)
        return result.get("order") or result

    async def create_simple_outbound_call(
        self,
        *,
        to_e164: str,
        from_e164: str | None = None,
        client_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Place a plain PSTN call with no media stream — for Telnyx speak/playback isolation tests."""
        from_num = from_e164 or self.cfg.get("phone_number") or ""
        if not from_num:
            raise TelnyxConfigError("Telnyx from number not configured (TELNYX_PHONE_NUMBER)")
        if not self.cfg.get("connection_id"):
            raise TelnyxConfigError("TELNYX_CONNECTION_ID is required for outbound calls")
        payload: dict[str, Any] = {
            "connection_id": self.cfg["connection_id"],
            "to": to_e164,
            "from": from_num,
        }
        if client_state:
            import base64
            import json

            payload["client_state"] = base64.b64encode(json.dumps(client_state).encode()).decode()
        data = await self._request("POST", "/calls", json=payload)
        return data.get("data") or data

    async def create_outbound_call(
        self,
        *,
        to_e164: str,
        from_e164: str | None = None,
        stream_url: str,
        client_state: dict[str, Any] | None = None,
        target_legs: str = "self",
        bidirectional_mode: str = "rtp",
    ) -> dict[str, Any]:
        from_num = from_e164 or self.cfg.get("phone_number") or ""
        if not from_num:
            raise TelnyxConfigError("Telnyx from number not configured (TELNYX_PHONE_NUMBER)")
        if not self.cfg.get("connection_id"):
            raise TelnyxConfigError("TELNYX_CONNECTION_ID is required for outbound calls")
        payload: dict[str, Any] = {
            "connection_id": self.cfg["connection_id"],
            "to": to_e164,
            "from": from_num,
            "stream_url": stream_url,
            "stream_track": "both_tracks",
            "stream_codec": TELNYX_RTP_CODEC,
            "stream_bidirectional_mode": bidirectional_mode,
            "stream_bidirectional_target_legs": target_legs,
            "send_silence_when_idle": True,
        }
        if bidirectional_mode == "rtp":
            payload.update(
                {
                    "stream_bidirectional_codec": TELNYX_RTP_CODEC,
                    "stream_bidirectional_sampling_rate": TELNYX_RTP_SAMPLE_RATE,
                }
            )
        if client_state:
            import base64
            import json

            payload["client_state"] = base64.b64encode(json.dumps(client_state).encode()).decode()
        data = await self._request("POST", "/calls", json=payload)
        return data.get("data") or data

    def build_stream_ws_url(self, *, token: str) -> str:
        base = public_api_base().rstrip("/")
        ws = base.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws}/ws/telnyx-stream?token={token}"

    async def start_streaming(
        self,
        call_control_id: str,
        *,
        stream_url: str,
        target_legs: str = "self",
    ) -> dict[str, Any]:
        """Start or restart bidirectional media stream (fallback if dial-time stream_url failed)."""
        payload: dict[str, Any] = {
            "stream_url": stream_url,
            "stream_track": "both_tracks",
            "stream_codec": TELNYX_RTP_CODEC,
            "stream_bidirectional_mode": "rtp",
            "stream_bidirectional_codec": TELNYX_RTP_CODEC,
            "stream_bidirectional_sampling_rate": TELNYX_RTP_SAMPLE_RATE,
            "stream_bidirectional_target_legs": target_legs,
            "send_silence_when_idle": True,
        }
        data = await self._request(
            "POST",
            f"/calls/{call_control_id}/actions/streaming_start",
            json=payload,
        )
        return data.get("data") or data

    async def playback_start(self, call_control_id: str, audio_url: str) -> dict[str, Any]:
        """Play hosted audio on the call (bypasses WebSocket — isolates Telnyx→handset path)."""
        data = await self._request(
            "POST",
            f"/calls/{call_control_id}/actions/playback_start",
            json={"audio_url": audio_url},
        )
        return data.get("data") or data

    async def speak(
        self,
        call_control_id: str,
        text: str,
        *,
        language: str = "en-US",
        voice: str = "female",
    ) -> dict[str, Any]:
        """Telnyx built-in TTS on the call (bypasses our WebSocket audio path)."""
        data = await self._request(
            "POST",
            f"/calls/{call_control_id}/actions/speak",
            json={"payload": text, "language": language, "voice": voice},
        )
        return data.get("data") or data

    async def hangup(self, call_control_id: str) -> dict[str, Any]:
        """End an active Telnyx call (dev stress tests / cleanup)."""
        data = await self._request("POST", f"/calls/{call_control_id}/actions/hangup", json={})
        return data.get("data") or data


class TelnyxCallRegistry:
    """In-memory Telnyx call events for dev Test Studio."""

    def __init__(self) -> None:
        self._calls: dict[str, dict[str, Any]] = {}

    def upsert(self, call_control_id: str, patch: dict[str, Any]) -> None:
        import time

        row = self._calls.get(call_control_id) or {"call_control_id": call_control_id}
        row.update(patch)
        row["updated_at"] = int(time.time())
        self._calls[call_control_id] = row

    def get(self, call_control_id: str) -> dict[str, Any] | None:
        return self._calls.get(call_control_id)

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = sorted(self._calls.values(), key=lambda r: r.get("updated_at") or 0, reverse=True)
        return rows[:limit]


telnyx_call_registry = TelnyxCallRegistry()


class TelnyxStreamTokens:
    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, Any]] = {}

    def put(self, token: str, **meta: Any) -> None:
        self._tokens[token] = meta

    def consume(self, token: str) -> dict[str, Any] | None:
        return self._tokens.pop(token, None)

    def peek(self, token: str) -> dict[str, Any] | None:
        return self._tokens.get(token)

    def create(self, **meta: Any) -> str:
        tok = uuid.uuid4().hex
        self.put(tok, **meta)
        return tok


telnyx_stream_tokens = TelnyxStreamTokens()
