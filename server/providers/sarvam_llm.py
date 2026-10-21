"""Sarvam Chat Completions V2 adapter for an explicitly selected model."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from server.call.live_turn_schema import SpokenResponseExtractor
from server.config.env import get_settings
from server.providers.base import LLMConfig
from server.providers.openai_messages import message_text
from server.services.dev_secrets_store import dev_secrets_store

SARVAM_CHAT_COMPLETIONS_V2_URL = "https://api.sarvam.ai/v2/chat/completions"


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _usage_from_payload(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {}
    prompt_tokens = _safe_count(usage.get("prompt_tokens"))
    completion_tokens = _safe_count(usage.get("completion_tokens"))
    prompt_details = usage.get("prompt_tokens_details")
    completion_details = usage.get("completion_tokens_details")
    cached_tokens = (
        _safe_count(prompt_details.get("cached_tokens")) if isinstance(prompt_details, dict) else 0
    )
    reasoning_tokens = (
        _safe_count(completion_details.get("reasoning_tokens"))
        if isinstance(completion_details, dict)
        else 0
    )
    normalized = {
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "total_tokens": _safe_count(usage.get("total_tokens")) or prompt_tokens + completion_tokens,
        "cached_tokens": min(prompt_tokens, cached_tokens),
        "cache_write_tokens": 0,
    }
    if reasoning_tokens:
        normalized["reasoning_tokens"] = min(completion_tokens, reasoning_tokens)
    return normalized


def _chat_messages(
    input_messages: list[dict[str, Any]] | None, transcript: str | None
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for original in input_messages or []:
        if not isinstance(original, dict):
            continue
        role = str(original.get("role") or "").strip().lower()
        if role not in {"system", "developer", "user", "assistant", "tool"}:
            continue
        content = original.get("content")
        if not isinstance(content, str):
            content = message_text(original)
        message: dict[str, Any] = {"role": role, "content": content}
        if role == "tool":
            call_id = original.get("tool_call_id")
            if call_id:
                message["tool_call_id"] = str(call_id)
            if original.get("name"):
                message["name"] = str(original["name"])
        if role == "assistant" and isinstance(original.get("tool_calls"), list):
            message["tool_calls"] = original["tool_calls"]
        if content or message.get("tool_calls"):
            messages.append(message)

    if not messages and (transcript or "").strip():
        messages.append({"role": "user", "content": (transcript or "").strip()})
    if not messages:
        raise ValueError("Sarvam LLM requires conversation messages from the resolved turn")
    return messages


def _stream_tool_call_deltas(calls_by_index: dict[int, dict[str, Any]], raw_calls: Any) -> None:
    if not isinstance(raw_calls, list):
        return
    for raw in raw_calls:
        if not isinstance(raw, dict):
            continue
        try:
            index = int(raw.get("index", 0))
        except (TypeError, ValueError):
            continue
        call = calls_by_index.setdefault(
            index,
            {"type": "function", "id": "", "function": {"name": "", "arguments": ""}},
        )
        if raw.get("id"):
            call["id"] = str(raw["id"])
        if raw.get("type"):
            call["type"] = str(raw["type"])
        function = raw.get("function")
        if not isinstance(function, dict):
            continue
        if function.get("name"):
            call["function"]["name"] += str(function["name"])
        if function.get("arguments"):
            call["function"]["arguments"] += str(function["arguments"])


class SarvamLLMAdapter:
    """Adapter code availability does not imply V2 beta access for an API key."""

    provider_id = "sarvam"

    def __init__(self, *, api_key: str | None = None) -> None:
        self._provided_api_key = api_key

    def supports_structured_output(self) -> bool:
        return True

    def supports_prompt_caching(self) -> bool:
        # Session-affinity caching is opt-in and is not enabled by this adapter.
        return False

    def _api_key(self) -> str:
        settings = get_settings()
        return (
            self._provided_api_key
            or dev_secrets_store.effective_secret("sarvam_api_key")
            or settings.sarvam_api_key
            or ""
        ).strip()

    @staticmethod
    def _model(kwargs: dict[str, Any]) -> str:
        config = kwargs.get("config")
        model = kwargs.get("model") or getattr(config, "model", None)
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Sarvam LLM requires the model selected in the resolved stack")
        return model.strip()

    @staticmethod
    def _timeout() -> httpx.Timeout:
        timeout_s = max(0.1, get_settings().request_timeout_ms / 1000)
        return httpx.Timeout(
            timeout=timeout_s,
            connect=min(timeout_s, 10.0),
            read=timeout_s,
            write=timeout_s,
            pool=timeout_s,
        )

    def _headers(self) -> dict[str, str]:
        key = self._api_key()
        if not key:
            raise RuntimeError("SARVAM_API_KEY is not configured")
        return {"api-subscription-key": key, "Content-Type": "application/json"}

    @staticmethod
    def _max_tokens(kwargs: dict[str, Any]) -> int:
        config = kwargs.get("config")
        raw = (
            kwargs.get("max_output_tokens")
            or getattr(config, "max_tokens", None)
            or get_settings().max_response_length
        )
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Sarvam LLM requires a positive output token limit") from exc
        if value <= 0:
            raise ValueError("Sarvam LLM requires a positive output token limit")
        return value

    @staticmethod
    def _temperature(kwargs: dict[str, Any]) -> float | None:
        config = kwargs.get("config")
        raw = kwargs.get("temperature")
        if raw is None:
            raw = getattr(config, "temperature", None)
        return float(raw) if raw is not None else None

    @staticmethod
    def _response_format(schema: dict[str, Any], schema_name: str) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        }

    def _request_body(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        kwargs: dict[str, Any],
        stream: bool,
        schema: dict[str, Any] | None = None,
        schema_name: str = "live_turn",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": self._max_tokens(kwargs),
            "stream": stream,
        }
        temperature = self._temperature(kwargs)
        if temperature is not None:
            body["temperature"] = temperature
        if schema is not None:
            body["response_format"] = self._response_format(schema, schema_name)
        tools = kwargs.get("tools")
        if isinstance(tools, list) and tools:
            body["tools"] = tools
        if kwargs.get("tool_choice") is not None:
            body["tool_choice"] = kwargs["tool_choice"]
        if kwargs.get("parallel_tool_calls") is not None:
            body["parallel_tool_calls"] = bool(kwargs["parallel_tool_calls"])
        reasoning_effort = kwargs.get("reasoning_effort")
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    def stream_live_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        return self._stream(
            input_messages=input_messages,
            schema=schema,
            **kwargs,
        )

    def stream_structured_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        return self._stream(
            input_messages=input_messages,
            schema=schema,
            **kwargs,
        )

    async def _stream(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        if not self._api_key():
            raise RuntimeError("SARVAM_API_KEY is not configured")
        model = self._model(kwargs)
        messages = _chat_messages(input_messages, kwargs.get("transcript"))
        body = self._request_body(
            model=model,
            messages=messages,
            kwargs=kwargs,
            stream=True,
            schema=schema,
            schema_name=str(kwargs.get("schema_name") or "live_turn"),
        )
        extractor = SpokenResponseExtractor() if schema is not None else None
        plain_parts: list[str] = []
        usage: dict[str, int] = {}
        tool_calls: dict[int, dict[str, Any]] = {}
        buffer_output = bool(kwargs.get("tools"))
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            try:
                async with client.stream(
                    "POST",
                    SARVAM_CHAT_COMPLETIONS_V2_URL,
                    headers=self._headers(),
                    json=body,
                ) as response:
                    if response.status_code >= 400:
                        raise RuntimeError(f"Sarvam Chat Completions HTTP {response.status_code}")
                    async for line in response.aiter_lines():
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise RuntimeError(
                                "Sarvam Chat Completions returned malformed SSE data"
                            ) from exc
                        if not isinstance(payload, dict):
                            raise TypeError("Sarvam Chat Completions returned malformed SSE data")
                        if payload.get("error"):
                            raise RuntimeError("Sarvam Chat Completions stream failed")
                        next_usage = _usage_from_payload(payload)
                        if next_usage:
                            usage = next_usage
                        choices = payload.get("choices")
                        if not isinstance(choices, list) or not choices:
                            continue
                        choice = choices[0]
                        delta = choice.get("delta") if isinstance(choice, dict) else None
                        if not isinstance(delta, dict):
                            continue
                        _stream_tool_call_deltas(tool_calls, delta.get("tool_calls"))
                        content = delta.get("content")
                        if isinstance(content, list):
                            content = "".join(
                                str(part.get("text") or "")
                                for part in content
                                if isinstance(part, dict)
                            )
                        if not isinstance(content, str) or not content:
                            continue
                        if extractor is not None:
                            spoken = extractor.feed(content)
                        else:
                            plain_parts.append(content)
                            spoken = content
                        if spoken and not buffer_output:
                            yield {"delta": spoken, "language_context": {}}
            except asyncio.CancelledError:
                raise
            except httpx.TimeoutException as exc:
                raise TimeoutError("Sarvam Chat Completions request timed out") from exc
            except httpx.HTTPError as exc:
                raise RuntimeError("Sarvam Chat Completions transport failed") from exc

        full_text = (
            extractor.spoken_text.strip() if extractor is not None else "".join(plain_parts).strip()
        )
        completed_tool_calls = [tool_calls[index] for index in sorted(tool_calls)]
        if not full_text and not completed_tool_calls:
            raise RuntimeError("Sarvam Chat Completions returned an empty response")

        event: dict[str, Any] = {
            "done": True,
            "text": full_text,
            "language_context": {},
            "usage": usage,
        }
        if completed_tool_calls:
            event["tool_calls"] = completed_tool_calls
        if extractor is not None:
            event.update(
                {
                    "memory_update": extractor.parse_memory_update(),
                    "end_call": extractor.parse_end_call(),
                    "memory_parse_failed": extractor.structured_parse_failed(),
                }
            )

        # Do not speak a prospective tool response before the authorized tool
        # result is known. The orchestrator either executes the tools and asks
        # for a final structured answer, or releases this text if no tool call
        # was requested.
        if buffer_output and not completed_tool_calls and full_text:
            yield {"delta": full_text, "language_context": {}}

        yield event

    async def structured_completion(
        self,
        input_messages: list[dict],
        schema: dict,
        config: LLMConfig | None = None,
        *,
        schema_name: str = "structured",
        max_output_tokens: int | None = None,
    ) -> dict:
        if not self._api_key():
            raise RuntimeError("SARVAM_API_KEY is not configured")
        model = (config.model if config else "").strip()
        if not model:
            raise ValueError("Sarvam LLM requires the model selected in the resolved stack")
        messages = _chat_messages(input_messages, None)
        kwargs: dict[str, Any] = {"max_output_tokens": max_output_tokens}
        if config is not None:
            kwargs["config"] = config
        body = self._request_body(
            model=model,
            messages=messages,
            kwargs=kwargs,
            stream=False,
            schema=schema,
            schema_name=schema_name,
        )
        if max_output_tokens is None and config is not None and config.max_tokens is not None:
            body["max_tokens"] = config.max_tokens
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            try:
                response = await client.post(
                    SARVAM_CHAT_COMPLETIONS_V2_URL,
                    headers=self._headers(),
                    json=body,
                )
            except asyncio.CancelledError:
                raise
            except httpx.TimeoutException as exc:
                raise TimeoutError("Sarvam Chat Completions request timed out") from exc
            except httpx.HTTPError as exc:
                raise RuntimeError("Sarvam Chat Completions transport failed") from exc
        if response.status_code >= 400:
            raise RuntimeError(f"Sarvam Chat Completions HTTP {response.status_code}")
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Sarvam Chat Completions returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise TypeError("Sarvam Chat Completions returned malformed JSON")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("Sarvam Chat Completions returned an empty response")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise TypeError("Sarvam Chat Completions returned a malformed response")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Sarvam Chat Completions returned an empty structured response")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Sarvam Chat Completions returned malformed structured JSON"
            ) from exc
        if not isinstance(result, dict):
            raise TypeError("Sarvam Chat Completions structured response must be an object")
        return result
