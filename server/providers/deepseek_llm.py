"""DeepSeek LLM adapter — OpenAI-compatible API for dev/testing."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store
from server.providers.base import LLMConfig


class DeepSeekLLMAdapter:
    provider_id = "deepseek"

    def supports_structured_output(self) -> bool:
        return True

    def supports_prompt_caching(self) -> bool:
        return False

    def _client(self) -> AsyncOpenAI:
        settings = get_settings()
        return AsyncOpenAI(
            api_key=dev_secrets_store.effective_secret("deepseek_api_key") or settings.deepseek_api_key or "",
            base_url="https://api.deepseek.com",
        )

    async def stream_live_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        settings = get_settings()
        model = kwargs.get("model") or settings.deepseek_model
        client = self._client()
        messages = input_messages or []
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages if m.get("role") != "developer"],
            stream=True,
            max_tokens=kwargs.get("max_output_tokens") or settings.max_response_length,
        )
        text_parts: list[str] = []
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                text_parts.append(delta)
                yield {"delta": delta, "language_context": {}}
        full = "".join(text_parts)
        yield {"done": True, "text": full, "language_context": {}}

    async def structured_completion(
        self,
        input_messages: list[dict],
        schema: dict,
        config: LLMConfig | None = None,
        *,
        schema_name: str = "structured",
        max_output_tokens: int | None = None,
    ) -> dict:
        settings = get_settings()
        model = (config.model if config else None) or settings.deepseek_model
        client = self._client()
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": m.get("role", "user"), "content": m.get("content", "")} for m in input_messages],
            max_tokens=max_output_tokens or 800,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        )
        text = response.choices[0].message.content or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
