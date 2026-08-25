"""Memory extraction fallback — used only when structured same-LLM parse fails SLO."""
from __future__ import annotations

from typing import Any

from server.call.memory_manager import memory_manager
from server.config.env import get_settings
from server.utils.logger import logger


async def extract_and_apply(
    call_id: str,
    *,
    turn_seq: int,
    user_text: str,
    assistant_text: str,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Fallback path. Default is off — CD-016 is the primary live path.
    When enabled, one cheap structured completion proposes ops; memory_manager applies them.
    """
    settings = get_settings()
    if not settings.memory_extraction_fallback:
        return None
    try:
        from server.providers import get_provider_registry
        from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA
        from server.providers.base import LLMConfig

        adapter = get_provider_registry().get_llm("openai")
        messages = [
            {
                "role": "user",
                "content": (
                    "Extract memory operations for this voice-call turn. "
                    "Return JSON only.\n"
                    f"[User]\n{user_text}\n[Assistant]\n{assistant_text}\n"
                    f"[Current memory]\n{snapshot or {}}"
                ),
            }
        ]
        payload = await adapter.structured_completion(
            messages,
            LIVE_TURN_JSON_SCHEMA,
            LLMConfig(provider="openai", model=settings.post_call_llm_model),
            schema_name="memory_extraction",
            max_output_tokens=settings.memory_extraction_max_output_tokens,
        )
        ops = (payload.get("memory_update") or {}).get("operations") or []
        return memory_manager.apply_proposals(call_id, ops, turn_seq=turn_seq, source="extraction_fallback")
    except Exception as e:
        logger.warning(f"[MEMORY] extraction fallback failed call={call_id}: {str(e)[:200]}")
        return None
