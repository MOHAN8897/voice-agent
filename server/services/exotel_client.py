"""Exotel Programmable Voice REST client — https://developer.exotel.com/docs/voice"""
from __future__ import annotations

import time
from typing import Any

import httpx

from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store


class ExotelConfigError(Exception):
    pass


class ExotelApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


_HANDSHAKE_CACHE: dict[str, Any] | None = None
_HANDSHAKE_CACHE_AT: float = 0.0
_HANDSHAKE_TTL_SEC = 90.0


def clear_handshake_cache() -> None:
    global _HANDSHAKE_CACHE, _HANDSHAKE_CACHE_AT
    _HANDSHAKE_CACHE = None
    _HANDSHAKE_CACHE_AT = 0.0


async def cached_handshake(client: ExotelClient | None = None, *, force: bool = False) -> dict[str, Any]:
    """Balance API with short TTL to avoid Exotel 'Too many GET requests'."""
    global _HANDSHAKE_CACHE, _HANDSHAKE_CACHE_AT
    now = time.time()
    if not force and _HANDSHAKE_CACHE and now - _HANDSHAKE_CACHE_AT < _HANDSHAKE_TTL_SEC:
        return dict(_HANDSHAKE_CACHE)
    c = client or ExotelClient()
    result = await c.handshake()
    _HANDSHAKE_CACHE = dict(result)
    _HANDSHAKE_CACHE_AT = now
    return dict(result)


def _resolve_exotel_config() -> dict[str, str]:
    settings = get_settings()
    api_key = dev_secrets_store.effective_secret("exotel_api_key") or settings.exotel_api_key
    api_token = dev_secrets_store.effective_secret("exotel_api_token") or settings.exotel_api_token
    account_sid = dev_secrets_store.effective("exotel_account_sid", settings.exotel_account_sid) or ""
    subdomain = dev_secrets_store.effective("exotel_subdomain", settings.exotel_subdomain) or "api.exotel.com"
    exophone = dev_secrets_store.effective("exotel_exophone", settings.exotel_exophone) or ""
    if not api_key or not api_token:
        raise ExotelConfigError("EXOTEL_API_KEY and EXOTEL_API_TOKEN are required")
    if not str(account_sid).strip():
        raise ExotelConfigError("EXOTEL_ACCOUNT_SID is required")
    return {
        "api_key": str(api_key).strip(),
        "api_token": str(api_token).strip(),
        "account_sid": str(account_sid).strip(),
        "subdomain": str(subdomain).strip().rstrip("/"),
        "exophone": str(exophone).strip(),
    }


def exotel_enabled() -> bool:
    return bool(dev_secrets_store.effective("enable_exotel", get_settings().enable_exotel))


def webhook_base_url() -> str | None:
    from server.config.urls import public_api_base

    base = public_api_base()
    if base.startswith("http://127.0.0.1") or base.startswith("http://localhost"):
        settings = get_settings()
        override = dev_secrets_store.effective("exotel_webhook_base_url", settings.exotel_webhook_base_url)
        if override:
            return str(override).rstrip("/")
        return None
    return base


