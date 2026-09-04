"""PSTN call lifecycle debug logs — toggle with LOG_PSTN in .env.

Emits structured [PSTN] lines to the API terminal for outbound/inbound telephony:
  dial → webhook → websocket → stream → STT → TTS → brain → hangup

Set LOG_PSTN=false (or LOG_ENABLED=false) to silence.
"""
from __future__ import annotations

import time
from typing import Any

from server.utils.log_config import should_log

# monotonic anchors keyed by call_control_id, call_id, or session id
_t0: dict[str, float] = {}


def _enabled() -> bool:
    return should_log("pstn")


def _safe_text(text: str | None, limit: int = 100) -> str:
    if not text:
        return ""
    return text[:limit].encode("ascii", "replace").decode("ascii")


def mark(key: str) -> None:
    """Start latency clock for this call leg (idempotent)."""
    if key and key not in _t0:
        _t0[key] = time.monotonic()


def clear(key: str) -> None:
    if key:
        _t0.pop(key, None)


def elapsed_ms(key: str | None) -> int | None:
    if not key or key not in _t0:
        return None
    return int((time.monotonic() - _t0[key]) * 1000)


def log_pstn(phase: str, *, timer_key: str | None = None, **kv: Any) -> None:
    if not _enabled():
        return
    from server.utils.logger import log_pstn as _log

    key = timer_key or str(kv.get("control") or kv.get("call_sid") or kv.get("call_id") or "")
    ms = elapsed_ms(key) if key else None
    msg = f"{phase} +{ms}ms" if ms is not None else phase
    _log(msg, **kv)


def log_pstn_summary(
    *,
    provider: str,
    external_id: str | None,
    call_id: str | None,
    media_in: int = 0,
    media_out: int = 0,
    reason: str = "stop",
    **extra: Any,
) -> None:
    key = external_id or call_id or ""
    bidirectional = media_in > 0 and media_out > 0
    log_pstn(
        "call.summary",
        timer_key=key,
        provider=provider,
        control=external_id,
        call_id=call_id,
        media_in=media_in,
        media_out=media_out,
        bidirectional=bidirectional,
        reason=reason,
        **extra,
    )
    clear(key)
    if call_id:
        clear(call_id)
