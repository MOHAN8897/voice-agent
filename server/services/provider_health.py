"""Provider health: classify vendor failures and keep one incident per outage.

Every stack component (LLM, STT, TTS, telephony, integrations, payments) reports
its real failure points here. A storm of identical failures becomes one incident
with a count, the calls and tenants it touched, and the key slot in use, so the
admin panel can say "Sarvam: out of credits on the primary key — now using the
backup key" instead of a silent "the agent could not get ready".

Nothing here ever stores or returns an API key. Only slot names
("primary", "secondary-1", ...) leave this module.

Error signals per provider (checked against vendor docs, 2026-10):
- Sarvam (docs.sarvam.ai/api-reference-docs/errors-troubleshooting): body
  ``{"error": {"code", "message"}}``. 402 ``insufficient_quota_error`` (credits
  empty; older docs list it under 429), 403 ``invalid_api_key_error``, 429
  ``rate_limit_exceeded_error`` / ``model_rate_limit_exceeded_error`` /
  ``audio_duration_busy_error`` (short limits), 429 ``seat_budget_exhausted_error``
  (spend budget used), 500 ``internal_server_error``, 502 ``model_call_failed``,
  503 ``model_overloaded`` / ``rate_limit_exceeded_error``.
- OpenAI: 401 ``invalid_api_key``; 429 ``insufficient_quota`` (billing) versus
  429 ``rate_limit_exceeded``; 5xx unavailable.
- Gemini: 400 ``API_KEY_INVALID`` / 403 ``PERMISSION_DENIED``; 429
  ``RESOURCE_EXHAUSTED`` (quota); billing disabled shows as 403/400 "billing".
- Cartesia: 401 invalid key; 402 payment required (credits); 429 rate/concurrency.
- Deepgram: 401 ``INVALID_AUTH``; 402 ``ASR_PAYMENT_REQUIRED``; 429.
- ElevenLabs: 401 with ``quota_exceeded`` (credits) or ``invalid_api_key``.
- Vobiz / Telnyx: 401/403 auth; low balance as "insufficient balance" text or
  Telnyx 402/10010-style codes; 5xx unavailable.
- Nango: 401 invalid secret key; Razorpay: 401 "Authentication failed".
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.utils.logger import logger

# ------------------------------------------------------------------ categories

CREDITS = "credits_exhausted"
QUOTA = "quota_limited"
AUTH = "auth_invalid"
RATE = "rate_limited"
UNAVAILABLE = "unavailable"
TIMEOUT = "timeout"
BAD_REQUEST = "bad_request"
MISCONFIGURED = "misconfigured"

CATEGORIES = (CREDITS, QUOTA, AUTH, RATE, UNAVAILABLE, TIMEOUT, BAD_REQUEST, MISCONFIGURED)
# A key that answers with one of these is dead for this account until topped
# up / replaced; another key is worth trying for the same request.
KEY_FAILOVER_CATEGORIES = frozenset({CREDITS, QUOTA, AUTH})
# Categories that stop calls outright when no backup exists.
HARD_CATEGORIES = frozenset({CREDITS, QUOTA, AUTH, MISCONFIGURED})

CATEGORY_LABEL = {
    CREDITS: "out of credits",
    QUOTA: "usage quota or spend budget reached",
    AUTH: "API key rejected (invalid, expired or revoked)",
    RATE: "rate limited",
    UNAVAILABLE: "service unavailable or erroring",
    TIMEOUT: "timing out",
    BAD_REQUEST: "rejecting our requests (bad request)",
    MISCONFIGURED: "not configured",
}

COMPONENTS = ("llm", "stt", "tts", "telephony", "integrations", "payments")

PROVIDER_LABEL = {
    "sarvam": "Sarvam",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "deepseek": "DeepSeek",
    "cartesia": "Cartesia",
    "gnani": "Gnani",
    "elevenlabs": "ElevenLabs",
    "deepgram": "Deepgram",
    "vobiz": "Vobiz",
    "telnyx": "Telnyx",
    "nango": "Nango",
    "razorpay": "Razorpay",
}

# Vendor-specific body codes, checked before the HTTP status.
_BODY_CODES: dict[str, str] = {
    # Sarvam
    "insufficient_quota_error": CREDITS,
    "seat_budget_exhausted_error": QUOTA,
    "invalid_api_key_error": AUTH,
    "rate_limit_exceeded_error": RATE,
    "model_rate_limit_exceeded_error": RATE,
    "audio_duration_busy_error": RATE,
    "model_overloaded": UNAVAILABLE,
    "model_call_failed": UNAVAILABLE,
    "internal_server_error": UNAVAILABLE,
    "invalid_request_error": BAD_REQUEST,
    "unprocessable_entity_error": BAD_REQUEST,
    # OpenAI
    "insufficient_quota": CREDITS,
    "billing_hard_limit_reached": CREDITS,
    "invalid_api_key": AUTH,
    "rate_limit_exceeded": RATE,
    # Gemini
    "api_key_invalid": AUTH,
    "permission_denied": AUTH,
    "resource_exhausted": QUOTA,
    # Deepgram / ElevenLabs
    "asr_payment_required": CREDITS,
    "invalid_auth": AUTH,
    "quota_exceeded": CREDITS,
}

_CREDIT_WORDS = re.compile(
    r"insufficient[_ ](?:quota|credit|balance|funds)|out of credits|no credits|credits? (?:exhausted|depleted)"
    r"|payment required|balance (?:is )?too low|low balance|insufficient balance|recharge|top[- ]?up",
    re.IGNORECASE,
)
_QUOTA_WORDS = re.compile(r"quota|spend(?:ing)? (?:limit|budget)|budget exhausted|billing", re.IGNORECASE)
_AUTH_WORDS = re.compile(
    r"invalid[_ ]api[_ ]key|api key not valid|unauthori[sz]ed|authentication failed|invalid[_ ]auth"
    r"|key (?:is )?(?:invalid|expired|revoked)|forbidden",
    re.IGNORECASE,
)
_HTTP_STATUS = re.compile(r"\bHTTP[ /]?(?:status )?(\d{3})\b|\((?:HTTP )?(\d{3})\)", re.IGNORECASE)


def _body_text(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, (bytes, bytearray)):
        return bytes(body[:4000]).decode("utf-8", errors="ignore")
    if isinstance(body, (dict, list)):
        try:
            return json.dumps(body)[:4000]
        except Exception:
            return str(body)[:4000]
    return str(body)[:4000]


def _body_code(text: str) -> str | None:
    """Pull the vendor error code out of a JSON error body."""
    if not text or "{" not in text:
        return None
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    candidates: list[str] = []
    if isinstance(payload, dict):
        err = payload.get("error")
        detail = payload.get("detail")
        for node in (err, detail, payload):
            if isinstance(node, dict):
                for field in ("code", "status", "type", "reason", "err_code"):
                    value = node.get(field)
                    if isinstance(value, str):
                        candidates.append(value)
                details = node.get("details")
                if isinstance(details, list):
                    for item in details:
                        if isinstance(item, dict) and isinstance(item.get("reason"), str):
                            candidates.append(item["reason"])
            elif isinstance(node, str) and node is not payload:
                candidates.append(node)
    else:
        candidates.extend(re.findall(r'"(?:code|status|reason|type)"\s*:\s*"([A-Za-z_]+)"', text))
    for raw in candidates:
        key = raw.strip().lower()
        if key in _BODY_CODES:
            return key
    return None


def classify(provider: str = "", *, status: int | None = None, body: Any = None, message: str = "") -> str:
    """Map a vendor answer to one category. Body codes win over the status."""
    text = f"{_body_text(body)} {message or ''}".strip()
    code = _body_code(_body_text(body))
    if code:
        category = _BODY_CODES[code]
        # Gemini RESOURCE_EXHAUSTED is also used for short per-minute limits.
        if code == "resource_exhausted" and not re.search(r"quota|billing|limit: 0", text, re.IGNORECASE):
            return RATE
        return category
    if status == 402:
        return CREDITS
    if status in (401, 403):
        if _CREDIT_WORDS.search(text):
            return CREDITS
        if re.search(r"quota_exceeded|quota exceeded", text, re.IGNORECASE):
            return CREDITS
        return AUTH
    if status == 429:
        if _CREDIT_WORDS.search(text):
            return CREDITS
        if _QUOTA_WORDS.search(text):
            return QUOTA
        return RATE
    if status in (408, 504):
        return TIMEOUT
    if status is not None and 500 <= status < 600:
        return UNAVAILABLE
    if status is not None and 400 <= status < 500:
        if _CREDIT_WORDS.search(text):
            return CREDITS
        if re.search(r"api key not valid|api_key_invalid", text, re.IGNORECASE):
            return AUTH
        return BAD_REQUEST
    # No status: judge the words.
    if _CREDIT_WORDS.search(text):
        return CREDITS
    if _AUTH_WORDS.search(text):
        return AUTH
    if re.search(r"timed? ?out|timeout", text, re.IGNORECASE):
        return TIMEOUT
    if re.search(r"not configured|missing api key|no api key", text, re.IGNORECASE):
        return MISCONFIGURED
    return UNAVAILABLE


class ProviderFailure(RuntimeError):
    """A classified vendor failure. ``str()`` keeps the legacy message."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        component: str,
        category: str,
        status: int | None = None,
        key_slot: str | None = None,
        all_keys_failed: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.component = component
        self.category = category
        self.status = status
        self.key_slot = key_slot
        self.all_keys_failed = all_keys_failed


