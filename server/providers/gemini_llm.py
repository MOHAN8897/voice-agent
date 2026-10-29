"""Gemini LLM adapter — same live-turn JSON, memory ops, and prefix-cache layout as OpenAI."""
from __future__ import annotations

import copy
import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from server.call.live_turn_schema import SpokenResponseExtractor
from server.config.env import get_settings
from server.providers.base import LLMConfig
from server.providers.llm_protocol import IncompleteTurnError
from server.providers.openai_messages import message_text, openai_input_to_gemini
from server.services.dev_secrets_store import dev_secrets_store
from server.utils.logger import log_brain, log_error

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_STRUCTURED_REPLY_FUNCTION = "VOXLY_RETURN_SPOKEN_TURN"


def _function_declarations(tools: list[Any]) -> list[dict[str, Any]]:
    declarations = []
    for raw in tools:
        if not isinstance(raw, dict) or raw.get("type", "function") != "function":
            raise ValueError("Gemini requires function tool declarations")
        function = raw.get("function") if isinstance(raw.get("function"), dict) else raw
        name = function.get("name")
        parameters = function.get("parameters")
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name)
                or name == _STRUCTURED_REPLY_FUNCTION or not isinstance(parameters, dict)):
            raise ValueError("Gemini function declaration is invalid")
        declarations.append({"name": name, "description": str(function.get("description") or ""),
                             "parametersJsonSchema": copy.deepcopy(parameters)})
    if len({item["name"] for item in declarations}) != len(declarations):
        raise ValueError("Gemini function names must be unique")
    return declarations


def _function_config(choice: Any) -> dict[str, Any]:
    if choice in (None, "auto"):
        return {"mode": "AUTO"}
    if choice == "none":
        return {"mode": "NONE"}
    if choice == "required":
        return {"mode": "ANY"}
    if isinstance(choice, dict):
        function = choice.get("function") or choice
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            return {"mode": "ANY", "allowedFunctionNames": [function["name"]]}
    raise ValueError("Gemini tool choice is invalid")


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


def _safe_token_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _modality_name(item: Any) -> str:
    raw = item.get("modality") if isinstance(item, dict) else getattr(item, "modality", None)
    return str(getattr(raw, "name", None) or raw or "").upper()


def _modality_count(item: Any) -> int:
    if isinstance(item, dict):
        return _safe_token_count(item.get("tokenCount") or item.get("token_count"))
    return _safe_token_count(getattr(item, "token_count", None) or getattr(item, "tokenCount", None))


def _split_modality_tokens(details: Any) -> tuple[int, int, int]:
    """Return (audio, image_or_video, other) from Live/generateContent detail lists."""
    audio = 0
    image = 0
    other = 0
    if not isinstance(details, list):
        return 0, 0, 0
    for item in details:
        n = _modality_count(item)
        name = _modality_name(item)
        if "AUDIO" in name:
            audio += n
        elif "IMAGE" in name or "VIDEO" in name:
            image += n
        else:
            other += n
    return audio, image, other


