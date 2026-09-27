"""Resolve compiled brain locked for a call (Test Studio session vs published agent)."""
from __future__ import annotations

from typing import Literal

BrainSource = Literal[
    "test_studio_session",
    "published_agent",
    "session_legacy",
    "none",
]


def classify_brain_source(version_label: str | None) -> BrainSource:
    label = (version_label or "").strip().lower()
    if not label:
        return "none"
    if label.startswith("session-v") or label == "session":
        return "test_studio_session"
    if label.startswith("session"):
        return "session_legacy"
    return "published_agent"


async def resolve_locked_compiled_brain(
    agent_id: str,
    *,
    session_id: str | None = None,
) -> tuple[str | None, str | None, BrainSource]:
    """Same precedence as CallLifecycleService._lock_compiled_brain."""
    from server.config.env import get_settings
    from server.utils.logger import logger

    if session_id:
        from server.agent.instruction_store import instruction_store

        meta = instruction_store.get_with_meta(session_id)
        brain = (meta.get("brainPrompt") or "").strip()
        version = meta.get("compiledVersion") or 0
        if brain and (
            meta.get("present")
            or version
            or meta.get("agentBrief")
            or meta.get("agentScript")
        ):
            label = f"session-v{version}" if version else "session"
            return label, brain, classify_brain_source(label)

    from server.brain.compiled_brain_service import compiled_brain_service

    try:
        snap = await compiled_brain_service.get_active_for_agent(agent_id)
        text = (snap.get("compiled_text") or "").strip()
        if text:
            version = str(snap.get("compiled_version") or "")
            return version or None, text, classify_brain_source(version)
    except Exception as e:
        logger.warning(f"[CALL] compiled brain lock skipped: {str(e)[:160]}")

    settings = get_settings()
    if settings.use_versioned_brains:
        return None, None, "none"

    if session_id:
        from server.agent.instruction_store import instruction_store

        brain = instruction_store.get_brain_prompt(session_id)
        if brain and brain.strip():
            return "session-default", brain.strip(), "session_legacy"

    return None, None, "none"
