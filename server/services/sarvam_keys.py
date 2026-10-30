"""Sarvam API key failover: primary key first, backup keys when it is spent.

Keys: the effective primary (admin-panel override or ``SARVAM_API_KEY``), then
``SARVAM_API_KEY_1``, ``SARVAM_API_KEY_2``... from the environment / ``.env``.

When Sarvam rejects a key for credits, quota or auth (see
``provider_health.KEY_FAILOVER_CATEGORIES``) that key cools down and the same
request moves on to the next key. Every Sarvam surface (LLM, STT REST and
realtime, TTS REST, stream and WebSocket) shares this pool, because credits
belong to the account behind the key, not to one endpoint. After the cool-down
the primary is tried first again, which is the periodic re-check; a success
closes the incident.

Thread- and task-safe (one ``threading.Lock`` around tiny critical sections),
per process. Keys never leave this module except to build request headers; logs
and the admin API only ever see slot names.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from server.services import provider_health as ph
from server.utils.logger import logger

PROVIDER = "sarvam"
MAX_SECONDARY = 9

COOLDOWN_S = {
    ph.CREDITS: 10 * 60,
    ph.QUOTA: 5 * 60,
    ph.AUTH: 30 * 60,
}
# When every key is cooling down, still let one probe through per key at most
# this often, so a top-up is noticed without hammering a dead account.
PROBE_INTERVAL_S = 20.0


@dataclass
class _SlotState:
    fingerprint: str
    cooldown_until: float = 0.0
    category: str | None = None
    failures: int = 0
    last_attempt: float = 0.0
    last_failure_at: float = 0.0
    last_success_at: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


def _fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _env_value(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


class SarvamKeyPool:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, _SlotState] = {}
        self._active_slot: str | None = None

    # ----------------------------------------------------------- key list
    @staticmethod
    def _primary() -> str:
        from server.config.env import get_settings
        from server.services.dev_secrets_store import dev_secrets_store

        try:
            settings = get_settings()
            fallback = settings.sarvam_api_key
        except Exception:
            fallback = _env_value("SARVAM_API_KEY")
        return str(dev_secrets_store.effective_secret("sarvam_api_key") or fallback or "").strip()

    def keys(self) -> list[tuple[str, str]]:
        """Ordered (slot, key) pairs, de-duplicated, never logged."""
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        primary = self._primary()
        if primary:
            out.append(("primary", primary))
            seen.add(primary)
        for index in range(1, MAX_SECONDARY + 1):
            value = _env_value(f"SARVAM_API_KEY_{index}")
            if value and value not in seen:
                out.append((f"secondary-{index}", value))
                seen.add(value)
        return out

    def _slot_state_locked(self, slot: str, key: str) -> _SlotState:
        fp = _fingerprint(key)
        state = self._state.get(slot)
        if state is None or state.fingerprint != fp:
            # A replaced key starts healthy.
            state = _SlotState(fingerprint=fp)
            self._state[slot] = state
        return state

    # --------------------------------------------------------- selection
    def plan(self, *, provided_key: str | None = None) -> list[tuple[str, str]]:
        """Keys to try for one request, best first. Empty means fail fast."""
        if provided_key:
            return [("provided", provided_key)]
        keys = self.keys()
        if not keys:
            return []
        now = time.monotonic()
        with self._lock:
            ready = []
            cooling = []
            for slot, key in keys:
                state = self._slot_state_locked(slot, key)
                if state.cooldown_until <= now:
                    ready.append((slot, key))
                else:
                    cooling.append((slot, key, state))
            if ready:
                # Cooling keys are not tried while a healthy one exists.
                return ready
            probes = [(slot, key) for slot, key, state in cooling if now - state.last_attempt >= PROBE_INTERVAL_S]
            for slot, _key in probes:
                self._state[slot].last_attempt = now
            return probes

    def mark_attempt(self, slot: str) -> None:
        with self._lock:
            state = self._state.get(slot)
            if state is not None:
                state.last_attempt = time.monotonic()

    def report_failure(self, slot: str, category: str, *, component: str, status: int | None = None,
                       detail: str = "", next_slot: str | None = None) -> None:
        """Cool down a key for a key-level failure and record the incident."""
        if slot == "provided":
            ph.provider_health.record_failure(PROVIDER, component, category, status=status, detail=detail)
            return
        now = time.monotonic()
        with self._lock:
            state = self._state.get(slot)
            if state is not None and category in ph.KEY_FAILOVER_CATEGORIES:
                state.failures += 1
                state.category = category
                state.last_failure_at = now
                state.cooldown_until = now + COOLDOWN_S.get(category, 300)
            all_down = all(s.cooldown_until > now for s in self._state.values()) if self._state else True
            if self._active_slot == slot and next_slot:
                self._active_slot = next_slot
        logger.warning(
            "[SARVAM] key slot=%s rejected category=%s status=%s component=%s%s",
            slot, category, status, component, f" -> trying slot={next_slot}" if next_slot else "",
        )
        ph.provider_health.record_failure(
            PROVIDER, component, category, status=status, detail=detail, key_slot=slot,
            failed_over_to=next_slot, all_keys_failed=bool(all_down and not next_slot and category in ph.KEY_FAILOVER_CATEGORIES),
        )
        self._publish()

    def report_success(self, slot: str, *, component: str) -> None:
        if slot == "provided":
            return
        now = time.monotonic()
        changed = False
        with self._lock:
            state = self._state.get(slot)
            if state is not None:
                recovered = state.category is not None
                state.cooldown_until = 0.0
                state.category = None
                state.failures = 0
                state.last_success_at = now
                state.last_attempt = now
                changed = recovered
            if self._active_slot != slot:
                previous = self._active_slot
                self._active_slot = slot
                changed = True
                logger.info("[SARVAM] active key slot=%s (was %s)", slot, previous or "-")
        ph.provider_health.record_recovery(PROVIDER, component, key_slot=slot)
        if changed:
            self._publish()

    # ---------------------------------------------------------- snapshot
    def snapshot(self) -> dict[str, Any]:
        """Slot-level state for the admin panel. No key material."""
        now = time.monotonic()
        keys = self.keys()
        with self._lock:
            slots = []
            for slot, key in keys:
                state = self._slot_state_locked(slot, key)
                cooling = state.cooldown_until > now
                slots.append({
                    "slot": slot,
                    "configured": True,
                    "state": "cooling_down" if cooling else ("active" if slot == self._active_slot else "standby"),
                    "category": state.category if cooling else None,
                    "retryInSeconds": int(state.cooldown_until - now) if cooling else 0,
                    "failures": state.failures,
                    "lastFailureAgoSeconds": int(now - state.last_failure_at) if state.last_failure_at else None,
                    "lastSuccessAgoSeconds": int(now - state.last_success_at) if state.last_success_at else None,
                })
            ready = [s["slot"] for s in slots if s["state"] != "cooling_down"]
            active = self._active_slot if self._active_slot in ready else (ready[0] if ready else None)
        return {"provider": PROVIDER, "activeSlot": active, "slots": slots,
                "allKeysCoolingDown": bool(slots) and not ready, "configuredKeys": len(slots)}

    def _publish(self) -> None:
        try:
            ph.provider_health.set_key_slots(PROVIDER, self.snapshot()["slots"])
        except Exception:
            pass

    def recheck_now(self) -> None:
        """Admin: lift cool-downs so the next request re-tries the primary."""
        with self._lock:
            for state in self._state.values():
                state.cooldown_until = 0.0
                state.last_attempt = 0.0
        logger.info("[SARVAM] key cool-downs cleared by admin; primary is re-checked on the next request")

    def reset(self) -> None:
        with self._lock:
            self._state.clear()
            self._active_slot = None


sarvam_key_pool = SarvamKeyPool()


def all_keys_failed_error(component: str, message: str, *, category: str | None = None,
                          status: int | None = None, slot: str | None = None) -> ph.ProviderFailure:
    return ph.ProviderFailure(
        message, provider=PROVIDER, component=component,
        category=category or ph.CREDITS, status=status, key_slot=slot, all_keys_failed=True,
    )


def no_key_available(component: str, label: str) -> ph.ProviderFailure:
    """Nothing to try: either nothing configured or every key is cooling down."""
    if not sarvam_key_pool.keys():
        ph.provider_health.record_failure(PROVIDER, component, ph.MISCONFIGURED, detail="No Sarvam API key configured")
        return ph.ProviderFailure("SARVAM_API_KEY is not configured", provider=PROVIDER, component=component,
                                  category=ph.MISCONFIGURED)
    snap = sarvam_key_pool.snapshot()
    category = next((s["category"] for s in snap["slots"] if s.get("category")), ph.CREDITS)
    ph.provider_health.record_failure(PROVIDER, component, category, all_keys_failed=True,
                                      detail="All Sarvam keys are cooling down after rejections", key_slot="primary")
    return all_keys_failed_error(component, f"{label}: all Sarvam keys unavailable ({category})", category=category)


# ------------------------------------------------------------------ helpers

def _next_slot(attempts: list[tuple[str, str]], index: int) -> str | None:
    return attempts[index + 1][0] if index + 1 < len(attempts) else None


def _detail(status: int, body: Any) -> str:
    code = ph._body_code(ph._body_text(body))
    return f"HTTP {status}" + (f" {code}" if code else "")


def _handle_rejection(attempts: list[tuple[str, str]], index: int, *, component: str,
                      status: int, body: Any) -> bool:
    """Record a non-2xx answer. True when the caller should try the next key."""
    slot = attempts[index][0]
    category = ph.classify(PROVIDER, status=status, body=body)
    nxt = _next_slot(attempts, index)
    if category in ph.KEY_FAILOVER_CATEGORIES:
        sarvam_key_pool.report_failure(slot, category, component=component, status=status,
                                       detail=_detail(status, body), next_slot=nxt)
        return nxt is not None
    ph.provider_health.record_failure(PROVIDER, component, category, status=status,
                                      detail=_detail(status, body), key_slot=slot)
    return False


def rejection_error(message: str, *, component: str, status: int, body: Any = None,
                    slot: str | None = None) -> ph.ProviderFailure:
    """The exception to raise for a final non-2xx Sarvam answer."""
    category = ph.classify(PROVIDER, status=status, body=body)
    return ph.ProviderFailure(message, provider=PROVIDER, component=component, category=category,
                              status=status, key_slot=slot,
                              all_keys_failed=category in ph.KEY_FAILOVER_CATEGORIES)


async def request_with_failover(component: str, label: str, send, *, provided_key: str | None = None):
    """Run ``send(key) -> httpx.Response`` with key failover.

    Returns ``(response, slot)``. A non-2xx response is returned (already
    recorded) for the caller to raise its own error type.
    """
    attempts = sarvam_key_pool.plan(provided_key=provided_key)
    if not attempts:
        raise no_key_available(component, label)
    for index, (slot, key) in enumerate(attempts):
        sarvam_key_pool.mark_attempt(slot)
        response = await send(key)
        if response.status_code < 400:
            sarvam_key_pool.report_success(slot, component=component)
            return response, slot
        if _handle_rejection(attempts, index, component=component, status=response.status_code,
                             body=getattr(response, "content", None)):
            continue
        return response, slot
    raise no_key_available(component, label)  # pragma: no cover - loop always returns


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def stream_with_failover(component: str, label: str, open_stream, *, provided_key: str | None = None):
    """``async with`` an httpx stream opened by ``open_stream(key)`` with failover.

    Failover only happens before any byte is consumed, so nothing has been
    spoken yet. Yields the response; a non-2xx one is already read and closed.
    """
    attempts = sarvam_key_pool.plan(provided_key=provided_key)
    if not attempts:
        raise no_key_available(component, label)
    for index, (slot, key) in enumerate(attempts):
        sarvam_key_pool.mark_attempt(slot)
        cm = open_stream(key)
        response = await cm.__aenter__()
        if response.status_code >= 400:
            try:
                body = await response.aread()
            finally:
                await cm.__aexit__(None, None, None)
            if _handle_rejection(attempts, index, component=component, status=response.status_code, body=body):
                continue
            yield response
            return
        sarvam_key_pool.report_success(slot, component=component)
        try:
            yield response
        except BaseException as exc:
            if not await cm.__aexit__(type(exc), exc, exc.__traceback__):
                raise
        else:
            await cm.__aexit__(None, None, None)
        return
    raise no_key_available(component, label)


async def probe_all(component: str = "llm") -> list[dict[str, Any]]:
    """Admin re-check: one minimal chat completion per key (a few tokens).

    Updates the pool with the answers, so a topped-up primary goes back into
    service immediately. Returns slot, HTTP status and category only.
    """
    import httpx

    sarvam_key_pool.recheck_now()
    results: list[dict[str, Any]] = []
    body = {"model": "sarvam-105b", "messages": [{"role": "user", "content": "ok"}],
            "max_tokens": 1, "reasoning_effort": None}
    async with httpx.AsyncClient(timeout=20) as client:
        for slot, key in sarvam_key_pool.keys():
            try:
                response = await client.post(
                    "https://api.sarvam.ai/v1/chat/completions",
                    headers={"api-subscription-key": key, "Authorization": f"Bearer {key}"}, json=body)
            except httpx.HTTPError as exc:
                results.append({"slot": slot, "status": None, "category": ph.UNAVAILABLE, "ok": False,
                                "error": type(exc).__name__})
                continue
            if response.status_code < 400:
                sarvam_key_pool.report_success(slot, component=component)
                results.append({"slot": slot, "status": response.status_code, "category": None, "ok": True})
                continue
            category = ph.classify(PROVIDER, status=response.status_code, body=response.content)
            if category in ph.KEY_FAILOVER_CATEGORIES:
                sarvam_key_pool.report_failure(slot, category, component=component, status=response.status_code,
                                               detail=_detail(response.status_code, response.content) + " (admin re-check)")
            results.append({"slot": slot, "status": response.status_code, "category": category, "ok": False})
    return results