def gemini_usage_from_metadata(
    meta: dict[str, Any] | None,
    *,
    native_audio: bool = False,
) -> dict[str, int]:
    if not isinstance(meta, dict):
        return {}
    prompt = _safe_token_count(meta.get("promptTokenCount") or meta.get("prompt_token_count"))
    out = _safe_token_count(
        meta.get("candidatesTokenCount")
        or meta.get("candidates_token_count")
        or meta.get("responseTokenCount")
        or meta.get("response_token_count")
    )
    total = _safe_token_count(meta.get("totalTokenCount") or meta.get("total_token_count"))
    cached = _safe_token_count(
        meta.get("cachedContentTokenCount") or meta.get("cached_content_token_count")
    )
    prompt_details = (
        meta.get("promptTokensDetails")
        or meta.get("prompt_tokens_details")
        or []
    )
    response_details = (
        meta.get("responseTokensDetails")
        or meta.get("response_tokens_details")
        or meta.get("candidatesTokensDetails")
        or meta.get("candidates_tokens_details")
        or []
    )
    audio_in, image_in, other_in = _split_modality_tokens(prompt_details)
    audio_out, image_out, other_out = _split_modality_tokens(response_details)
    if prompt <= 0:
        prompt = audio_in + image_in + other_in
    if out <= 0:
        out = audio_out + image_out + other_out
    has_details = bool(prompt_details) or bool(response_details)
    if not has_details:
        # generateContent: missing details must not be billed as audio.
        # Live S2S: prompt without details is system text; spoken reply is audio out.
        audio_in = 0
        image_in = 0
        audio_out = out if native_audio else 0
        image_out = 0
    return {
        "input_tokens": prompt,
        "output_tokens": out,
        "total_tokens": total or (prompt + out),
        "cached_tokens": cached,
        "cache_write_tokens": 0,
        "input_audio_tokens": min(prompt, audio_in),
        "output_audio_tokens": min(out, audio_out),
        "input_image_tokens": min(prompt, image_in),
        "output_image_tokens": min(out, image_out),
        "cached_audio_tokens": min(audio_in, cached) if audio_in else 0,
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
        from server.providers.llm_protocol import text_llm_api_mode

        text_llm_api_mode("gemini", model, kwargs.get("api_mode"))
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
        declarations = _function_declarations(kwargs.get("tools") or [])
        # Gemini 3+ supports JSON output together with functions. Earlier models
        # use a forced response function for the same live-turn JSON contract.
        legacy_reply = bool(schema and declarations and not model.startswith(("gemini-3", "gemini-4")))
        if schema and not legacy_reply:
            gen["responseMimeType"] = "application/json"
            gen["responseJsonSchema"] = schema
        body: dict[str, Any] = {"contents": contents, "generationConfig": gen}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if declarations:
            function_config = _function_config(kwargs.get("tool_choice"))
            if legacy_reply:
                declarations.append({"name": _STRUCTURED_REPLY_FUNCTION,
                    "description": "Return the caller-facing response and conversation state when no external action is needed.",
                    "parametersJsonSchema": schema})
                function_config = {"mode": "ANY"}
                if kwargs.get("tool_choice") == "none":
                    function_config["allowedFunctionNames"] = [_STRUCTURED_REPLY_FUNCTION]
            body["tools"] = [{"functionDeclarations": declarations}]
            body["toolConfig"] = {"functionCallingConfig": function_config}

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
        native_parts: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        legacy_response: dict[str, Any] | None = None
        seen_ids: set[str] = set()
        completed = False
        finish_reason: str | None = None
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
                        await resp.aread()
                        raise RuntimeError(f"Gemini request failed (HTTP {resp.status_code})")
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip() if line.startswith("data:") else line.strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise RuntimeError("Gemini returned malformed SSE data") from exc
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("error"):
                            raise RuntimeError("Gemini stream failed")
                        meta = payload.get("usageMetadata") or payload.get("usage_metadata")
                        if isinstance(meta, dict):
                            usage = gemini_usage_from_metadata(meta)
                        candidates = payload.get("candidates") or []
                        candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
                        stop_reason = str(candidate.get("finishReason") or "").strip().upper()
                        content = candidate.get("content") or {}
                        for part in content.get("parts") or []:
                            if not isinstance(part, dict):
                                continue
                            native_parts.append(copy.deepcopy(part))
                            function = part.get("functionCall")
                            if not isinstance(function, dict):
                                continue
                            name = function.get("name")
                            arguments = function.get("args", {})
                            if not isinstance(name, str) or not name or not isinstance(arguments, dict):
                                raise RuntimeError("Gemini returned an invalid function call")
                            if legacy_reply and name == _STRUCTURED_REPLY_FUNCTION:
                                if legacy_response is not None:
                                    raise RuntimeError("Gemini returned duplicate spoken responses")
                                legacy_response = arguments
                                continue
                            identifier = str(function.get("id") or uuid.uuid4().hex)
                            if identifier in seen_ids:
                                raise RuntimeError("Gemini returned duplicate function call identifiers")
                            if (not tool_calls and model.startswith(("gemini-3", "gemini-4"))
                                    and not part.get("thoughtSignature")):
                                raise RuntimeError("Gemini function call is missing its thought signature")
                            seen_ids.add(identifier)
                            tool_calls.append({"id": identifier, "type": "function", "function": {
                                "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}})
                        delta = _chunk_text(payload)
                        if delta:
                            if extractor is not None:
                                spoken = extractor.feed(delta)
                            else:
                                plain_parts.append(delta)
                                spoken = delta
                            if spoken and not declarations:
                                yield {
                                    "delta": spoken,
                                    "language_context": {},
                                    "close_preview": (
                                        extractor.preview_decision()
                                        if extractor is not None
                                        else None
                                    ),
                                    "action_preview": (
                                        extractor.preview_action_claim()
                                        if extractor is not None
                                        else None
                                    ),
                                }
                        if stop_reason:
                            finish_reason = stop_reason.lower()
                            if stop_reason == "STOP":
                                completed = True
                            else:
                                # Text in this final candidate was already spoken above.
                                raise IncompleteTurnError(
                                    provider=self.provider_id,
                                    finish_reason=finish_reason,
                                    raw_finish_reason=stop_reason,
                                    partial_text=(
                                        extractor.spoken_text
                                        if extractor is not None
                                        else "".join(plain_parts)
                                    ),
                                    usage=usage,
                                )
        except Exception as e:
            log_error("Gemini stream failed", error_type=type(e).__name__, model=model)
            raise

        if not completed and not tool_calls:
            raise IncompleteTurnError(
                provider=self.provider_id,
                finish_reason=finish_reason or "no_finish_reason",
                raw_finish_reason=finish_reason or "no_finish_reason",
                partial_text=(
                    extractor.spoken_text if extractor is not None else "".join(plain_parts)
                ),
                usage=usage,
            )

        if tool_calls:
            if not completed:
                raise IncompleteTurnError(
                    provider=self.provider_id,
                    finish_reason=finish_reason or "interrupted",
                    raw_finish_reason=finish_reason or "interrupted",
                    partial_text=(
                        extractor.spoken_text if extractor is not None else "".join(plain_parts)
                    ),
                    usage=usage,
                )
            if legacy_response is not None:
                raise RuntimeError("Gemini combined a final response with an unfinished action")
            yield {"done": True, "text": "", "language_context": {}, "usage": usage,
                "tool_calls": tool_calls, "_gemini_content": {"role": "model", "parts": native_parts},
                "finish_reason": finish_reason or "stop",
                "memory_update": {"operations": []}, "memory_parse_failed": False,
                "end_call": {"should_end": False, "reason": "none", "farewell": ""}}
            return
        if legacy_response is not None:
            if not completed:
                raise RuntimeError("Gemini spoken response was interrupted before completion")
            from jsonschema import ValidationError, validate

            try:
                validate(legacy_response, schema)
            except ValidationError as exc:
                raise RuntimeError("Gemini returned an invalid structured spoken response") from exc
            extractor.feed(json.dumps(legacy_response, ensure_ascii=False))
        if extractor is not None:
            full_text = extractor.spoken_text.strip()
            memory_update = extractor.parse_memory_update()
            memory_parse_failed = extractor.structured_parse_failed()
            end_call = extractor.parse_end_call()
            action_claimed = extractor.parse_action_claim()
        else:
            full_text = "".join(plain_parts).strip()
            memory_update = {"operations": []}
            memory_parse_failed = False
            end_call = {"should_end": False, "reason": "none", "farewell": ""}
            action_claimed = None
        if not full_text or (declarations and memory_parse_failed):
            raise IncompleteTurnError(
                provider=self.provider_id,
                finish_reason="empty" if not full_text else "incomplete_schema",
                partial_text=full_text,
                usage=usage,
            )
        if declarations:
            yield {"delta": full_text, "language_context": {}}

        from server.agent.conversation_manager import conversation_manager
        from server.services.prompt_cache_key import compute_cache_key
        from server.services.prompt_cache_tracker import prompt_cache_tracker

        # Transport adapters do not mutate dialogue or working memory. The
        # orchestrator owns the single confirmed assistant turn for this call.
        if system_instruction and usage:
            prompt_cache_tracker.record(
                cache_key=compute_cache_key(system_instruction, 2500),
                session_id=session_id,
                turn=conversation_manager.get_completed_turns(session_id) + 1,
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
            "finish_reason": finish_reason or "stop",
            "memory_update": memory_update,
            "memory_parse_failed": memory_parse_failed,
            "end_call": end_call,
            "action_claimed": action_claimed,
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
        if config is not None and config.temperature is not None:
            body["generationConfig"]["temperature"] = config.temperature
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        url = f"{_GEMINI_BASE}/{model}:generateContent"
        # Background structured generation is allowed 45s by its caller.
        # A 15s transport read timeout prematurely exhausted both attempts.
        timeout = max(40.0, settings.request_timeout_ms / 1000)
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"Gemini request failed (HTTP {resp.status_code})")
            payload = resp.json()
        text = _chunk_text(payload if isinstance(payload, dict) else {})
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
