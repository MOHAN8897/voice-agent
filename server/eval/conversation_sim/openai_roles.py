"""OpenAI plays the caller and the judge, so Sarvam is never grading or talking to itself."""
from __future__ import annotations

import asyncio
import os
from typing import Any

CALLER_MODEL = os.getenv("SIM_CALLER_MODEL", "gpt-5.6-luna")
JUDGE_MODEL = os.getenv("SIM_JUDGE_MODEL", "gpt-5.5")


async def structured(model: str, system: str, user: str, schema: dict, name: str,
                     *, max_output_tokens: int = 1500, timeout: float = 90) -> dict[str, Any]:
    from server.providers import get_provider_registry
    from server.providers.base import LLMConfig
    from server.eval.conversation_sim.environment import ACTOR

    adapter = get_provider_registry().get_llm("openai")
    token = ACTOR.set("openai:" + name)
    try:
        async with asyncio.timeout(timeout):
            result = await adapter.structured_completion(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                schema, LLMConfig(provider="openai", model=model),
                schema_name=name, max_output_tokens=max_output_tokens)
    finally:
        ACTOR.reset(token)
    if not isinstance(result, dict):
        raise RuntimeError(f"{name}: OpenAI returned no structured object")
    return result