def _status_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value < 600:
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None) or getattr(response, "status", None)
    if isinstance(value, int) and 100 <= value < 600:
        return value
    match = _HTTP_STATUS.search(str(exc))
    if match:
        return int(match.group(1) or match.group(2))
    return None


_PROVIDER_HINTS = (
    ("sarvam", "sarvam"), ("openai", "openai"), ("gemini", "gemini"), ("google", "gemini"),
    ("cartesia", "cartesia"), ("gnani", "gnani"), ("elevenlabs", "elevenlabs"), ("deepgram", "deepgram"),
    ("vobiz", "vobiz"), ("telnyx", "telnyx"), ("nango", "nango"), ("razorpay", "razorpay"),
    ("deepseek", "deepseek"),
)


def _provider_hint(text: str) -> str | None:
    lower = text.lower()
    for needle, provider in _PROVIDER_HINTS:
        if needle in lower:
            return provider
    return None


def provider_failure_from(exc: BaseException | None, *, provider: str | None = None,
                          component: str | None = None) -> ProviderFailure | None:
    """Find the vendor failure behind an exception chain, or None.

    Only evidence counts: a ProviderFailure, an AppError naming a provider, or
    an exception whose message names a provider. A bare TimeoutError from our
    own code is not a vendor failure.
    """
    try:
        from server.utils.errors import AppError
    except Exception:  # pragma: no cover
        AppError = ()  # type: ignore[assignment]
    seen: set[int] = set()
    node = exc
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if isinstance(node, ProviderFailure):
            return node
        app_provider = getattr(node, "provider", None) if isinstance(node, AppError) else None
        if isinstance(app_provider, str) and app_provider:
            base = app_provider.split("_", 1)[0]
            status = _status_of(node)
            comp = component or ("stt" if app_provider.endswith("_stt") else "tts" if app_provider.endswith("_tts") else "llm")
            code = str(getattr(node, "code", "") or "").lower()
            category = (TIMEOUT if "timeout" in code else UNAVAILABLE if "network" in code
                        else classify(base, status=status, message=str(node)))
            return ProviderFailure(str(node), provider=base, component=comp, category=category, status=status)
        text = str(node)
        hinted = _provider_hint(text) or (provider if node is exc else None)
        if hinted and (_status_of(node) is not None or _CREDIT_WORDS.search(text) or _AUTH_WORDS.search(text)
                       or re.search(r"timed? ?out|transport failed|unavailable|not configured", text, re.IGNORECASE)):
            status = _status_of(node)
            return ProviderFailure(text, provider=hinted, component=component or "llm",
                                   category=classify(hinted, status=status, message=text), status=status)
        node = node.__cause__ or node.__context__
    return None


