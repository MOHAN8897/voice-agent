"""Single speak-then-disconnect executor for every live hangup path.

Sequence: closing signal → flush remaining audio → wait until farewell is
off the wire → human trail pause → drain archive → provider hangup →
lifecycle end with the real hangup reason.
"""
from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from server.call.call_end_policy import HANGUP_REASONS
from server.call.natural_hangup import pause_before_disconnect, wait_for_farewell_playback

MaybeAsync = Callable[[], Awaitable[None] | None]

JUDGMENT_END_REASONS = frozenset(HANGUP_REASONS)
LIFECYCLE_PASSTHROUGH = frozenset({
    "user_stop",
    "timeout",
    "error",
    "transfer",
    "browser_unload",
    "pstn_hangup",
    "agent_hangup",
    "superseded",
    "stale_recovery",
    "ws_disconnect",
    *JUDGMENT_END_REASONS,
})


def canonical_lifecycle_reason(reason: str | None) -> str:
    raw = str(reason or "").strip().lower()
    if raw in LIFECYCLE_PASSTHROUGH:
        return raw
    if raw in {"user_hangup"}:
        return "user_stop"
    if raw in {"idle_timeout"}:
        return "timeout"
    if raw in {"hangup", "normal_clearing"}:
        return "pstn_hangup" if raw == "normal_clearing" else "user_stop"
    return "agent_hangup"


@dataclass
class CloseCallResult:
    heard_playback: bool
    playback_wait_ms: int
    trail_ms: int
    reason: str


async def _maybe_await(fn: MaybeAsync | None) -> None:
    if fn is None:
        return
    result = fn()
    if inspect.isawaitable(result):
        await result


async def execute_agent_close(
    *,
    call_id: str | None,
    reason: str,
    spoke_farewell: bool = True,
    flush_audio: MaybeAsync | None = None,
    is_playing: Callable[[], bool] | None = None,
    on_closing: MaybeAsync | None = None,
    drain_archive: MaybeAsync | None = None,
    on_provider_hangup: MaybeAsync | None = None,
    on_ended: MaybeAsync | None = None,
    end_lifecycle: bool = True,
    trail_sec: float | None = None,
    playback_timeout_sec: float | None = None,
) -> CloseCallResult:
    from server.call.natural_hangup import HANGUP_PLAYBACK_TIMEOUT_SEC, HANGUP_TRAIL_SILENCE_SEC
    from server.services.pstn_media_flow import pstn_media_flow
    from server.utils.logger import log_pstn

    canonical = canonical_lifecycle_reason(reason)
    t0 = time.monotonic()
    await _maybe_await(on_closing)
    if call_id:
        pstn_media_flow.emit(
            call_id,
            "hangup_closing",
            "internal",
            detail=canonical,
            status="processing",
        )

    await _maybe_await(flush_audio)

    heard = False
    if is_playing is not None:
        timeout = HANGUP_PLAYBACK_TIMEOUT_SEC if playback_timeout_sec is None else playback_timeout_sec
        heard = await wait_for_farewell_playback(is_playing, timeout_sec=timeout)
        if not heard:
            log_pstn("hangup.playback_idle", call_id=call_id, heard=False)
    wait_ms = int((time.monotonic() - t0) * 1000)

    should_pause = heard or spoke_farewell
    trail = HANGUP_TRAIL_SILENCE_SEC if trail_sec is None else trail_sec
    await pause_before_disconnect(should_pause=should_pause, trail_sec=trail)
    trail_ms = int((trail if should_pause else 0) * 1000)

    await _maybe_await(drain_archive)
    try:
        await _maybe_await(on_provider_hangup)
    except Exception as exc:
        log_pstn("hangup.provider.failed", call_id=call_id, error=str(exc)[:200])

    await _maybe_await(on_ended)

    result = CloseCallResult(
        heard_playback=heard,
        playback_wait_ms=wait_ms,
        trail_ms=trail_ms,
        reason=canonical,
    )
    _stamp_hangup_telemetry(call_id, result)
    if end_lifecycle and call_id:
        from server.call.call_lifecycle_service import call_lifecycle_service

        await call_lifecycle_service.end(call_id, reason=canonical)
    if call_id:
        pstn_media_flow.emit(
            call_id,
            "hangup_complete",
            "internal",
            detail=canonical,
            extra={
                "playback_wait_ms": wait_ms,
                "trail_ms": trail_ms,
                "heard_playback": heard,
            },
        )
    from server.call.callback_close import mark_hangup_executed

    mark_hangup_executed(call_id)
    return result


def _stamp_hangup_telemetry(call_id: str | None, result: CloseCallResult) -> None:
    if not call_id:
        return
    try:
        from server.call.call_ledger import call_ledger
        from server.call import call_context

        meta = call_ledger.read_meta(call_id)
        if not meta:
            return
        meta["hangup_reason"] = result.reason
        meta["hangup_playback_wait_ms"] = result.playback_wait_ms
        meta["hangup_trail_ms"] = result.trail_ms
        meta["hangup_heard_playback"] = result.heard_playback
        ctx = call_context.get(call_id)
        if ctx is not None:
            meta["callback_close_phase"] = ctx.callback_close_phase
        call_ledger.write_meta(call_id, meta)
    except Exception:
        pass
