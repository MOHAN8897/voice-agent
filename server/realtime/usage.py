"""Normalize Realtime usage and assert the text-only contract (zero audio tokens)."""
from __future__ import annotations

from typing import Any

from server.utils.logger import logger

_EMPTY = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cached_tokens": 0,
    "cache_write_tokens": 0,
    "audio_tokens": 0,
    "input_audio_tokens": 0,
    "output_audio_tokens": 0,
    "text_tokens": 0,
    "reasoning_tokens": 0,
}


def _num(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            data = dump()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def extract_realtime_usage(response: Any) -> dict[str, Any]:
    payload = _as_dict(response)
    usage = payload.get("usage") if payload else None
    if usage is None and response is not None and not isinstance(response, dict):
        usage = getattr(response, "usage", None)
    dump = _as_dict(usage)
    if not dump:
        return dict(_EMPTY)
    input_details = _as_dict(dump.get("input_token_details"))
    output_details = _as_dict(dump.get("output_token_details"))
    cached_details = _as_dict(input_details.get("cached_tokens_details"))
    input_audio = _num(input_details.get("audio_tokens"))
    output_audio = _num(output_details.get("audio_tokens"))
    return {
        "input_tokens": _num(dump.get("input_tokens")),
        "output_tokens": _num(dump.get("output_tokens")),
        "cached_tokens": _num(input_details.get("cached_tokens")),
        "cache_write_tokens": 0,
        "audio_tokens": input_audio + output_audio,
        "input_audio_tokens": input_audio,
        "output_audio_tokens": output_audio,
        "text_tokens": _num(input_details.get("text_tokens")) + _num(output_details.get("text_tokens")),
        "reasoning_tokens": _num(cached_details.get("reasoning_tokens")),
    }


def assert_zero_audio_tokens(usage: dict[str, Any], *, call_id: str | None = None) -> None:
    audio = _num(usage.get("audio_tokens"))
    if audio:
        logger.warning(
            "[REALTIME] audio tokens were billed call=%s audio=%s in=%s out=%s — text-only contract broken",
            call_id,
            audio,
            usage.get("input_audio_tokens"),
            usage.get("output_audio_tokens"),
        )
    else:
        logger.debug("[REALTIME] usage audio_tokens=0 call=%s", call_id)
