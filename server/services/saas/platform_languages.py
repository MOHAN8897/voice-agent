"""Which spoken languages the agent-creation UI may offer.

The agent-creation frontend renders a language list. Which entries appear is a
platform decision, not a build-time constant: an operator serving English-speaking
countries should not have Telugu/Hindi/Kannada in the picker, but turning a
language off must never break an agent that already speaks it.

So this is an *enablement* list layered over `SUPPORTED_LANGUAGES`, not a
replacement of it. Enabled means "offerable at creation". Anything already stored
on an agent keeps resolving through the normal path.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from server.config.constants import constants, normalize_supported_language
from server.config.env import get_settings

SUPPORTED_LANGUAGES = constants.SUPPORTED_LANGUAGES

_LOCK = threading.Lock()
_cache: dict[str, Any] | None = None

#: Shipped default. The site is for English-speaking countries, so only English
#: variants are offered until an operator enables more from the admin panel.
DEFAULT_ENABLED: tuple[str, ...] = ("en-US", "en-GB", "en-IN")


def _path() -> Path:
    return get_settings().data_path / "platform_languages.json"


def _load() -> dict[str, Any]:
    """Read the override, re-reading when the file changed.

    Cached on mtime rather than forever: the admin panel writes through one
    worker, and a long-lived cache would keep serving the previous language set to
    every other worker until a restart.
    """
    global _cache, _cache_mtime
    with _LOCK:
        path = _path()
        mtime = 0.0
        if path.is_file():
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
        if _cache is not None and mtime == _cache_mtime:
            return _cache
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                _cache = raw if isinstance(raw, dict) else {}
            except Exception:
                _cache = {}
        else:
            _cache = {}
        _cache_mtime = mtime
        return _cache


def _save(data: dict[str, Any]) -> None:
    global _cache, _cache_mtime
    with _LOCK:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        _cache = dict(data)
        try:
            _cache_mtime = path.stat().st_mtime
        except OSError:
            _cache_mtime = 0.0


def _canonical(code: str) -> str | None:
    """A language code the platform can actually speak, or None."""
    raw = (code or "").strip()
    if raw in SUPPORTED_LANGUAGES:
        return raw
    resolved = normalize_supported_language(raw)
    return resolved if resolved in SUPPORTED_LANGUAGES else None


def known_languages() -> dict[str, dict[str, str]]:
    """Every language the platform can technically speak, with a display name."""
    return dict(SUPPORTED_LANGUAGES)


def enabled_languages() -> list[str]:
    """Codes the creation UI may offer, in a stable order."""
    raw = _load().get("enabled")
    wanted = [str(c).strip() for c in raw if str(c).strip()] if isinstance(raw, list) else []
    if not wanted:
        wanted = list(DEFAULT_ENABLED)
    # Resolve aliases ("en-GB" -> "en-US") and drop anything genuinely unknown,
    # so a stored code the platform cannot speak never reaches the picker.
    return [c for c in dict.fromkeys(_canonical(c) for c in wanted) if c]


def language_options() -> list[dict[str, str]]:
    """[{code, label}] for the creation UI, enabled languages only."""
    return [
        {"code": code, "label": SUPPORTED_LANGUAGES[code].get("name") or code}
        for code in enabled_languages()
    ]


def is_enabled(code: str | None) -> bool:
    return bool(code) and str(code).strip() in set(enabled_languages())


def set_enabled(codes: list[str]) -> dict[str, Any]:
    """Replace the enabled set. Unknown codes are rejected, not silently dropped."""
    if not codes:
        raise ValueError("no_languages")
    resolved: list[str] = []
    for code in codes:
        canonical = _canonical(code)
        if canonical is None:
            raise ValueError("unknown_language")
        resolved.append(canonical)
    data = dict(_load())
    data["enabled"] = list(dict.fromkeys(resolved))  # dedupe, keep order
    _save(data)
    return {"enabled": enabled_languages(), "known": sorted(SUPPORTED_LANGUAGES)}


def state() -> dict[str, Any]:
    """Full picture for the admin panel: what is known and what is enabled."""
    return {
        "enabled": enabled_languages(),
        "known": sorted(SUPPORTED_LANGUAGES),
        "labels": {
            code: SUPPORTED_LANGUAGES[code].get("name") or code for code in sorted(SUPPORTED_LANGUAGES)
        },
        "defaultEnabled": [c for c in (_canonical(x) for x in DEFAULT_ENABLED) if c],
    }