# ------------------------------------------------------------- call context

_CALL_CONTEXT: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "provider_health_call_context", default=None
)


def set_call_context(*, call_id: str | None = None, tenant_id: str | None = None) -> contextvars.Token:
    """Attribute provider failures in this task (and tasks it spawns) to a call."""
    return _CALL_CONTEXT.set({"call_id": str(call_id or ""), "tenant_id": str(tenant_id or "")})


def reset_call_context(token: contextvars.Token) -> None:
    try:
        _CALL_CONTEXT.reset(token)
    except ValueError:
        pass


# ---------------------------------------------------------------- incidents

ACTIVE_WINDOW_S = 15 * 60
_MAX_INCIDENTS = 300
_MAX_IDS = 200


def _now_iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _sanitize(text: str) -> str:
    """Strip anything shaped like a credential before it is stored."""
    text = re.sub(r"(?i)(bearer|api[-_ ]?key|subscription[-_ ]key|token|secret)([\"':= ]+)[A-Za-z0-9._\-]{8,}", r"\1\2***", text)
    text = re.sub(r"\b(sk|rk|pk|rzp)_[A-Za-z0-9_\-]{8,}", "***", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}", "***", text)
    text = re.sub(r"\b[A-Za-z0-9]{32,}\b", "***", text)
    return text[:300]


class ProviderHealthRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._incidents: dict[str, dict[str, Any]] = {}
        self._key_slots: dict[str, dict[str, Any]] = {}
        self._loaded = False
        self._last_save = 0.0
        self._dirty = False

    # persistence ----------------------------------------------------------
    @staticmethod
    def _persist_enabled() -> bool:
        if os.environ.get("PROVIDER_HEALTH_PERSIST", "").strip() == "0":
            return False
        return "pytest" not in sys.modules

    @staticmethod
    def _path() -> Path:
        try:
            from server.config.env import PROJECT_ROOT, get_settings

            base = Path(get_settings().data_dir)
            if not base.is_absolute():
                base = Path(PROJECT_ROOT) / base
        except Exception:
            base = Path("data")
        return base / "provider_health.json"

    def _load_locked(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._persist_enabled():
            return
        try:
            path = self._path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                for row in data.get("incidents") or []:
                    if isinstance(row, dict) and row.get("id"):
                        self._incidents[str(row["id"])] = row
        except Exception as exc:
            logger.warning("[HEALTH] provider health load failed kind=%s", type(exc).__name__)

    def _save_locked(self, *, force: bool = False) -> None:
        if not self._persist_enabled():
            return
        now = time.time()
        if not force and now - self._last_save < 2.0:
            self._dirty = True
            return
        self._last_save = now
        self._dirty = False
        try:
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            rows = sorted(self._incidents.values(), key=lambda r: r.get("lastSeenTs", 0), reverse=True)[:_MAX_INCIDENTS]
            tmp.write_text(json.dumps({"incidents": rows}, default=str), encoding="utf-8")
            os.replace(tmp, path)
        except Exception as exc:
            logger.warning("[HEALTH] provider health save failed kind=%s", type(exc).__name__)

    # recording ------------------------------------------------------------
    def record_failure(
        self,
        provider: str,
        component: str,
        category: str,
        *,
        status: int | None = None,
        detail: str = "",
        key_slot: str | None = None,
        failed_over_to: str | None = None,
        all_keys_failed: bool = False,
        call_id: str | None = None,
        tenant_id: str | None = None,
        call_rejected: bool = False,
        summary: str | None = None,
    ) -> dict[str, Any]:
        provider = (provider or "unknown").strip().lower()
        component = component if component in COMPONENTS else "llm"
        category = category if category in CATEGORIES else UNAVAILABLE
        ctx = _CALL_CONTEXT.get() or {}
        call_id = call_id or ctx.get("call_id") or None
        tenant_id = tenant_id or ctx.get("tenant_id") or None
        dedup = f"{provider}:{component}:{category}"
        now = time.time()
        with self._lock:
            self._load_locked()
            open_incident = next(
                (row for row in self._incidents.values()
                 if row.get("dedupKey") == dedup and not row.get("resolvedAt")
                 and now - float(row.get("lastSeenTs") or 0) < ACTIVE_WINDOW_S),
                None,
            )
            new = open_incident is None
            if new:
                open_incident = {
                    "id": uuid.uuid4().hex[:16],
                    "dedupKey": dedup,
                    "provider": provider,
                    "component": component,
                    "category": category,
                    "firstSeen": _now_iso(now),
                    "firstSeenTs": now,
                    "count": 0,
                    "callIds": [],
                    "tenantIds": [],
                    "callsRejected": 0,
                    "resolvedAt": None,
                    "acknowledgedAt": None,
                }
                self._incidents[open_incident["id"]] = open_incident
            row = open_incident
            row["count"] = int(row.get("count") or 0) + 1
            row["lastSeen"] = _now_iso(now)
            row["lastSeenTs"] = now
            row["status"] = status
            row["detail"] = _sanitize(detail or "")
            if key_slot:
                row["keySlot"] = key_slot
            row["failedOverTo"] = failed_over_to
            row["allKeysFailed"] = bool(all_keys_failed) or bool(row.get("allKeysFailed") and not failed_over_to)
            if call_id and call_id not in row["callIds"] and len(row["callIds"]) < _MAX_IDS:
                row["callIds"].append(call_id)
            if tenant_id and tenant_id not in row["tenantIds"] and len(row["tenantIds"]) < _MAX_IDS:
                row["tenantIds"].append(tenant_id)
            if call_rejected:
                row["callsRejected"] = int(row.get("callsRejected") or 0) + 1
            if summary:
                row["summary"] = summary[:300]
            row["message"] = incident_message(row)
            if len(self._incidents) > _MAX_INCIDENTS:
                oldest = sorted(self._incidents.values(), key=lambda r: r.get("lastSeenTs", 0))
                for stale in oldest[: len(self._incidents) - _MAX_INCIDENTS]:
                    self._incidents.pop(stale["id"], None)
            self._save_locked(force=new)
            snapshot = dict(row)
        if new:
            logger.warning(
                "[HEALTH] provider incident opened provider=%s component=%s category=%s slot=%s status=%s",
                provider, component, category, key_slot or "-", status,
            )
        return snapshot

    def note_call_rejected(self, provider: str, component: str, category: str, *,
                           call_id: str | None = None, tenant_id: str | None = None) -> None:
        """A call was refused because of this provider; count it on the open incident."""
        self.record_failure(provider, component, category, call_id=call_id, tenant_id=tenant_id,
                            call_rejected=True, detail="Call was not placed because this service failed during setup")

    def record_recovery(self, provider: str, component: str | None = None, *, key_slot: str | None = None) -> None:
        """A request succeeded: close open incidents that the success disproves."""
        provider = (provider or "").strip().lower()
        now = time.time()
        changed = False
        with self._lock:
            self._load_locked()
            for row in self._incidents.values():
                if row.get("provider") != provider or row.get("resolvedAt"):
                    continue
                if component and row.get("component") != component and row.get("category") not in KEY_FAILOVER_CATEGORIES:
                    continue
                # A success on a backup key does not prove the primary is back.
                if row.get("category") in KEY_FAILOVER_CATEGORIES and row.get("keySlot") and key_slot and row["keySlot"] != key_slot:
                    if not row.get("servedByBackup"):
                        row["servedByBackup"] = key_slot
                        row["allKeysFailed"] = False
                        row["message"] = incident_message(row)
                        changed = True
                    continue
                row["resolvedAt"] = _now_iso(now)
                row["message"] = incident_message(row)
                changed = True
            if changed:
                self._save_locked(force=True)

    def set_key_slots(self, provider: str, slots: list[dict[str, Any]]) -> None:
        with self._lock:
            self._key_slots[provider] = {"slots": slots, "at": _now_iso()}

    def acknowledge(self, incident_id: str) -> bool:
        with self._lock:
            self._load_locked()
            row = self._incidents.get(incident_id)
            if row is None:
                return False
            row["resolvedAt"] = row.get("resolvedAt") or _now_iso()
            row["acknowledgedAt"] = _now_iso()
            self._save_locked(force=True)
            return True

    def incidents(self, *, limit: int = 200) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            self._load_locked()
            if self._dirty:
                self._save_locked(force=True)
            rows = sorted(self._incidents.values(), key=lambda r: r.get("lastSeenTs", 0), reverse=True)[:limit]
            out = []
            for row in rows:
                item = {k: v for k, v in row.items() if k not in {"callIds", "tenantIds", "dedupKey"}}
                item["active"] = not row.get("resolvedAt") and now - float(row.get("lastSeenTs") or 0) < ACTIVE_WINDOW_S
                item["callsAffected"] = len(row.get("callIds") or [])
                item["tenantsAffected"] = len(row.get("tenantIds") or [])
                item["tenantIds"] = list(row.get("tenantIds") or [])[:20]
                item["recentCallIds"] = list(row.get("callIds") or [])[-10:]
                out.append(item)
            return out

    def reset(self) -> None:
        with self._lock:
            self._incidents.clear()
            self._key_slots.clear()
            self._loaded = True


def incident_message(row: dict[str, Any]) -> str:
    """Plain admin language for one incident."""
    name = PROVIDER_LABEL.get(str(row.get("provider")), str(row.get("provider") or "Provider").title())
    category = str(row.get("category") or UNAVAILABLE)
    label = CATEGORY_LABEL.get(category, category)
    slot = row.get("keySlot")
    if row.get("resolvedAt") and not row.get("acknowledgedAt"):
        return f"{name}: was {label} — recovered."
    if row.get("summary"):
        return f"{name}: {row['summary']}"
    if category in KEY_FAILOVER_CATEGORIES and slot:
        slot_text = "the primary key" if slot == "primary" else f"key {slot}"
        backup = row.get("failedOverTo") or row.get("servedByBackup")
        if row.get("allKeysFailed") and not backup:
            return f"{name}: all API keys are {label} — calls using {name} are failing."
        if backup:
            return f"{name}: {label} on {slot_text} — now using the {backup} key."
        return f"{name}: {label} on {slot_text}."
    if category in HARD_CATEGORIES:
        return f"{name}: {label} — calls using {name} are failing."
    return f"{name}: {label}."


provider_health = ProviderHealthRegistry()


def record_exception(exc: BaseException, *, provider: str, component: str, **kwargs: Any) -> ProviderFailure | None:
    """Classify and record an exception from a known provider call site. Never raises."""
    try:
        if isinstance(exc, (asyncio.CancelledError,)):
            return None
        failure = provider_failure_from(exc, provider=provider, component=component)
        if failure is None:
            status = _status_of(exc)
            category = TIMEOUT if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) else classify(
                provider, status=status, body=getattr(exc, "body", None), message=str(exc))
            failure = ProviderFailure(str(exc), provider=provider, component=component, category=category, status=status)
        provider_health.record_failure(
            failure.provider or provider, component, failure.category,
            status=failure.status, detail=str(exc), **kwargs,
        )
        return failure
    except Exception as err:  # never let health bookkeeping break a call
        logger.warning("[HEALTH] record failed kind=%s", type(err).__name__)
        return None


