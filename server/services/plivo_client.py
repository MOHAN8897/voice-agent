"""Plivo Voice API — https://www.plivo.com/docs/voice/"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from server.config.env import get_settings
from server.config.urls import public_api_base
from server.services.dev_secrets_store import dev_secrets_store

logger = logging.getLogger(__name__)

PLIVO_API = "https://api.plivo.com/v1"


class PlivoConfigError(Exception):
    pass


class PlivoApiError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def plivo_enabled() -> bool:
    return bool(dev_secrets_store.effective("enable_plivo", get_settings().enable_plivo))


def _resolve_config() -> dict[str, str]:
    settings = get_settings()
    auth_id = dev_secrets_store.effective_secret("plivo_auth_id") or settings.plivo_auth_id or ""
    auth_token = dev_secrets_store.effective_secret("plivo_auth_token") or settings.plivo_auth_token or ""
    phone = dev_secrets_store.effective("plivo_phone_number", settings.plivo_phone_number) or ""
    if not auth_id or not auth_token:
        raise PlivoConfigError("PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN are required")
    return {"auth_id": auth_id, "auth_token": auth_token, "phone_number": phone}


class PlivoClient:
    def __init__(self, cfg: dict[str, str] | None = None) -> None:
        self.cfg = cfg or _resolve_config()

    def _base(self) -> str:
        return f"{PLIVO_API}/Account/{self.cfg['auth_id']}"

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self._base()}{path}"
        auth = (self.cfg["auth_id"], self.cfg["auth_token"])
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.request(method, url, auth=auth, **kwargs)
        if r.status_code >= 400:
            raise PlivoApiError(f"Plivo API {r.status_code}", status=r.status_code, body=r.text[:500])
        if not r.content:
            return {}
        return r.json()

    async def handshake(self) -> dict[str, Any]:
        data = await self._request("GET", "/")
        return {
            "ok": True,
            "account": data.get("account") or data.get("name"),
            "phone_number": self.cfg.get("phone_number"),
        }

    def build_stream_ws_url(self, *, token: str) -> str:
        base = public_api_base().rstrip("/")
        ws = base.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws}/ws/plivo-stream?token={token}"

    def answer_xml(self, stream_url: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f'<Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">'
            f"{stream_url}"
            "</Stream>"
            "</Response>"
        )

    async def create_outbound_call(
        self,
        *,
        to_e164: str,
        from_e164: str | None = None,
        answer_url: str,
        client_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from_num = from_e164 or self.cfg.get("phone_number") or ""
        if not from_num:
            raise PlivoConfigError("PLIVO_PHONE_NUMBER is required")
        payload: dict[str, Any] = {
            "from": from_num,
            "to": to_e164,
            "answer_url": answer_url,
            "answer_method": "GET",
        }
        return await self._request("POST", "/Call/", json=payload)


class PlivoCallRegistry:
    def __init__(self) -> None:
        self._calls: dict[str, dict[str, Any]] = {}

    def upsert(self, call_uuid: str, patch: dict[str, Any]) -> None:
        import time

        row = self._calls.get(call_uuid) or {"call_uuid": call_uuid}
        row.update(patch)
        row["updated_at"] = int(time.time())
        self._calls[call_uuid] = row

    def get(self, call_uuid: str) -> dict[str, Any] | None:
        return self._calls.get(call_uuid)

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = sorted(self._calls.values(), key=lambda r: r.get("updated_at") or 0, reverse=True)
        return rows[:limit]


plivo_call_registry = PlivoCallRegistry()


class PlivoStreamTokens:
    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, Any]] = {}

    def put(self, token: str, **meta: Any) -> None:
        self._tokens[token] = meta

    def consume(self, token: str) -> dict[str, Any] | None:
        return self._tokens.pop(token, None)

    def create(self, **meta: Any) -> str:
        import uuid

        tok = uuid.uuid4().hex
        self.put(tok, **meta)
        return tok


plivo_stream_tokens = PlivoStreamTokens()
