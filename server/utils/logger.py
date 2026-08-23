"""
Secret-safe structured logger — server/utils/logger.py
Category toggles via .env: LOG_ENABLED, LOG_VOICE, LOG_STT, LOG_BRAIN, LOG_TTS, LOG_WS, LOG_PERF.
Set LOG_LEVEL=off or LOG_ENABLED=false to silence all logs.
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Any

from server.utils.log_config import should_log

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9-_]{10,}"),
    re.compile(r"api[_-]?subscription[_-]?key", re.IGNORECASE),
    re.compile(r"OPENAI_API_KEY", re.IGNORECASE),
    re.compile(r"SARVAM_API_KEY", re.IGNORECASE),
]

_REDACTED = "***REDACTED***"


def _redact(msg: str) -> str:
    for pat in _SECRET_PATTERNS:
        msg = pat.sub(_REDACTED, msg)
    msg = re.sub(r"Bearer\s+[A-Za-z0-9-_.\"]{10,}", "Bearer ***REDACTED***", msg, flags=re.IGNORECASE)
    return msg


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _redact(super().format(record))


def get_logger(name: str = "telugu-agent") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    handler.setFormatter(RedactingFormatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


logger = get_logger()


def set_level(level: str) -> None:
    if level.lower() == "off":
        lvl = logging.CRITICAL + 1
    else:
        lvl = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(lvl)
    for h in logger.handlers:
        h.setLevel(lvl)


def _emit(level: int, category: str, prefix: str, msg: str, **kv: Any) -> None:
    if not should_log(category):
        return
    suffix = f" {kv}" if kv else ""
    logger.log(level, f"{prefix} {msg}{suffix}".strip())


def log_voice(msg: str, **kv: Any) -> None:
    _emit(logging.INFO, "voice", "[VOICE]", msg, **kv)


def log_stt(msg: str, **kv: Any) -> None:
    _emit(logging.INFO, "stt", "[STT]", msg, **kv)


def log_brain(msg: str, **kv: Any) -> None:
    _emit(logging.INFO, "brain", "[BRAIN]", msg, **kv)


def log_tts(msg: str, **kv: Any) -> None:
    _emit(logging.INFO, "tts", "[TTS]", msg, **kv)


def log_ws(msg: str, **kv: Any) -> None:
    _emit(logging.INFO, "ws", "[WS]", msg, **kv)


def log_perf(msg: str, **kv: Any) -> None:
    _emit(logging.INFO, "perf", "[PERF]", msg, **kv)


def log_error(msg: str, **kv: Any) -> None:
    """Surface errors when master logging is enabled."""
    from server.utils.log_config import get_log_flags
    if not get_log_flags().get("enabled"):
        return
    suffix = f" {kv}" if kv else ""
    logger.error(f"[ERROR] {msg}{suffix}".strip())
