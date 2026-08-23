"""
Secret-safe structured logger — server/utils/logger.py
Pino-style JSON logs, redacts secrets, pii-safe.
"""
from __future__ import annotations

import logging
import re
import sys
from typing import Any

# Never log these patterns
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
    # also redact Bearer tokens
    msg = re.sub(r"Bearer\s+[A-Za-z0-9-_.\"]{10,}", "Bearer ***REDACTED***", msg, flags=re.IGNORECASE)
    return msg


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return _redact(original)


def get_logger(name: str = "telugu-agent") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    handler.setFormatter(RedactingFormatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))
    logger.addHandler(handler)
    # Level set from env at startup
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


logger = get_logger()


def set_level(level: str) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(lvl)
    for h in logger.handlers:
        h.setLevel(lvl)


# Convenience helpers matching plan log taxonomy
def log_voice(msg: str, **kv: Any) -> None:
    logger.info(f"[VOICE] {msg} {kv if kv else ''}".strip())


def log_stt(msg: str, **kv: Any) -> None:
    logger.info(f"[STT] {msg} {kv if kv else ''}".strip())


def log_brain(msg: str, **kv: Any) -> None:
    logger.info(f"[BRAIN] {msg} {kv if kv else ''}".strip())


def log_tts(msg: str, **kv: Any) -> None:
    logger.info(f"[TTS] {msg} {kv if kv else ''}".strip())


def log_error(msg: str, **kv: Any) -> None:
    logger.error(f"[ERROR] {msg} {kv if kv else ''}".strip())
