"""Production phone-call stack for SaaS subscribers (same path as new PSTN realtime flow)."""
from __future__ import annotations

from typing import Any

from server.realtime.models import DEFAULT_REALTIME_MODEL, DEFAULT_REALTIME_VOICE
from server.services.pstn_stack import normalize_pstn_stack_override
from server.services.saas.agent_voice_config import load_agent_voice_config
from server.services.saas.platform_phone_stack import resolve_platform_phone_stack
from server.services.saas.voice_catalog import phone_voice_catalog


def realtime_voice_catalog() -> list[dict[str, str]]:
    return phone_voice_catalog()


def _agent_spoken_language(agent: dict[str, Any], voice_cfg: dict[str, Any]) -> str:
    """Settings languages[] win over stale voice-section language."""
    langs = agent.get("languages") or []
    if isinstance(langs, list) and langs:
        code = str(langs[0] or "").strip()
        if code:
            return code
    single = str(agent.get("language") or "").strip()
    if single:
        return single
    voice_lang = str(voice_cfg.get("language") or "").strip()
    if voice_lang:
        return voice_lang
    return "en-US"


async def saas_stack_override_for_agent(agent: dict[str, Any]) -> dict[str, Any]:
    """Platform stack from dev panel; agent only overrides spoken voice, speed, and language."""
    agent_id = str(agent.get("agent_id") or agent.get("id") or "")
    voice_cfg = await load_agent_voice_config(agent_id) if agent_id else {}
    lang = _agent_spoken_language(agent, voice_cfg)
    stack = await resolve_platform_phone_stack(lang)
    rv = dict(stack.get("realtime_voice") or {})
    realtime_voice = str(voice_cfg.get("realtimeVoice") or voice_cfg.get("voiceId") or rv.get("voice") or DEFAULT_REALTIME_VOICE)
    rv["voice"] = realtime_voice
    if voice_cfg.get("speed") is not None:
        rv["speed"] = voice_cfg.get("speed")
    stack["language"] = lang
    stack["realtime_voice"] = rv
    normalized, _ = normalize_pstn_stack_override(stack, language=lang, tier="medium")
    return normalized or stack


def saas_stack_override(language: str) -> dict[str, Any]:
    """Backward-compatible minimal override (language only). Prefer saas_stack_override_for_agent."""
    raw: dict[str, Any] = {
        "pipeline": "realtime_voice",
        "language": language,
        "llm": {"provider": "openai", "model": DEFAULT_REALTIME_MODEL},
        "realtime_voice": {"voice": DEFAULT_REALTIME_VOICE},
    }
    normalized, _ = normalize_pstn_stack_override(raw, language=language, tier="medium")
    return normalized or raw
