"""
Token usage normalization — Responses API usage objects.
"""
from __future__ import annotations


def normalize_usage(usage) -> dict:
    if not usage:
        return {}
    if isinstance(usage, dict):
        details = usage.get("input_tokens_details") or {}
        if isinstance(details, dict):
            cached = details.get("cached_tokens", 0)
            cache_write = details.get("cache_write_tokens", 0)
        else:
            cached = getattr(details, "cached_tokens", 0) or 0
            cache_write = getattr(details, "cache_write_tokens", 0) or 0
        return {
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "cached_tokens": int(cached or 0),
            "cache_write_tokens": int(cache_write or 0),
        }
    details = getattr(usage, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) if details else 0
    cache_write = getattr(details, "cache_write_tokens", 0) if details else 0
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        "cached_tokens": int(cached or 0),
        "cache_write_tokens": int(cache_write or 0),
    }
