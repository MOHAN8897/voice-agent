"""Universal live-phone stack — configured in dev panel, applied to all SaaS calls."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from server.config.env import get_settings
from server.realtime.models import DEFAULT_REALTIME_MODEL, DEFAULT_REALTIME_VOICE
from server.services.dev_runtime import effective_app_environment
from server.services.pstn_stack import normalize_pstn_stack_override

logger = logging.getLogger(__name__)

_STACK_FILE = "saas_universal_phone_stack.json"


def _stack_path() -> Path:
    return get_settings().data_path / _STACK_FILE


def load_universal_phone_stack_raw() -> dict[str, Any] | None:
    path = _stack_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        logger.warning("could not read %s", path)
        return None


def save_universal_phone_stack_raw(stack: dict[str, Any]) -> dict[str, Any]:
    path = _stack_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stack, indent=2), encoding="utf-8")
    return stack


def resolve_platform_phone_stack_sync(language: str = "te-IN") -> dict[str, Any]:
    """Dev-configured stack, else env medium tier realtime_voice defaults (sync)."""
    lang = (language or "te-IN").strip() or "te-IN"
    stored = load_universal_phone_stack_raw()
    if stored and stored.get("stack_override"):
        base = dict(stored["stack_override"])
        # Provider/voice defaults are global; spoken language belongs to this agent.
        base["language"] = lang
        normalized, _ = normalize_pstn_stack_override(base, language=lang, tier="medium")
        return normalized or base

    if stored and stored.get("pipeline") == "realtime_voice":
        normalized, _ = normalize_pstn_stack_override({**stored, "language": lang}, language=lang, tier="medium")
        return normalized or stored

    # Fallback: production realtime_voice defaults (no per-agent tier).
    raw: dict[str, Any] = {
        "pipeline": "realtime_voice",
        "voice_flow": "realtime_e2e",
        "language": lang,
        "llm": {"provider": "openai", "model": DEFAULT_REALTIME_MODEL},
        "realtime_voice": {
            "voice": DEFAULT_REALTIME_VOICE,
            "turn_detection": "semantic_vad",
            "vad_eagerness": "high",
            "noise_reduction": "far_field",
            "speed": 1.0,
            "silence_ms": 250,
        },
    }
    try:
        from server.providers import resolve_stack
        from server.services.dev_runtime import effective_config_mode, effective_voice_tier

        app_env = effective_app_environment()
        tier = effective_voice_tier()
        resolved = resolve_stack(mode="env", tier=tier, environment=app_env)
        preview = resolved.to_safe_dict()
        llm = preview.get("llm") or {}
        if llm.get("model"):
            raw["llm"] = {"provider": llm.get("provider") or "openai", "model": llm["model"]}
    except Exception:
        pass

    normalized, _ = normalize_pstn_stack_override(raw, language=lang, tier="medium")
    return normalized or raw


async def resolve_platform_phone_stack(language: str = "te-IN") -> dict[str, Any]:
    return resolve_platform_phone_stack_sync(language)
