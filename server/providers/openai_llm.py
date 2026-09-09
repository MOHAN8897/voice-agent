"""OpenAI LLM adapter — wraps openai_brain_service + structured completions."""
from __future__ import annotations

import inspect
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from server.providers.base import LLMConfig


def extract_responses_text(response: Any) -> str:
    """Pull text from a Responses API object, including incomplete / truncated payloads."""
    text = getattr(response, "output_text", None) or ""
    if text:
        return str(text)
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        if isinstance(item, dict):
            if item.get("type") in ("message", "output_text"):
                for ch in item.get("content") or []:
                    if isinstance(ch, dict) and ch.get("text"):
                        parts.append(str(ch["text"]))
                    elif isinstance(ch, str):
                        parts.append(ch)
            elif item.get("text"):
                parts.append(str(item["text"]))
            continue
        item_type = getattr(item, "type", "")
        if item_type == "message":
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else None)
                if t:
                    parts.append(str(t))
        elif item_type == "output_text":
            t = getattr(item, "text", None)
            if t:
                parts.append(str(t))
    return "".join(parts)


def _repair_truncated_json(text: str) -> dict | None:
    """Close truncated JSON objects/strings enough to json.loads. None if salvage fails."""
    s = (text or "").rstrip()
    if not s.startswith("{"):
        return None
    in_string = False
    escape = False
    for ch in s:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
    if in_string:
        s += '"'
    opens = 0
    brackets = 0
    in_string = False
    escape = False
    for ch in s:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            opens += 1
        elif ch == "}":
            opens -= 1
        elif ch == "[":
            brackets += 1
        elif ch == "]":
            brackets -= 1
    s += "]" * max(0, brackets)
    s += "}" * max(0, opens)
    try:
        payload = json.loads(s)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def parse_structured_json(text: str) -> dict:
    """Parse a structured-completion payload, including markdown fences and truncated JSON."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("structured_completion returned empty text")
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
    candidates = [raw]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0:
        if end > start:
            candidates.append(raw[start : end + 1])
        candidates.append(raw[start:])
    seen: set[str] = set()
    last_err: json.JSONDecodeError | None = None
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        try:
            payload = json.loads(cand)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError as e:
            last_err = e
            repaired = _repair_truncated_json(cand)
            if repaired is not None:
                return repaired
    raise ValueError(f"structured_completion JSON parse failed: {last_err}") from last_err


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
        from server.realtime.models import http_openai_model, is_realtime_llm_model
        from server.services.openai_model_params import apply_generation_params
        from server.utils.http_clients import get_openai_client

        settings = get_settings()
        model = (config.model if config else None) or http_openai_model(settings)
        if is_realtime_llm_model(model):
            model = http_openai_model(settings)
        client = get_openai_client()
        create_kwargs: dict[str, Any] = {
            "model": model,
            "input": input_messages,
            "max_output_tokens": max_output_tokens or 800,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        apply_generation_params(
            create_kwargs,
            model=model,
            temperature=None,
            default_temperature=getattr(settings, "openai_temperature", 0.4),
            voice_optimized=True,
        )
        response = await client.responses.create(**create_kwargs)
        text = extract_responses_text(response).strip()
        if not text:
            return {}
        payload = parse_structured_json(text)
        if not isinstance(payload, dict):
            raise ValueError("structured_completion did not return an object")
        return payload
