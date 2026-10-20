"""Vobiz Voice API & WebSocket Streaming Client — https://vobiz.ai/docs"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from server.config.env import get_settings
from server.config.urls import public_api_base, ws_public_base
from server.services.dev_secrets_store import dev_secrets_store

logger = logging.getLogger(__name__)

VOBIZ_API_BASE = "https://api.vobiz.ai/api/v1"

# Standard Vobiz audio stream settings
VOBIZ_DEFAULT_SAMPLE_RATE = 16000
VOBIZ_DEFAULT_CODEC = "L16"  # PCMU or L16
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_TRUE_VALUES = {"1", "true", "yes", "on"}
_TEST_NUMBER_MARKER_RE = re.compile(
    r"(^|[^a-z0-9])(test|trial|demo|mock|sandbox)([^a-z0-9]|$)", re.IGNORECASE
)


def _is_true(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_VALUES
    if isinstance(value, bool):
        return value
    return value == 1 if isinstance(value, int) else False


def _is_test_number(row: dict[str, Any]) -> bool:
    if any(
        _is_true(row.get(field))
        for field in ("is_trial_number", "is_test_number", "test_mode", "is_mock", "mock")
    ):
        return True
    tags = row.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    marker_text = " ".join(
        str(value)
        for value in [*tags, row.get("source"), row.get("number_type"), row.get("type")]
        if value
    )
    return bool(_TEST_NUMBER_MARKER_RE.search(marker_text))


def _normalize_vobiz_number(row: dict[str, Any]) -> dict[str, Any] | None:
    e164 = str(row.get("e164") or row.get("phone_number") or "").strip()
    if not _E164_RE.fullmatch(e164) or _is_test_number(row):
        return None
    capabilities = row.get("capabilities")
    voice_capability = (
        capabilities.get("voice")
        if isinstance(capabilities, dict) and "voice" in capabilities
        else row.get("voice_enabled")
    )
    if voice_capability is not None and not _is_true(voice_capability):
        return None
    return {
        **row,
        "e164": e164,
        "phone_number": e164,
        "country": str(row.get("country") or "").upper(),
        "status": str(row.get("status") or "").lower(),
        "provider": "vobiz",
        "features": [
            label
            for key, label in (("voice", "Voice"), ("sms", "SMS"))
            if not isinstance(capabilities, dict) or _is_true(capabilities.get(key))
        ],
    }


class VobizConfigError(Exception):
    pass


class VobizApiError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def vobiz_enabled() -> bool:
    return bool(dev_secrets_store.effective("enable_vobiz", get_settings().enable_vobiz))


def _resolve_vobiz_config() -> dict[str, str]:
    settings = get_settings()
    auth_id = dev_secrets_store.effective_secret("vobiz_auth_id") or settings.vobiz_auth_id or ""
    auth_token = dev_secrets_store.effective_secret("vobiz_auth_token") or settings.vobiz_auth_token or ""
    app_id = dev_secrets_store.effective("vobiz_app_id", settings.vobiz_app_id) or ""
    phone = dev_secrets_store.effective("vobiz_phone_number", settings.vobiz_phone_number) or ""
    if not auth_id or not auth_token:
        raise VobizConfigError("VOBIZ_AUTH_ID and VOBIZ_AUTH_TOKEN must be configured")
    return {
        "auth_id": str(auth_id).strip(),
        "auth_token": str(auth_token).strip(),
        "app_id": str(app_id).strip(),
        "phone_number": str(phone).strip(),
    }


class VobizClient:
    def __init__(self, cfg: dict[str, str] | None = None) -> None:
        self.cfg = cfg or _resolve_vobiz_config()

    @property
    def configured(self) -> bool:
        return bool(self.cfg.get("auth_id") and self.cfg.get("auth_token"))

    @property
    def auth_id(self) -> str:
        return str(self.cfg.get("auth_id") or "")

    def _auth(self) -> httpx.BasicAuth:
        return httpx.BasicAuth(self.cfg["auth_id"], self.cfg["auth_token"])

    def _headers(self) -> dict[str, str]:
        return {
            "X-Auth-ID": self.cfg["auth_id"],
            "X-Auth-Token": self.cfg["auth_token"],
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "DialTact-Voice-Agent/1.0",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{VOBIZ_API_BASE}{path}"
        timeout = kwargs.pop("timeout", None)
        retry = kwargs.pop("retry", True)
        if timeout is None:
            timeout = httpx.Timeout(connect=15.0, read=25.0, write=15.0, pool=15.0)

        max_attempts = 1 if not retry or (method.upper() == "POST" and "/Call" in path) else 2
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    r = await client.request(method, url, headers=self._headers(), **kwargs)
                if r.status_code >= 400:
                    raise VobizApiError(
                        f"Vobiz API {r.status_code}: {r.text[:300]}",
                        status=r.status_code,
                        body=r.text[:800],
                    )
                if not r.content:
                    return {}
                return r.json()
            except httpx.TimeoutException as exc:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.3)
                    continue
                raise VobizApiError(
                    f"Vobiz API timeout ({exc.__class__.__name__})",
                    status=None,
                    body=str(exc)[:400],
                ) from exc
            except httpx.HTTPError as exc:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.3)
                    continue
                raise VobizApiError(
                    f"Vobiz API transport error ({exc.__class__.__name__})",
                    status=None,
                    body=str(exc)[:400],
                ) from exc

    async def create_customer_subaccount(
        self, *, name: str, email: str, business_type: str, description: str
    ) -> dict[str, Any]:
        """Create a KYC-gated tenant subaccount; a lost response is not retried."""
        parent_auth_id = quote(self.cfg["auth_id"], safe="")
        return await self._request(
            "POST",
            f"/accounts/{parent_auth_id}/sub-accounts/",
            json={
                "name": name,
                "email": email,
                "description": description,
                "kyc_mode": "customer_use",
                "business_type": business_type,
            },
            retry=False,
            timeout=httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=3.0),
        )

    async def create_customer_kyc_session(
        self, *, sub_auth_id: str, redirect_url: str, webhook_url: str | None = None
    ) -> dict[str, Any]:
        raw_sub_auth_id = sub_auth_id
        sub_auth_id = quote(raw_sub_auth_id, safe="")
        return await self._request(
            "POST",
            f"/sub-accounts/{sub_auth_id}/kyc-sessions",
            json={
                "account_auth_id": raw_sub_auth_id,
                "flow_type": "redirect",
                "redirect_url": redirect_url,
                **({"webhook_url": webhook_url} if webhook_url else {}),
            },
            retry=False,
            timeout=httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=3.0),
        )

    async def get_customer_kyc_status(self, sub_auth_id: str) -> dict[str, Any]:
        sub_auth_id = quote(sub_auth_id, safe="")
        return await self._request(
            "GET",
            f"/sub-accounts/{sub_auth_id}/kyc/status",
            timeout=httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=3.0),
        )

    async def get_customer_subaccount(self, sub_auth_id: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/accounts/{quote(self.auth_id, safe='')}/sub-accounts/{quote(sub_auth_id, safe='')}",
            timeout=httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=3.0),
        )

    async def ensure_default_application(self, *, name: str, app_id: str | None = None) -> str:
        """Use the account's default app for inbound DIDs; never a parent's app ID."""
        path = f"/Account/{quote(self.auth_id, safe='')}/Application/"
        if not app_id:
            data = await self._request("GET", path)
            apps = data.get("objects", data.get("applications", data.get("items", [])))
            matches = [a for a in apps if a.get("app_name") == name] if isinstance(apps, list) else []
            if len(matches) > 1:
                raise VobizConfigError("Duplicate voice applications require reconciliation")
            if matches:
                app_id = str(matches[0].get("app_id") or "")
            else:
                data = await self._request(
                    "POST", path, json={"app_name": name, "answer_url": f"{public_api_base()}/api/vobiz/answer",
                                       "answer_method": "POST"}, retry=False,
                )
                app_id = str(data.get("app_id") or "")
        if not app_id:
            raise VobizConfigError("Voice application confirmation unavailable")
        await self.update_application(app_id=app_id, app_name=name, default_number_app=True)
        return app_id

    async def release_owned_number(self, e164: str) -> dict[str, Any]:
        return await self._request(
            "DELETE", f"/Account/{quote(self.auth_id, safe='')}/numbers/{quote(e164, safe='')}", retry=False,
        )

    async def assign_number_to_subaccount(self, *, e164: str, sub_auth_id: str) -> dict[str, Any]:
        """Assign a newly purchased parent-pool DID using the documented endpoint."""
        parent_auth_id = quote(self.cfg["auth_id"], safe="")
        encoded_number = quote(e164, safe="")
        return await self._request(
            "POST",
            f"/account/{parent_auth_id}/numbers/{encoded_number}/assign-subaccount",
            json={"sub_account_id": sub_auth_id},
            retry=False,
            timeout=httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=3.0),
        )

    async def handshake(self) -> dict[str, Any]:
        """Test API credentials with Vobiz account lookup."""
        auth_id = self.cfg["auth_id"]
        try:
            # Query active verified user profile from /auth/me
            data = await self._request("GET", "/auth/me")
            return {
                "ok": True,
                "provider": "vobiz",
                "auth_id": auth_id,
                "account_id": data.get("id"),
                "phone_number": self.cfg.get("phone_number") or None,
                "app_id": self.cfg.get("app_id") or None,
                "account_name": data.get("name") or data.get("company") or None,
                "email": data.get("email"),
                "verified": data.get("is_verified", True),
                "pricing_tier": data.get("pricing_tier", {}).get("name"),
            }
        except Exception as e:
            logger.warning("Phone account check failed error_type=%s", type(e).__name__)
            return {
                "ok": False,
                "provider": "vobiz",
                "auth_id": auth_id,
                "error": str(e)[:300],
            }

    async def create_outbound_call(
        self,
        *,
        to: str,
        from_: str | None = None,
        answer_url: str | None = None,
        hangup_url: str | None = None,
        fallback_url: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Trigger an outbound call through Vobiz REST API."""
        auth_id = self.cfg["auth_id"]
        base_api = public_api_base()
        caller_id = (from_ or self.cfg.get("phone_number") or "+917965480745").strip()

        # Normalize destination and caller ID to E.164
        dest = to.strip()
        if not dest.startswith("+"):
            digits = "".join(c for c in dest if c.isdigit())
            if len(digits) == 10:
                dest = f"+91{digits}"
            elif len(digits) == 12 and digits.startswith("91"):
                dest = f"+{digits}"
            else:
                dest = f"+{digits}" if digits else dest

        if not caller_id.startswith("+"):
            c_digits = "".join(c for c in caller_id if c.isdigit())
            if len(c_digits) == 10:
                caller_id = f"+91{c_digits}"
            elif len(c_digits) == 12 and c_digits.startswith("91"):
                caller_id = f"+{c_digits}"
            else:
                caller_id = f"+{c_digits}" if c_digits else caller_id

        ans_url = answer_url or f"{base_api}/api/vobiz/answer"
        hup_url = hangup_url or f"{base_api}/api/vobiz/hangup"
        app_id = None if self.cfg.get("disable_app_id") == "true" else (
            self.cfg.get("app_id") or "19573358086719545"
        )

        payload: dict[str, Any] = {
            "to": dest,
            "from": caller_id,
            "answer_url": ans_url,
            "answer_method": "POST",
            "hangup_url": hup_url,
            "hangup_method": "POST",
        }
        if fallback_url:
            payload["fallback_url"] = fallback_url
            payload["fallback_method"] = "POST"
        if app_id:
            payload["app_id"] = app_id
        if extra_params:
            payload.update(extra_params)

        try:
            res = await self._request("POST", f"/Account/{auth_id}/Call/", json=payload)
            return res
        except VobizApiError as exc:
            # If carrier rejects newly configured domain (e.g. DNS/SSL propagation in flight),
            # fall back safely so outbound calls do not fail.
            if (self.cfg.get("disable_app_id") != "true"
                    and "not a valid URL" in str(exc) and "dialtact.com" in ans_url):
                logger.warning(
                    "[VOBIZ] dialtact.com webhook not accepted by carrier yet; retrying with secondary fallback URL"
                )
                fallback_base = getattr(get_settings(), "vobiz_fallback_webhook_base_url", "https://api-dev.hustlelabs.in")
                payload["answer_url"] = f"{fallback_base}/api/vobiz/answer"
                payload["hangup_url"] = f"{fallback_base}/api/vobiz/hangup"
                return await self._request("POST", f"/Account/{auth_id}/Call/", json=payload)
            raise

    async def update_application(
        self,
        *,
        app_id: str | None = None,
        answer_url: str | None = None,
        hangup_url: str | None = None,
        fallback_answer_url: str | None = None,
        app_name: str | None = None,
        default_number_app: bool | None = None,
    ) -> dict[str, Any]:
        """Update Vobiz voice application callback URLs."""
        auth_id = self.cfg["auth_id"]
        target_app_id = (app_id or self.cfg.get("app_id") or "19573358086719545").strip()
        base_api = public_api_base()
        ans = answer_url or f"{base_api}/api/vobiz/answer"
        hup = hangup_url or f"{base_api}/api/vobiz/hangup"
        fb = fallback_answer_url or f"{base_api}/api/vobiz/fallback"
        payload: dict[str, Any] = {
            "answer_url": ans,
            "answer_method": "POST",
            "hangup_url": hup,
            "hangup_method": "POST",
            "fallback_answer_url": fb,
            "fallback_method": "POST",
        }
        if app_name is not None:
            payload["app_name"] = app_name
        if default_number_app is not None:
            payload["default_number_app"] = default_number_app
        return await self._request("POST", f"/Account/{auth_id}/Application/{target_app_id}/", json=payload)

    async def hangup_call(self, call_uuid: str) -> dict[str, Any]:
        """Terminate a live call on Vobiz."""
        auth_id = self.cfg["auth_id"]
        try:
            return await self._request("DELETE", f"/Account/{auth_id}/Call/{call_uuid}/")
        except VobizApiError as exc:
            if exc.status in (404, 422):
                return {"ok": True, "already_ended": True}
            raise

    def build_stream_ws_url(self, token: str, call_uuid: str | None = None) -> str:
        """Construct secure WebSocket URL for Vobiz media streaming."""
        base = ws_public_base()
        query = {"token": token}
        if call_uuid:
            query["call_uuid"] = call_uuid
        return f"{base}/ws/vobiz-stream?{urlencode(query)}"

    async def get_call_cdr(self, call_uuid: str) -> dict[str, Any]:
        """Retrieve authoritative talk seconds and per-call cost, excluding ringing."""
        parsed = str(uuid.UUID(str(call_uuid)))
        return await self._request("GET", f"/Account/{self.auth_id}/cdr/{parsed}", timeout=httpx.Timeout(2.5))

    async def get_balance(self) -> dict[str, Any]:
        """Fetch account balance from Vobiz."""
        auth_id = self.cfg["auth_id"]
        try:
            data = await self._request("GET", f"/account/{auth_id}/balance")
            balances = data.get("balances") or []
            if balances:
                bal = float(balances[0].get("balance", 0.0))
                curr = balances[0].get("currency", "INR")
                return {"ok": True, "balance": bal, "currency": curr}
            return {"ok": True, "balance": 0.0, "currency": "INR"}
        except Exception as e:
            logger.warning(
                "[VOBIZ] balance fetch fallback error_type=%s",
                type(e).__name__,
            )
            from server.config.env import get_settings
            env = getattr(get_settings(), "environment", "development")
            if env in ("development", "test", "staging"):
                return {"ok": True, "balance": 0.0, "currency": "INR", "fallback": True}
            return {
                "ok": False,
                "balance": 0.0,
                "currency": "INR",
                "error": type(e).__name__,
            }

    async def list_account_numbers(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List numbers already assigned to this account (not numbers for sale)."""
        auth_id = self.cfg["auth_id"]
        requested = max(0, min(int(limit), 1000))
        if requested == 0:
            return []
        per_page = min(100, requested)
        results: list[dict[str, Any]] = []
        page = 1
        total: int | None = None
        while len(results) < requested:
            params: dict[str, Any] = {"page": page, "per_page": per_page}
            if search:
                params["search"] = search
            data = await self._request(
                "GET", f"/Account/{auth_id}/numbers", params=params
            )
            items = data.get("items") or []
            if not isinstance(items, list):
                raise VobizApiError("Vobiz account number list returned an invalid response")
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                item = _normalize_vobiz_number(raw)
                if item is None:
                    # Keep test/trial numbers out of all account-number consumers.
                    continue
                item["account_id"] = str(raw.get("account_id") or raw.get("auth_id") or "")
                item["id"] = raw.get("id")
                item["region"] = raw.get("region")
                item["monthly_fee"] = raw.get("monthly_fee")
                item["setup_fee"] = raw.get("setup_fee")
                item["currency"] = raw.get("currency")
                item["is_trial_number"] = _is_true(raw.get("is_trial_number"))
                results.append(item)
                if len(results) >= requested:
                    break
            try:
                total = int(data.get("total")) if data.get("total") is not None else total
            except (TypeError, ValueError):
                pass
            if not items or (total is not None and page * per_page >= total):
                break
            page += 1
        return results

    async def search_available_numbers(
        self,
        country: str = "IN",
        limit: int = 10,
        number_type: str = "Local DID",
    ) -> list[dict[str, Any]]:
        """List live, unassigned Vobiz inventory numbers eligible for purchase."""
        country_norm = country.strip().upper()
        requested = max(0, min(int(limit), 1000))
        if requested == 0:
            return []
        auth_id = self.cfg["auth_id"]
        per_page = min(100, max(25, requested))
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        total: int | None = None
        while len(results) < requested:
            params: dict[str, Any] = {"page": page, "per_page": per_page}
            if country_norm and country_norm != "ALL":
                params["country"] = country_norm
            data = await self._request(
                "GET", f"/Account/{auth_id}/inventory/numbers", params=params
            )
            items = data.get("items") or []
            if not isinstance(items, list):
                raise VobizApiError("Vobiz inventory returned an invalid response")
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                row = _normalize_vobiz_number(raw)
                if row is None or row["status"] != "active":
                    continue
                # Inventory must be unassigned. The API guarantees auth_id=NULL;
                # keep the guard here in case an upstream response is malformed.
                if raw.get("auth_id") not in (None, ""):
                    continue
                if country_norm and country_norm != "ALL" and row["country"] != country_norm:
                    continue
                if row["e164"] in seen:
                    continue
                seen.add(row["e164"])
                results.append(row)
                if len(results) >= requested:
                    break
            try:
                total = int(data.get("total")) if data.get("total") is not None else total
            except (TypeError, ValueError):
                pass
            if not items or (total is not None and page * per_page >= total):
                break
            page += 1
        return results

    async def place_number_order(self, phone_number: str) -> dict[str, Any]:
        """Purchase an exact number from Vobiz inventory, idempotently."""
        e164 = str(phone_number or "").strip()
        if not _E164_RE.fullmatch(e164):
            raise ValueError("invalid_e164")
        auth_id = self.cfg["auth_id"]

        async def find_owned_active_number() -> dict[str, Any] | None:
            owned_rows = await self.list_account_numbers(search=e164, limit=25)
            for row in owned_rows:
                if row["e164"] != e164:
                    continue
                if row.get("account_id") != auth_id or row.get("is_trial_number"):
                    raise VobizApiError("Vobiz number is not owned by the purchasing account")
                if row.get("status") != "active":
                    raise VobizApiError("Vobiz number is not active")
                number_id = str(row.get("id") or "").strip()
                if not number_id:
                    raise VobizApiError("Vobiz did not return a provider number ID")
                return {
                    "ok": True,
                    "phone_number": e164,
                    "id": number_id,
                    "status": "active",
                    "already_owned": True,
                }
            return None

        already_owned = await find_owned_active_number()
        if already_owned is not None:
            return already_owned

        try:
            response = await self._request(
                "POST",
                f"/Account/{auth_id}/numbers/purchase-from-inventory",
                json={"e164": e164},
                retry=False,
            )
        except Exception:
            # A timeout can happen after Vobiz accepted the purchase. Reconcile
            # against the owned-number endpoint before the durable job retries.
            try:
                owned = await find_owned_active_number()
            except Exception:
                raise
            if owned is not None:
                return owned
            raise

        purchased = response.get("number") if isinstance(response, dict) else None
        if isinstance(purchased, dict):
            returned_e164 = str(purchased.get("e164") or "").strip()
            returned_account = str(purchased.get("account_id") or "").strip()
            number_id = str(purchased.get("id") or "").strip()
            status = str(purchased.get("status") or "").strip().lower()
            if (
                returned_e164 == e164
                and returned_account == auth_id
                and number_id
                and status == "active"
                and not _is_test_number(purchased)
            ):
                return {
                    "ok": True,
                    "phone_number": e164,
                    "id": number_id,
                    "status": "active",
                    "details": response,
                }

        # Do not invent an ID or mark the line provisioned when the documented
        # provider purchase response is incomplete. Reconcile first in case the
        # number was bought but the response body was lost or malformed.
        try:
            owned = await find_owned_active_number()
        except Exception:
            raise
        if owned is not None:
            return owned
        raise VobizApiError("Vobiz did not confirm the purchased number")

    async def provision_ordered_number(self, phone_number: str) -> dict[str, Any]:
        """Order number + link to Vobiz voice application for inbound calls."""
        order = await self.place_number_order(phone_number)
        clean = phone_number.strip().lstrip("+")
        app_id = self.cfg.get("app_id")
        if app_id:
            try:
                auth_id = self.cfg["auth_id"]
                await self._request("POST", f"/Account/{auth_id}/Number/{clean}/", json={"app_id": app_id})
            except Exception as e:
                logger.debug(
                    "[VOBIZ] app linking notice error_type=%s",
                    type(e).__name__,
                )
        phone_number_id = order.get("id") if isinstance(order, dict) else None
        if not phone_number_id:
            raise VobizApiError("Vobiz did not confirm a provider number ID")
        return {
            "ok": True,
            "order": order,
            "phone_number_id": str(phone_number_id),
            "e164": phone_number,
            "provider": "vobiz",
        }


class VobizCallRegistry:
    """Thread-safe and Redis-mirrored call session store for Vobiz calls."""

    _REDIS_PREFIX = "voice:vobiz:call:"
    _REDIS_RECENT_KEY = "voice:vobiz:calls:recent"
    _REDIS_TTL_SEC = 7200

    def __init__(self) -> None:
        from collections import OrderedDict
        from threading import RLock
        self._calls = OrderedDict()
        self._cache_lock = RLock()
        self._lock = asyncio.Lock()
        self._max_local_calls = 2048

    def _remember(self, call_uuid, row):
        import time
        with self._cache_lock:
            self._calls[call_uuid] = dict(row)
            self._calls.move_to_end(call_uuid)
            cutoff = time.time() - self._REDIS_TTL_SEC
            while self._calls:
                oldest = next(iter(self._calls.values()))
                if len(self._calls) <= self._max_local_calls and float(oldest.get("updated_at") or 0) > cutoff:
                    break
                self._calls.popitem(last=False)

    def _redis(self):
        try:
            from server.call.redis_memory_cache import _redis

            return _redis()
        except Exception:
            return None

    def get(self, call_uuid: str) -> dict[str, Any] | None:
        import json, time
        if not call_uuid:
            return None
        client = self._redis()
        shared = str(getattr(get_settings(), "app_environment", "development")).lower() in ("production", "staging")
        seen = set()
        for _ in range(8):
            if call_uuid in seen:
                return None
            seen.add(call_uuid)
            if client is not None:
                try:
                    raw = client.get(f"{self._REDIS_PREFIX}{call_uuid}")
                    row = json.loads(raw) if raw else None
                except Exception:
                    return None
            elif shared:
                return None
            else:
                with self._cache_lock:
                    row = self._calls.get(call_uuid)
            if not isinstance(row, dict) or float(row.get("updated_at") or 0) <= time.time() - self._REDIS_TTL_SEC:
                return None
            target = row.get("aliased_to")
            if not target or target == call_uuid:
                return dict(row)
            call_uuid = str(target)
        return None

    def alias(self, alias_id: str, target_id: str) -> None:
        """Map a secondary identifier (like request_uuid) to an authoritative CallUUID."""
        if not alias_id or not target_id or alias_id == target_id:
            return
        target = self.get(target_id) or {}
        self.upsert(alias_id, {**target, "aliased_to": target_id, "call_uuid": target_id})

    def upsert(self, call_uuid: str, updates: dict[str, Any]) -> dict[str, Any]:
        import json, time
        from redis.exceptions import WatchError
        if not call_uuid:
            return {}
        client = self._redis()
        if client is not None:
            key = f"{self._REDIS_PREFIX}{call_uuid}"
            for attempt in range(8):
                try:
                    with client.pipeline() as pipe:
                        pipe.watch(key)
                        raw = pipe.get(key)
                        existing = json.loads(raw) if raw else {}
                        merged = {**existing, **updates, "call_uuid": call_uuid, "updated_at": int(time.time())}
                        if existing.get("ended"):
                            merged["ended"] = True
                        pipe.multi()
                        pipe.set(key, json.dumps(merged), ex=self._REDIS_TTL_SEC)
                        pipe.zadd(self._REDIS_RECENT_KEY, {call_uuid: time.time()})
                        pipe.zremrangebyscore(self._REDIS_RECENT_KEY, "-inf", time.time() - self._REDIS_TTL_SEC)
                        pipe.execute()
                    self._remember(call_uuid, merged)
                    return dict(merged)
                except WatchError:
                    if attempt < 7:
                        time.sleep(min(0.025, 0.001 * (2 ** attempt)))
                        continue
                    raise VobizConfigError("Concurrent call metadata update needs retry")
                except Exception as exc:
                    raise VobizConfigError("Shared call metadata storage is unavailable") from exc
        if str(getattr(get_settings(), "app_environment", "development")).lower() in ("production", "staging"):
            raise VobizConfigError("Shared call metadata storage is unavailable")
        with self._cache_lock:
            existing = self._calls.get(call_uuid) or {}
            merged = {**existing, **updates, "call_uuid": call_uuid, "updated_at": int(time.time())}
            if existing.get("ended"):
                merged["ended"] = True
            self._remember(call_uuid, merged)
        return dict(merged)

    async def atomic_check_and_set(self, call_uuid: str, key: str, value: Any = True) -> bool:
        import hashlib
        client = await asyncio.to_thread(self._redis)
        if client is not None:
            claim = hashlib.sha256(f"{call_uuid}:{key}".encode()).hexdigest()
            try:
                won = await asyncio.to_thread(client.set, f"{self._REDIS_PREFIX}claim:{claim}", "1", nx=True, ex=self._REDIS_TTL_SEC)
                if not won:
                    return False
                await asyncio.to_thread(self.upsert, call_uuid, {key: value})
                return True
            except Exception:
                return False
        if str(getattr(get_settings(), "app_environment", "development")).lower() in ("production", "staging"):
            return False
        async with self._lock:
            row = self.get(call_uuid) or {}
            if row.get(key):
                return False
            self.upsert(call_uuid, {key: value})
            return True

    def list_recent(self, limit: int | None = 20) -> list[dict[str, Any]]:
        import time
        by_id: dict[str, dict[str, Any]] = {}
        with self._cache_lock:
            local_rows = list(self._calls.values())
        for row in local_rows:
            cid = str(row.get("call_uuid") or "")
            if cid and float(row.get("updated_at") or 0) > time.time() - self._REDIS_TTL_SEC:
                by_id[cid] = row
        client = self._redis()
        if client is not None:
            try:
                import json

                for cid in client.zrevrange(self._REDIS_RECENT_KEY, 0, -1 if limit is None else max(limit * 3, 40) - 1):
                    if isinstance(cid, bytes):
                        cid = cid.decode("utf-8")
                    raw = client.get(f"{self._REDIS_PREFIX}{cid}")
                    if not raw:
                        continue
                    data = json.loads(raw)
                    if isinstance(data, dict) and data.get("call_uuid"):
                        by_id[str(data["call_uuid"])] = data
            except Exception as exc:
                logger.debug("[VOBIZ] list_recent redis failed: %s", exc)
        ordered = sorted(
            by_id.values(),
            key=lambda r: float(r.get("updated_at") or r.get("dialed_at") or 0),
            reverse=True,
        )
        selected = ordered if limit is None else ordered[:limit]
        return [{key: value for key, value in row.items() if key not in {"token", "webhook_token", "stream_url"}} for row in selected]


vobiz_call_registry = VobizCallRegistry()


class VobizStreamTokens:
    """Call-scoped media credentials, consumed once across all shared workers."""
    _REDIS_PREFIX = "voice:vobiz:stream_token:"
    _REDIS_TTL_SEC = 7200

    def __init__(self):
        import threading
        self._tokens = {}
        self._used = {}
        self._lock = threading.Lock()

    def _redis(self):
        from server.call.redis_memory_cache import _redis
        return _redis()

    def _shared_required(self):
        return str(getattr(get_settings(), "app_environment", "development")).lower() in ("production", "staging")

    def _client(self):
        client = self._redis()
        if self._shared_required() and (client is None or type(client).__module__.startswith("fakeredis")):
            raise VobizConfigError("Shared call authentication storage is unavailable")
        return client

    def create(self, **meta):
        import secrets
        token = secrets.token_urlsafe(32)
        self.put(token, **meta)
        return token

    def put(self, token, **meta):
        import json, time
        meta["_expires_at"] = time.time() + self._REDIS_TTL_SEC
        client = self._client()
        if client is not None:
            # Retain the used-token marker when callbacks update metadata.
            if client.get(f"{self._REDIS_PREFIX}{token}:used"):
                return
            client.set(f"{self._REDIS_PREFIX}{token}", json.dumps(meta), ex=self._REDIS_TTL_SEC)
            return
        with self._lock:
            if self._used.get(token, 0) > time.time():
                return
            self._tokens = {key: value for key, value in self._tokens.items() if float(value.get("_expires_at") or 0) > time.time()}
            self._used = {key: expiry for key, expiry in self._used.items() if expiry > time.time()}
            self._tokens[token] = dict(meta)

    def peek(self, token):
        import json, time
        if not token:
            return None
        try:
            client = self._client()
            if client is not None:
                raw = client.get(f"{self._REDIS_PREFIX}{token}")
                meta = json.loads(raw) if raw else None
            else:
                with self._lock:
                    meta = self._tokens.get(token)
            return dict(meta) if isinstance(meta, dict) and float(meta.get("_expires_at") or 0) > time.time() else None
        except Exception:
            return None

    def consume(self, token):
        import json, time
        if not token:
            return None
        try:
            client = self._client()
            if client is not None:
                key = f"{self._REDIS_PREFIX}{token}"
                # Do not allocate claim keys for arbitrary unauthenticated input.
                if not client.get(key):
                    return None
                if not client.set(f"{key}:used", "1", nx=True, ex=self._REDIS_TTL_SEC):
                    return None
                raw = client.getdel(key)
                meta = json.loads(raw) if raw else None
                with self._lock:
                    self._tokens.pop(token, None)
            else:
                with self._lock:
                    if self._used.get(token, 0) > time.time():
                        return None
                    meta = self._tokens.pop(token, None)
                    if meta:
                        self._used[token] = float(meta.get("_expires_at") or 0)
            if isinstance(meta, dict) and float(meta.get("_expires_at") or 0) > time.time():
                return dict(meta)
        except Exception:
            # No process-local fallback after a shared-store failure: another
            # worker may already have consumed this credential.
            return None
        return None


vobiz_stream_tokens = VobizStreamTokens()
