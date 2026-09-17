"""Telnyx Voice API v2 — https://developers.telnyx.com"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any
from urllib.parse import urlparse

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
        timeout = kwargs.pop("timeout", None)
        if timeout is None:
            timeout = httpx.Timeout(connect=15.0, read=25.0, write=15.0, pool=15.0)
        # A lost dial response does not mean the call was not placed. Retrying
        # POST /calls creates another real call, leaving the first untracked.
        max_attempts = 1 if method.upper() == "POST" and path == "/calls" else 2
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    r = await client.request(method, url, headers=self._headers(), **kwargs)
                if r.status_code >= 400:
                    raise TelnyxApiError(f"Telnyx API {r.status_code}", status=r.status_code, body=r.text[:800])
                if not r.content:
                    return {}
                return r.json()
            except httpx.TimeoutException as exc:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.3)
                    continue
                raise TelnyxApiError(f"Telnyx API timeout ({exc.__class__.__name__})", status=None, body=str(exc)[:400]) from exc
            except httpx.HTTPError as exc:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.3)
                    continue
                raise TelnyxApiError(f"Telnyx API transport ({exc.__class__.__name__})", status=None, body=str(exc)[:400]) from exc

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
        stream_url: str | None = None,
        client_state: dict[str, Any] | None = None,
        target_legs: str = "both",
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
            # Default Telnyx answer wait is 30s; give the callee more ring time.
            "timeout_secs": 60,
        }
        # Prefer starting media on answer via streaming_start. Dial-time stream_url makes
        # Telnyx open WSS during ring; through Cloudflare that often ends as connection_failed
        # before the callee answers.
        if stream_url:
            payload.update(
                {
                    "stream_url": stream_url,
                    "stream_track": "both_tracks",
                    "stream_codec": TELNYX_RTP_CODEC,
                    "stream_bidirectional_mode": bidirectional_mode,
                    "stream_bidirectional_target_legs": target_legs,
                    "send_silence_when_idle": True,
                }
            )
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
        parsed = urlparse(base)
        if parsed.scheme not in ("http", "https"):
            raise TelnyxConfigError(
                f"public_api_base has unsupported scheme '{parsed.scheme}' — expected http or https"
            )
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws = f"{ws_scheme}://{parsed.netloc}{parsed.path}"
        return f"{ws}/ws/telnyx-stream?token={token}"

    async def answer(self, call_control_id: str) -> dict[str, Any]:
        """Answer once; call.answered starts media through the shared streaming path."""
        command_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"telnyx:answer:{call_control_id}"))
        data = await self._request(
            "POST", f"/calls/{call_control_id}/actions/answer",
            json={"command_id": command_id},
        )
        return data.get("data") or data

    async def start_streaming(
        self,
        call_control_id: str,
        *,
        stream_url: str,
        target_legs: str = "both",
    ) -> dict[str, Any]:
        """Start or restart bidirectional media stream (fallback if dial-time stream_url failed).

        `both` so answer-time streaming_start actually reaches the callee and
        captures their inbound audio. `self` on outbound after answer is silent.
        """
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

    async def start_recording(
        self,
        call_control_id: str,
        *,
        fmt: str = "wav",
        channels: str = "dual",
    ) -> dict[str, Any]:
        """Start a Telnyx Call Control recording (dual-channel WAV)."""
        data = await self._request(
            "POST",
            f"/calls/{call_control_id}/actions/record_start",
            json={
                "format": fmt,
                "channels": channels,
                "play_beep": False,
                "recording_track": "both",
            },
        )
        return data.get("data") or data

    async def hangup(self, call_control_id: str) -> dict[str, Any]:
        """End an active Telnyx call (dev stress tests / cleanup)."""
        try:
            data = await self._request("POST", f"/calls/{call_control_id}/actions/hangup", json={})
            return data.get("data") or data
        except TelnyxApiError as exc:
            # 404/422: already hung up or control id no longer active.
            if exc.status in (404, 422):
                logger.info(
                    "[TELNYX] hangup skipped control=%s status=%s",
                    call_control_id,
                    exc.status,
                )
                return {}
            raise


class TelnyxCallRegistry:
    """Telnyx call event registry — process memory + optional Redis for multi-worker (1.4)."""

    _REDIS_PREFIX = "voice:telnyx:call:"
    _REDIS_TTL_SEC = 7200

    def __init__(self) -> None:
        self._calls: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def _redis(self):
        try:
            from server.call.redis_memory_cache import _redis

            return _redis()
        except Exception:
            return None

    def upsert(self, call_control_id: str, patch: dict[str, Any]) -> None:
        import time

        # Synchronous upsert is fine for single-threaded asyncio; the lock
        # is used by atomic_upsert for read-modify-write patterns.
        row = dict(self._calls.get(call_control_id) or {"call_control_id": call_control_id})
        first_seen = row.get("first_seen_at")
        row.update(patch)
        if first_seen:
            row["first_seen_at"] = first_seen
        elif not row.get("first_seen_at"):
            row["first_seen_at"] = time.time()
        row["updated_at"] = int(time.time())
        self._calls[call_control_id] = row
        client = self._redis()
        if client is not None:
            try:
                import json

                if callable(getattr(client, "eval", None)):
                    # Merge only the patch in Redis. Publishing a stale local snapshot
                    # otherwise erases another worker's agent/answer/hangup fields.
                    script = """
                    local raw = redis.call('GET', KEYS[1])
                    local row = raw and cjson.decode(raw) or {}
                    local patch = cjson.decode(ARGV[1])
                    for k,v in pairs(patch) do row[k] = v end
                    local merged = cjson.encode(row)
                    redis.call('SET', KEYS[1], merged, 'EX', ARGV[2])
                    return merged
                    """
                    merged = client.eval(script, 1, f"{self._REDIS_PREFIX}{call_control_id}",
                                         json.dumps({
                                             **patch,
                                             "call_control_id": call_control_id,
                                             "updated_at": row["updated_at"],
                                             "first_seen_at": row["first_seen_at"],
                                         }),
                                         self._REDIS_TTL_SEC)
                    self._calls[call_control_id] = json.loads(merged)
                else:
                    client.setex(f"{self._REDIS_PREFIX}{call_control_id}", self._REDIS_TTL_SEC, json.dumps(row))
            except Exception:
                pass

    async def atomic_check_and_set(self, call_control_id: str, key: str, value: Any = True) -> bool:
        """Atomically check if key is falsy, then set it. Returns True if set, False if already set.

        When Redis is configured, uses SET NX for a true cross-worker claim so two
        processes cannot both handle the same call.answered (1.2 + 1.4).
        """
        import json
        import time

        claim_key = f"{self._REDIS_PREFIX}claim:{call_control_id}:{key}"
        async with self._lock:
            client = self._redis()
            if client is not None:
                try:
                    claimed = client.set(claim_key, "1", nx=True, ex=self._REDIS_TTL_SEC)
                    if not claimed:
                        return False
                except Exception:
                    # Fall back to process-local claim if Redis blips.
                    client = None

            row = dict(self.get(call_control_id) or {"call_control_id": call_control_id})
            if row.get(key):
                return False
            row[key] = value
            row["updated_at"] = int(time.time())
            self.upsert(call_control_id, {key: value})
            return True

    def get(self, call_control_id: str) -> dict[str, Any] | None:
        row = self._calls.get(call_control_id)
        client = self._redis()
        if client is None:
            return row
        try:
            import json

            raw = client.get(f"{self._REDIS_PREFIX}{call_control_id}")
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    self._calls[call_control_id] = data
                    return data
        except Exception:
            pass
        return row

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        self._prune_stale()
        rows = sorted(self._calls.values(), key=lambda r: r.get("updated_at") or 0, reverse=True)
        return rows[:limit]

    def _prune_stale(self, *, max_age_s: int = 3600) -> None:
        """Drop completed/orphaned rows so a long-lived process does not leak memory."""
        import time

        now = int(time.time())
        stale = [
            cid
            for cid, row in self._calls.items()
            if (now - int(row.get("updated_at") or 0)) > max_age_s
            and str(row.get("status") or "") in {"completed", "stream-error", "hangup", "failed"}
        ]
        for cid in stale:
            self._calls.pop(cid, None)
            client = self._redis()
            if client is not None:
                try:
                    client.delete(f"{self._REDIS_PREFIX}{cid}")
                except Exception:
                    pass



telnyx_call_registry = TelnyxCallRegistry()


class TelnyxStreamTokens:
    """Stream WS token metadata.

    Process-local by default. When Redis is configured, mirrors tokens so a
    webhook worker and a different WebSocket worker can both resolve agent/tier.
    Process-local-only is single-worker safe — multi-worker requires REDIS_URL.
    """

    _REDIS_PREFIX = "voice:telnyx:stream_token:"
    _REDIS_TTL_SEC = 7200

    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, Any]] = {}

    def _redis(self):
        try:
            from server.call.redis_memory_cache import _redis

            return _redis()
        except Exception:
            return None

    def put(self, token: str, **meta: Any) -> None:
        import time

        meta["_expires_at"] = time.time() + self._REDIS_TTL_SEC
        self._tokens[token] = meta
        client = self._redis()
        if client is not None:
            try:
                import json

                client.setex(
                    f"{self._REDIS_PREFIX}{token}",
                    self._REDIS_TTL_SEC,
                    json.dumps(meta),
                )
            except Exception:
                pass

    def consume(self, token: str) -> dict[str, Any] | None:
        meta = self._tokens.pop(token, None)
        client = self._redis()
        if client is not None:
            try:
                import json

                key = f"{self._REDIS_PREFIX}{token}"
                if meta is None:
                    raw = client.get(key)
                    if raw:
                        data = json.loads(raw)
                        if isinstance(data, dict):
                            meta = data
                client.delete(key)
            except Exception:
                pass
        return meta

    def peek(self, token: str) -> dict[str, Any] | None:
        import time

        meta = self._tokens.get(token)
        if meta is not None and float(meta.get("_expires_at") or 0) <= time.time():
            self._tokens.pop(token, None)
            meta = None
        if meta is not None:
            return meta
        client = self._redis()
        if client is None:
            return None
        try:
            import json

            raw = client.get(f"{self._REDIS_PREFIX}{token}")
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    self._tokens[token] = data
                    return data
        except Exception:
            pass
        return None

    def create(self, **meta: Any) -> str:
        tok = uuid.uuid4().hex
        self.put(tok, **meta)
        return tok


telnyx_stream_tokens = TelnyxStreamTokens()
