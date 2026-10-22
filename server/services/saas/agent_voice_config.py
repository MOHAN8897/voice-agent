"""Per-agent phone voice settings stored in business brain draft (SaaS console)."""
from __future__ import annotations

import json
import logging
from typing import Any

from server.brain.business_brain_store import business_brain_store

logger = logging.getLogger(__name__)

SAAS_VOICE_SECTION_TITLE = "saas_voice_config"


def parse_voice_config_from_sections(sections: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not sections:
        return {}
    for s in sections:
        title = str(s.get("title") or "")
        if title != SAAS_VOICE_SECTION_TITLE:
            continue
        raw = str(s.get("raw_text") or "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            logger.warning("invalid saas_voice_config json for agent")
            return {}
    return {}


async def load_agent_voice_config(agent_id: str) -> dict[str, Any]:
    if not agent_id:
        return {}
    cfg: dict[str, Any] = {}
    try:
        sections = await business_brain_store.get_sections(agent_id)
        cfg = parse_voice_config_from_sections(sections)
    except Exception:
        logger.debug("voice config load failed agent=%s", agent_id, exc_info=True)
    if not cfg:
        try:
            from server.brain.agent_service import agent_service
            agent_dict = await agent_service.get_agent(agent_id)
            if agent_dict and agent_dict.get("voice_settings"):
                vs = agent_dict["voice_settings"]
                if isinstance(vs, dict) and (vs.get("realtimeVoice") or vs.get("voiceId")):
                    return vs
        except Exception:
            pass
    return cfg
