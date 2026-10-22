"""DeepSeek LLM adapter — OpenAI-compatible API for dev/testing."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store
from server.providers.base import LLMConfig
from server.providers.openai_messages import to_chat_messages


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
            base_url=settings.deepseek_base_url,
        )

    async def stream_live_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        if schema is not None:
            async for chunk in self.stream_structured_turn(
                input_messages=input_messages, schema=schema, **kwargs
            ):
                yield chunk
            return
        settings = get_settings()
        model = kwargs.get("model") or kwargs.get("openai_model") or settings.deepseek_model
        client = self._client()
        messages = to_chat_messages(input_messages)
        if not messages:
            messages = [{"role": "user", "content": str(kwargs.get("transcript") or ".")}]
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
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
        from server.agent.conversation_manager import conversation_manager
        from server.services.openai_brain_service import _after_turn_memory

        session_id = str(kwargs.get("session_id") or "default")
        conversation_manager.add_turn(session_id, str(kwargs.get("transcript") or ""), full)
        _after_turn_memory(session_id, call_id=kwargs.get("call_id"))
        yield {"done": True, "text": full, "language_context": {}}

    async def stream_structured_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        from server.call.live_turn_schema import SpokenResponseExtractor

        settings = get_settings()
        model = kwargs.get("model") or kwargs.get("openai_model") or settings.deepseek_model
        client = self._client()
        messages = to_chat_messages(input_messages)
        if not messages:
            messages = [{"role": "user", "content": str(kwargs.get("transcript") or ".")}]
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": kwargs.get("max_output_tokens") or settings.max_response_length,
        }
        if schema:
            create_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "live_turn", "schema": schema, "strict": True},
            }
        stream = await client.chat.completions.create(**create_kwargs)
        extractor = SpokenResponseExtractor()
        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if not delta:
                continue
            spoken = extractor.feed(delta)
            if spoken:
                yield {"delta": spoken, "language_context": {}}
        from server.agent.conversation_manager import conversation_manager
        from server.services.openai_brain_service import _after_turn_memory

        session_id = str(kwargs.get("session_id") or "default")
        transcript = str(kwargs.get("transcript") or "")
        conversation_manager.add_turn(session_id, transcript, extractor.spoken_text)
        _after_turn_memory(session_id, call_id=kwargs.get("call_id"))
        yield {
            "done": True,
            "text": extractor.spoken_text,
            "memory_update": extractor.parse_memory_update(),
            "end_call": extractor.parse_end_call(),
            "memory_parse_failed": extractor.structured_parse_failed(),
            "language_context": {},
        }

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
            messages=to_chat_messages(input_messages) or [{"role": "user", "content": "."}],
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
