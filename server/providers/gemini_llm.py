"""Gemini LLM adapter — same live-turn JSON, memory ops, and prefix-cache layout as OpenAI."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from server.call.live_turn_schema import SpokenResponseExtractor
from server.config.env import get_settings
from server.providers.base import LLMConfig
from server.providers.openai_messages import message_text, openai_input_to_gemini
from server.prompts.agent_voice_rules import unclear_fallback_for
from server.services.dev_secrets_store import dev_secrets_store
from server.utils.logger import log_brain, log_error

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _api_key() -> str:
    settings = get_settings()
    return (dev_secrets_store.effective_secret("gemini_api_key") or settings.gemini_api_key or "").strip()


def _model_id(raw: str | None) -> str:
    settings = get_settings()
    model = (raw or settings.gemini_model or "gemini-3.5-flash-lite").strip()
    if model.startswith("models/"):
        model = model[len("models/") :]
    return model


def thinking_config_for(model: str) -> dict[str, str] | None:
    """Lowest valid thinking level for live voice. 3.7/3.8 reject MINIMAL."""
    mid = (model or "").lower()
    if not mid.startswith("gemini-3"):
        return None
    if "flash-lite" in mid:
        return {"thinkingLevel": "MINIMAL"}
    return {"thinkingLevel": "LOW"}


def gemini_usage_from_metadata(meta: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(meta, dict):
        return {}
    prompt = int(meta.get("promptTokenCount") or meta.get("prompt_token_count") or 0)
    out = int(meta.get("candidatesTokenCount") or meta.get("candidates_token_count") or 0)
    total = int(meta.get("totalTokenCount") or meta.get("total_token_count") or 0)
    cached = int(
        meta.get("cachedContentTokenCount")
        or meta.get("cached_content_token_count")
        or 0
    )
    return {
        "input_tokens": prompt,
        "output_tokens": out,
        "total_tokens": total or (prompt + out),
        "cached_tokens": cached,
        "cache_write_tokens": 0,
    }


def _chunk_text(payload: dict[str, Any]) -> str:
    cands = payload.get("candidates") or []
    if not cands:
        return ""
    content = (cands[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    bits: list[str] = []
    for part in parts:
        if not isinstance(part, dict) or not part.get("text"):
            continue
        if part.get("thought"):
            continue
        bits.append(str(part["text"]))
    return "".join(bits)


def _ensure_user_last(contents: list[dict[str, Any]], transcript: str) -> list[dict[str, Any]]:
    if not contents:
        text = (transcript or "").strip() or "."
        return [{"role": "user", "parts": [{"text": text}]}]
    if contents[-1]["role"] != "user":
        text = (transcript or "").strip() or "."
        contents = list(contents)
        contents.append({"role": "user", "parts": [{"text": text}]})
    return contents


class GeminiLLMAdapter:
    provider_id = "gemini"

    def supports_structured_output(self) -> bool:
        return True

    def supports_prompt_caching(self) -> bool:
        return True

    def stream_live_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        if schema is not None:
            return self.stream_structured_turn(
                input_messages=input_messages, schema=schema, **kwargs
            )
        return self._stream(input_messages=input_messages, schema=None, **kwargs)

    def stream_structured_turn(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        return self._stream(input_messages=input_messages, schema=schema, **kwargs)

    async def _stream(
        self,
        input_messages: list[dict] | None = None,
        schema: dict | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict]:
        settings = get_settings()
        key = _api_key()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is missing — add it in Environment or .env")
        model = _model_id(kwargs.get("model") or kwargs.get("openai_model"))
        language_code = str(kwargs.get("language_code") or "te-IN")
        session_id = str(kwargs.get("session_id") or "default")
        transcript = str(kwargs.get("transcript") or "")
        system_instruction, contents = openai_input_to_gemini(input_messages)
        if not system_instruction:
            system_instruction = str(kwargs.get("brain_prompt") or "").strip()
        if not contents:
            extra: list[dict] = []
            projection = str(kwargs.get("memory_projection") or "").strip()
            rolling = str(kwargs.get("rolling_summary") or "").strip()
            if projection:
                extra.append({"role": "user", "parts": [{"text": f"[Memory projection]\n{projection}"}]})
            if rolling:
                extra.append({"role": "user", "parts": [{"text": f"[Rolling summary]\n{rolling}"}]})
            extra.append({"role": "user", "parts": [{"text": transcript or "."}]})
            contents = extra
        contents = _ensure_user_last(contents, transcript)

        gen: dict[str, Any] = {
            "maxOutputTokens": kwargs.get("max_output_tokens") or settings.max_response_length,
        }
        temp = kwargs.get("temperature")
        if temp is not None:
            gen["temperature"] = float(temp)
        think = thinking_config_for(model)
        if think:
            gen["thinkingConfig"] = think
        if schema:
            gen["responseMimeType"] = "application/json"
            gen["responseJsonSchema"] = schema
        body: dict[str, Any] = {"contents": contents, "generationConfig": gen}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        log_brain(
            "Gemini stream started",
            model=model,
            session=session_id,
            structured=bool(schema),
            cache_prefix=bool(system_instruction),
        )
        extractor = SpokenResponseExtractor() if schema else None
        plain_parts: list[str] = []
        usage: dict[str, int] = {}
        url = f"{_GEMINI_BASE}/{model}:streamGenerateContent"
        timeout = max(15.0, settings.request_timeout_ms / 1000)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    url,
                    params={"alt": "sse"},
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=body,
                ) as resp:
                    if resp.status_code >= 400:
                        err = (await resp.aread()).decode("utf-8", errors="replace")[:400]
                        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {err}")
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        data = line[5:].strip() if line.startswith("data:") else line.strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("error"):
                            raise RuntimeError(str(payload["error"])[:300])
                        meta = payload.get("usageMetadata") or payload.get("usage_metadata")
                        if isinstance(meta, dict):
                            usage = gemini_usage_from_metadata(meta)
                        delta = _chunk_text(payload)
                        if not delta:
                            continue
                        if extractor is not None:
                            spoken = extractor.feed(delta)
                        else:
                            plain_parts.append(delta)
                            spoken = delta
                        if spoken:
                            yield {"delta": spoken, "language_context": {}}
        except Exception as e:
            log_error("Gemini stream failed", err=str(e)[:400], model=model)
            raise

        if extractor is not None:
            full_text = extractor.spoken_text.strip() or unclear_fallback_for(language_code)
            memory_update = extractor.parse_memory_update()
            memory_parse_failed = extractor.structured_parse_failed()
            end_call = extractor.parse_end_call()
        else:
            full_text = "".join(plain_parts).strip() or unclear_fallback_for(language_code)
            memory_update = {"operations": []}
            memory_parse_failed = False
            end_call = {"should_end": False, "reason": "none", "farewell": ""}

        from server.agent.conversation_manager import conversation_manager
        from server.services.openai_brain_service import _after_turn_memory
        from server.services.prompt_cache_key import compute_cache_key
        from server.services.prompt_cache_tracker import prompt_cache_tracker

        conversation_manager.add_turn(session_id, transcript, full_text)
        _after_turn_memory(session_id, call_id=kwargs.get("call_id"))
        if system_instruction and usage:
            prompt_cache_tracker.record(
                cache_key=compute_cache_key(system_instruction, 2500),
                session_id=session_id,
                turn=conversation_manager.get_completed_turns(session_id),
                input_tokens=int(usage.get("input_tokens") or 0),
                cached_tokens=int(usage.get("cached_tokens") or 0),
                cache_write_tokens=int(usage.get("cache_write_tokens") or 0),
                request_id=None,
            )
        log_brain(
            "Gemini stream completed",
            model=model,
            session=session_id,
            chars=len(full_text),
            cached=usage.get("cached_tokens"),
        )
        yield {
            "done": True,
            "text": full_text,
            "language_context": {},
            "usage": usage,
            "memory_update": memory_update,
            "memory_parse_failed": memory_parse_failed,
            "end_call": end_call,
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
        key = _api_key()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is missing — add it in Environment or .env")
        model = _model_id(config.model if config else None)
        system_instruction, contents = openai_input_to_gemini(input_messages)
        contents = _ensure_user_last(contents, message_text(input_messages[-1]) if input_messages else ".")
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_output_tokens or 800,
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        url = f"{_GEMINI_BASE}/{model}:generateContent"
        timeout = max(15.0, settings.request_timeout_ms / 1000)
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:400]}")
            payload = resp.json()
        text = _chunk_text(payload if isinstance(payload, dict) else {})
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
