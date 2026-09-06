"""OpenAI LLM adapter — wraps openai_brain_service + structured completions."""
from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator
from typing import Any

from server.providers.base import LLMConfig


class OpenAILLMAdapter:
    provider_id = "openai"

    def supports_structured_output(self) -> bool:
        return True

    def supports_prompt_caching(self) -> bool:
        return True

    async def stream_live_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        """Wrap existing openai_brain_service streaming — same live path, registry-indirection."""
        from server.services.openai_brain_service import generate_response_stream

        allowed = set(inspect.signature(generate_response_stream).parameters)
        stream_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        if not stream_kwargs.get("openai_model"):
            mapped = kwargs.get("openai_model") or kwargs.get("model")
            if mapped and "openai_model" in allowed:
                stream_kwargs["openai_model"] = mapped
        if input_messages is not None:
            stream_kwargs["input_messages"] = input_messages
        if schema is not None:
            stream_kwargs["live_turn_schema"] = schema
        async for event in generate_response_stream(**stream_kwargs):
            yield event

    def stream_structured_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        return self.stream_live_turn(input_messages=input_messages, schema=schema, **kwargs)

    async def structured_completion(
        self,
        input_messages: list[dict],
        schema: dict,
        config: LLMConfig | None = None,
        *,
        schema_name: str = "structured",
        max_output_tokens: int | None = None,
    ) -> dict:
        from server.config.env import get_settings
        from server.utils.http_clients import get_openai_client

        settings = get_settings()
        model = (config.model if config else None) or settings.post_call_llm_model or settings.openai_model
        client = get_openai_client()
        response = await client.responses.create(
            model=model,
            input=input_messages,
            max_output_tokens=max_output_tokens or 800,
            store=False,
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        )
        text = getattr(response, "output_text", None) or ""
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"structured_completion JSON parse failed: {e}") from e
        if not isinstance(payload, dict):
            raise ValueError("structured_completion did not return an object")
        return payload
