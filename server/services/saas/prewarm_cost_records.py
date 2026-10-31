"""Persist known setup spend even when a ringing call is never answered.

Records contain usage costs and tenant attribution, never caller audio/text.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import logging
from threading import RLock
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
_record_lock = RLock()


def record_directory() -> Path:
    from server.config.env import get_settings
    return Path(get_settings().data_dir) / "billing-prewarm"


def _path(key: str) -> Path:
    parts = key.split(":", 1)
    if len(parts) == 2:
        try:
            day = datetime.strptime(parts[0], "%Y-%m-%d").date().isoformat()
            return record_directory() / day / (hashlib.sha256(key.encode()).hexdigest() + ".json")
        except ValueError:
            pass
    return record_directory() / (hashlib.sha256(key.encode()).hexdigest() + ".json")


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def record_prepared(key: str, *, tenant_id: str, usage: dict, model: str) -> str | None:
    if not tenant_id or not usage:
        return
    from server.services.usage_pricing import cost_llm_usd, resolve_fx_rate_inr
    from server.realtime.usage import extract_realtime_usage
    normalized = extract_realtime_usage({"usage": usage})
    cost = cost_llm_usd(
        llm_model=model,
        input_tokens=normalized.get("input_tokens", 0), output_tokens=normalized.get("output_tokens", 0),
        input_audio_tokens=normalized.get("input_audio_tokens", 0), output_audio_tokens=normalized.get("output_audio_tokens", 0),
        cached_tokens=normalized.get("cached_tokens", 0), input_image_tokens=normalized.get("input_image_tokens", 0),
    )["total_usd"]
    fx = float((await asyncio.to_thread(resolve_fx_rate_inr))["rate"])
    now = datetime.now(timezone.utc)
    key = now.date().isoformat() + ":" + key
    await asyncio.to_thread(_write, _path(key), {
        "created_at": now.isoformat(), "tenant_id": tenant_id,
        "model": model, "cost_usd": cost, "cost_inr": cost * fx,
        "status": "prepared", "call_id": None,
    })
    return key


async def mark_usage(key: str, *, call_id: str | None = None) -> None:
    def update():
        with _record_lock:
            path = _path(key)
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                # A later expiry/cancel cannot convert attributed spend into overhead.
                if value.get("call_id"):
                    return
                value.update(status="connected" if call_id else "unused", call_id=call_id)
                _write(path, value)
            except (OSError, ValueError, AttributeError):
                logger.error("[BILLING] could not update prewarm cost attribution")
    await asyncio.to_thread(update)
