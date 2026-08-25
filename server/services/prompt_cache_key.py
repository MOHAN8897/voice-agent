"""
Prompt cache key — content hash for GPT-5.6 explicit caching.
"""
from __future__ import annotations

import hashlib

from server.config.env import get_settings


def compute_cache_key(brain_prompt: str, budget_tokens: int) -> str:
    settings = get_settings()
    prefix = settings.prompt_cache_key_prefix
    digest = hashlib.sha256(f"{brain_prompt}|{budget_tokens}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:cfg-{digest}"


def compute_cache_key_versioned(compiled_brain_version: str, budget_tokens: int) -> str:
    """Version-based cache key — stable across sessions when brain version unchanged."""
    settings = get_settings()
    prefix = settings.prompt_cache_key_prefix
    digest = hashlib.sha256(f"{compiled_brain_version}|{budget_tokens}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:cb-{digest}"


def cache_eligible(brain_tokens: int) -> bool:
    settings = get_settings()
    return brain_tokens >= int(settings.prompt_cache_min_tokens)


def caching_enabled(model: str, brain_tokens: int = 0) -> bool:
    settings = get_settings()
    if not settings.enable_prompt_caching:
        return False
    if not str(model).startswith("gpt-5.6"):
        return False
    return brain_tokens >= int(settings.prompt_cache_min_tokens)