class ExotelClient:
    def __init__(self, cfg: dict[str, str] | None = None):
        self.cfg = cfg or _resolve_exotel_config()
        self.base_url = f"https://{self.cfg['subdomain']}/v1/Accounts/{self.cfg['account_sid']}"
        self.auth = (self.cfg["api_key"], self.cfg["api_token"])

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request(method, url, auth=self.auth, data=data)
        try:
            payload = r.json() if r.content else {}
        except Exception:
            payload = {"raw": r.text}
        if not r.is_success:
            msg = ""
            if isinstance(payload, dict):
                rest = payload.get("RestException") or {}
                msg = str(rest.get("Message") or payload.get("message") or r.text or "Exotel API error")
            else:
                msg = r.text or "Exotel API error"
            raise ExotelApiError(msg, status_code=r.status_code, payload=payload)
        return payload if isinstance(payload, dict) else {"data": payload}

    async def list_incoming_numbers(self) -> list[dict[str, Any]]:
        """List ExoPhones provisioned on the account (may be empty)."""
        payload = await self._request("GET", "/IncomingPhoneNumbers.json")
        if isinstance(payload.get("RestException"), dict):
            msg = str(payload["RestException"].get("Message") or "")
            if "No matching results" in msg:
                return []
        items = payload.get("IncomingPhoneNumbers") or payload.get("incoming_phone_numbers") or []
        if isinstance(items, dict):
            items = [items]
        out: list[dict[str, Any]] = []
        for row in items:
            if not isinstance(row, dict):
                continue
            phone = row.get("PhoneNumber") or row.get("phone_number") or row.get("FriendlyName")
            if phone:
                out.append(
                    {
                        "e164": str(phone),
                        "sid": row.get("Sid") or row.get("sid"),
                        "friendly_name": row.get("FriendlyName"),
                        "source": "exotel_api",
                    }
                )
        return out

    async def handshake(self) -> dict[str, Any]:
        """Verify credentials via Balance API."""
        payload = await self._request("GET", "/Balance.json")
        account = payload.get("Account") or {}
        balance_data = account.get("BalanceData") or {}
        balance_simple = payload.get("Balance") or {}
        amount = balance_data.get("Balance") or balance_simple.get("Amount")
        return {
            "ok": True,
            "account_sid": account.get("AccountSid") or self.cfg["account_sid"],
            "balance": amount,
            "currency": balance_data.get("Currency") or balance_simple.get("Currency"),
            "pricing_plan": balance_data.get("PricingPlan"),
            "subdomain": self.cfg["subdomain"],
        }

    async def connect_two_numbers(
        self,
        *,
        from_number: str,
        to_number: str,
        caller_id: str,
        status_callback: str | None = None,
        custom_field: str | None = None,
        record: bool = False,
        stream_url: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "From": from_number,
            "To": to_number,
            "CallerId": caller_id,
            "CallType": "trans",
        }
        if status_callback:
            data["StatusCallback"] = status_callback
            data["StatusCallbackEvents[0]"] = "terminal"
            data["StatusCallbackEvents[1]"] = "answered"
            data["StatusCallbackContentType"] = "application/json"
        if custom_field:
            data["CustomField"] = custom_field[:128]
        if record:
            data["Record"] = "true"
        if stream_url:
            data["StreamUrl"] = stream_url
            data["StreamBegin"] = "at Leg2Connect"
        payload = await self._request("POST", "/Calls/connect", data=data, timeout=30.0)
        return self._parse_connect_response(payload)

    async def connect_voice_ai(
        self,
        *,
        to_number: str,
        caller_id: str,
        stream_url: str,
        status_callback: str | None = None,
        custom_field: str | None = None,
        record: bool = False,
    ) -> dict[str, Any]:
        """Outbound Voice AI — dial customer and stream to bidirectional WSS bot."""
        data: dict[str, Any] = {
            "From": to_number,
            "CallerId": caller_id,
            "StreamUrl": stream_url,
            "StreamType": "bidirectional",
        }
        if status_callback:
            data["StatusCallback"] = status_callback
            data["StatusCallbackEvents[0]"] = "terminal"
            data["StatusCallbackEvents[1]"] = "answered"
            data["StatusCallbackContentType"] = "application/json"
        if custom_field:
            data["CustomField"] = custom_field[:128]
        if record:
            data["Record"] = "true"
        payload = await self._request("POST", "/Calls/connect", data=data, timeout=30.0)
        return self._parse_connect_response(payload)

    def _parse_connect_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        call = payload.get("Call") or {}
        return {
            "call_sid": call.get("Sid"),
            "status": call.get("Status"),
            "from": call.get("From"),
            "to": call.get("To"),
            "direction": call.get("Direction"),
            "raw": call,
        }

    async def get_call(self, call_sid: str) -> dict[str, Any]:
        payload = await self._request("GET", f"/Calls/{call_sid}.json")
        return payload.get("Call") or payload


def public_webhook_urls() -> dict[str, str | None]:
    base = webhook_base_url()
    if not base:
        return {"passthru_url": None, "status_callback_url": None, "stream_url_resolver": None}
    return {
        "passthru_url": f"{base}/api/exotel/passthru",
        "status_callback_url": f"{base}/api/exotel/status-callback",
        "stream_url_resolver": f"{base}/api/exotel/stream-url",
    }


def build_stream_ws_url(
    *,
    agent_id: str | None = None,
    tier: str | None = None,
    token: str | None = None,
) -> str | None:
    """Public WSS URL for Exotel Voicebot / Connect Voice AI."""
    import secrets

    base = webhook_base_url()
    if not base:
        return None
    from server.config.urls import ws_public_base

    ws_base = ws_public_base()
    tok = token or secrets.token_urlsafe(18)
    from server.services.exotel_stream_tokens import exotel_stream_tokens

    exotel_stream_tokens.put(tok, agent_id=agent_id, tier=tier)
    qs = f"token={tok}"
    if agent_id:
        qs += f"&agentId={agent_id}"
    if tier:
        qs += f"&tier={tier}"
    return f"{ws_base}/ws/exotel-stream?{qs}"