def record_http_failure(provider: str, component: str, status: int | None, body: Any = None,
                        *, message: str = "", **kwargs: Any) -> str:
    """Record a non-2xx vendor answer; returns the category. Never raises."""
    category = classify(provider, status=status, body=body, message=message)
    try:
        code = _body_code(_body_text(body))
        detail = f"HTTP {status}" + (f" {code}" if code else "") + (f" — {message}" if message else "")
        provider_health.record_failure(provider, component, category, status=status, detail=detail, **kwargs)
    except Exception as err:
        logger.warning("[HEALTH] record failed kind=%s", type(err).__name__)
    return category


def record_turn_exception(exc: BaseException, *, provider: str | None, component: str = "llm",
                          call_id: str | None = None, tenant_id: str | None = None) -> None:
    """Record a vendor failure that ended a live turn (OpenAI, Gemini, DeepSeek...).

    Sarvam reports from its key pool at the request itself, and a model that
    merely produced an unusable answer (``finish_reason``) is not an outage.
    """
    provider = (provider or "").strip().lower()
    if not provider or provider == "sarvam" or getattr(exc, "finish_reason", None) is not None:
        return
    if isinstance(exc, ProviderFailure):
        return
    record_exception(exc, provider=provider, component=component, call_id=call_id, tenant_id=tenant_id)


def record_vendor_answer(provider: str, component: str, status: int | None, body: Any = None,
                         *, message: str = "") -> None:
    """Record carrier/integration/payment failures that say something about the
    vendor (credits, auth, outage, timeouts). A plain 4xx about one request —
    an invalid number, an unknown call — is that request's problem, not an
    incident. Never raises."""
    try:
        category = classify(provider, status=status, body=body, message=message)
        if category == BAD_REQUEST:
            return
        if status is None and category == UNAVAILABLE and not message:
            return
        record_http_failure(provider, component, status, body, message=message)
    except Exception:
        pass
