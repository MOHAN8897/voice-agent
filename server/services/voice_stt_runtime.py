"""Shared STT runtime normalization — browser WS and PSTN use the same rules."""
from __future__ import annotations

from typing import Any

from server.config.constants import constants

DEFAULT_STT_SILENCE_MS = 400


def effective_stt_silence_ms(runtime: dict[str, Any] | None, *, explicit: int | None = None) -> int:
    if explicit is not None:
        return int(explicit)
    rt = runtime or {}
    val = rt.get("sttSilenceMs")
    if val is None:
        return DEFAULT_STT_SILENCE_MS
    return int(val)


def effective_stt_stream_type(stream_type: str | None) -> str:
    st = str(stream_type or "fast").strip()
    if st not in constants.STT_STREAM_TYPES:
        return "fast"
    return st


def effective_stt_mode(mode: str | None) -> str:
    m = str(mode or "transcribe").strip()
    if m != "transcribe":
        return "transcribe"
    return m
