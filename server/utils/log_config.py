"""
Logging feature flags — driven by .env so categories can be toggled independently.
"""
from __future__ import annotations

from functools import lru_cache

from server.config.env import get_settings


@lru_cache(maxsize=1)
def get_log_flags() -> dict[str, bool]:
    s = get_settings()
    master = bool(s.log_enabled)
    return {
        "enabled": master,
        "voice": master and bool(s.log_voice),
        "stt": master and bool(s.log_stt),
        "brain": master and bool(s.log_brain),
        "tts": master and bool(s.log_tts),
        "ws": master and bool(s.log_ws),
        "perf": master and bool(s.log_perf),
        "client": master and bool(s.log_client),
        "pstn": master and bool(s.log_pstn),
    }


def should_log(category: str) -> bool:
    return get_log_flags().get(category, False)


def clear_log_flags_cache() -> None:
    get_log_flags.cache_clear()
