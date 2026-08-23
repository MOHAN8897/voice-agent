"""
OpenAI Brain service — server/services/openai_brain_service.py
Uses official `openai` SDK, Responses API (recommended). Falls back to Chat Completions if needed.
"""
from __future__ import annotations

import asyncio
import time

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, RateLimitError

from server.agent.conversation_manager import conversation_manager
from server.agent.instruction_builder import build_agent_instructions, build_input_messages
from server.agent.language_resolver import resolve_language
from server.config.env import get_settings
from server.prompts.system_prompt import CORE_SYSTEM_PROMPT
from server.services.openai_model_params import apply_generation_params
from server.utils.logger import log_brain, log_error, log_perf
import json


def _get_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _is_quota_error(e: Exception) -> bool:
    """Permanent billing errors must NOT be retried (industry: fail fast)."""
    body = getattr(e, "body", None)
    text = json.dumps(body) if isinstance(body, dict) else str(e)
    return "insufficient_quota" in text or "quota" in text.lower() and "exceeded" in text.lower()


async def generate_response(
    *,
    transcript: str,
    language_code: str = "te-IN",
    session_id: str = "default",
    user_instructions: str = "",
    business_instructions: str | None = None,
    response_style: str | None = None,
    openai_model: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    timeout_ms: int | None = None,
) -> dict:
    """
    Calls OpenAI Responses API with Telugu-first system prompt + wrapped
    BEHAVIOUR (how to respond) + BUSINESS (client domain knowledge) + history.
    Runtime overrides (openai_model/temperature/max_output_tokens) come from Fine-tune console.
    Returns {text, language_context, usage, request_id}
    Preserves original transcript language — no te→en translation.
    Industry: priority System > Core > Behaviour > Business > History > Turn.
    """
    settings = get_settings()
    timeout_s = (timeout_ms or settings.request_timeout_ms) / 1000
    use_model = openai_model or settings.openai_model
    use_max_tokens = max_output_tokens or settings.max_response_length
    language_context = resolve_language(language_code, transcript)
    history = conversation_manager.get_history(session_id)
    # Dynamic prompting: pull stored behaviour/business/style unless explicitly given
    if not user_instructions or business_instructions is None or response_style is None:
        try:
            from server.agent.instruction_store import instruction_store

            if not user_instructions:
                user_instructions = instruction_store.get_behaviour(session_id)
            if business_instructions is None:
                business_instructions = instruction_store.get_business(session_id)
            if response_style is None:
                response_style = instruction_store.get_style(session_id)
        except Exception:
            pass

    developer_instructions = build_agent_instructions(
        core_instructions=CORE_SYSTEM_PROMPT,
        behaviour_instructions=user_instructions,
        business_instructions=business_instructions or "",
        language=language_context["responseLanguage"],
        response_style=response_style,
    )
    input_messages = build_input_messages(
        transcript=transcript,
        history=history,
        developer_instructions=developer_instructions,
    )

    log_brain("Request started", model=use_model, historyLen=len(history), lang=language_context)

    client = _get_client()
    retries = 0
    max_retries = settings.max_retries

    create_kwargs: dict = {
        "model": use_model,
        "instructions": CORE_SYSTEM_PROMPT,
        "input": input_messages,
        "max_output_tokens": use_max_tokens,
        "store": False,
    }
    apply_generation_params(
        create_kwargs,
        model=use_model,
        temperature=temperature,
        default_temperature=settings.openai_temperature,
        voice_optimized=True,
    )
    log_brain(
        "CONFIG",
        model=use_model,
        max_output_tokens=use_max_tokens,
        temperature=create_kwargs.get("temperature"),
        reasoning=create_kwargs.get("reasoning"),
        history_len=len(history),
    )

    while True:
        try:
            # Responses API — primary
            response = await asyncio.wait_for(
                client.responses.create(**create_kwargs),
                timeout=timeout_s,
            )
            # Extract text: SDK provides output_text helper
            text = getattr(response, "output_text", None)
            if not text:
                # Fallback: iterate output items
                parts = []
                for item in getattr(response, "output", []) or []:
                    # item may be dict or object
                    if isinstance(item, dict):
                        if item.get("type") in ("message", "output_text"):
                            c = item.get("content") or []
                            for ch in c:
                                if isinstance(ch, dict) and ch.get("text"):
                                    parts.append(ch["text"])
                                elif isinstance(ch, str):
                                    parts.append(ch)
                    else:
                        # SDK object
                        item_type = getattr(item, "type", "")
                        if item_type == "message":
                            for c in getattr(item, "content", []) or []:
                                t = getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else None)
                                if t:
                                    parts.append(t)
                text = "".join(parts) or ""

            text = text.strip()
            if not text:
                text = "క్షమించండి, నాకు అర్థం కాలేదు. మళ్లీ ప్రయత్నించండి."

            # Update history
            conversation_manager.add_turn(session_id, transcript, text)

            usage = getattr(response, "usage", None)
            # usage may be object; normalize
            if usage and not isinstance(usage, dict):
                try:
                    usage = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "total_tokens": usage.total_tokens}
                except Exception:
                    usage = None

            log_brain("Response received", chars=len(text), usage=usage)
            return {
                "text": text,
                "language_context": language_context,
                "usage": usage,
                "request_id": getattr(response, "id", None),
            }

        except asyncio.TimeoutError as e:
            if retries < max_retries:
                retries += 1
                backoff = 0.2 * (2**retries)
                await asyncio.sleep(backoff)
                continue
            raise AppError(ErrorCode.TIMEOUT, provider="openai", retryable=True, cause=e) from e

        except RateLimitError as e:
            if _is_quota_error(e):
                # Billing problem — retrying cannot help; fail fast with actionable message
                raise AppError(
                    ErrorCode.AUTH_ERROR,
                    "OpenAI quota exceeded — check your plan/billing at platform.openai.com.",
                    provider="openai", status_code=429, cause=e,
                ) from e
            if retries < max_retries:
                retries += 1
                await asyncio.sleep(0.5 * (2**retries))
                continue
            raise AppError(ErrorCode.RATE_LIMIT, provider="openai", retryable=True, cause=e) from e

        except (APITimeoutError, APIConnectionError) as e:
            if retries < max_retries:
                retries += 1
                await asyncio.sleep(0.3 * (2**retries))
                continue
            raise AppError(ErrorCode.NETWORK_ERROR, provider="openai", retryable=True, cause=e) from e

        except APIStatusError as e:
            status = getattr(e, "status_code", 500)
            if status in (401, 403):
                raise AppError(ErrorCode.AUTH_ERROR, provider="openai", status_code=status, cause=e) from e
            if status == 429:
                try:
                    body = getattr(e, "body", None)
                    text = json.dumps(body) if isinstance(body, dict) else str(e)
                    quota = "insufficient_quota" in text
                except Exception:
                    quota = False
                if quota:
                    raise AppError(
                        ErrorCode.AUTH_ERROR,
                        "OpenAI quota exceeded — check your plan/billing at platform.openai.com.",
                        provider="openai", status_code=429, cause=e,
                    ) from e
                if retries < max_retries:
                    retries += 1
                    await asyncio.sleep(0.5 * (2**retries))
                    continue
                raise AppError(ErrorCode.RATE_LIMIT, provider="openai", status_code=429, retryable=True, cause=e) from e
            if status in (400, 422):
                raise AppError(ErrorCode.VALIDATION_ERROR, provider="openai", status_code=status, cause=e) from e
            if 500 <= status < 600 and retries < max_retries:
                retries += 1
                await asyncio.sleep(0.4 * (2**retries))
                continue
            raise AppError(ErrorCode.PROVIDER_ERROR, provider="openai", status_code=status, retryable=status >= 500, cause=e) from e

        except AppError:
            raise
        except Exception as e:
            log_error("Brain unexpected", err=str(e)[:500])
            raise AppError(ErrorCode.PROVIDER_ERROR, provider="openai", cause=e) from e


async def generate_response_stream(
    *,
    transcript: str,
    language_code: str = "te-IN",
    session_id: str = "default",
    user_instructions: str = "",
    business_instructions: str | None = None,
    response_style: str | None = None,
    openai_model: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    timeout_ms: int | None = None,
):
    """
    Streaming variant — yields SSE chunks {delta, done, language_context, request_id}
    Uses Responses API stream=True, events: response.output_text.delta
    Dual-channel prompting (behaviour + business) same as non-streaming.
    """

    settings = get_settings()
    use_model = openai_model or settings.openai_model
    language_context = resolve_language(language_code, transcript)
    history = conversation_manager.get_history(session_id)
    if not user_instructions or business_instructions is None or response_style is None:
        try:
            from server.agent.instruction_store import instruction_store

            if not user_instructions:
                user_instructions = instruction_store.get_behaviour(session_id)
            if business_instructions is None:
                business_instructions = instruction_store.get_business(session_id)
            if response_style is None:
                response_style = instruction_store.get_style(session_id)
        except Exception:
            pass
    developer_instructions = build_agent_instructions(
        core_instructions=CORE_SYSTEM_PROMPT,
        behaviour_instructions=user_instructions,
        business_instructions=business_instructions or "",
        language=language_context["responseLanguage"],
        response_style=response_style,
    )
    input_messages = build_input_messages(
        transcript=transcript,
        history=history,
        developer_instructions=developer_instructions,
    )
    log_brain("Stream started", model=use_model, historyLen=len(history))
    client = _get_client()
    # We accumulate to update history on complete
    full_text_parts: list[str] = []
    create_kwargs: dict = {
        "model": use_model,
        "instructions": CORE_SYSTEM_PROMPT,
        "input": input_messages,
        "max_output_tokens": max_output_tokens or settings.max_response_length,
        "store": False,
        "stream": True,
    }
    apply_generation_params(
        create_kwargs,
        model=use_model,
        temperature=temperature,
        default_temperature=settings.openai_temperature,
        voice_optimized=True,
    )
    log_brain(
        "CONFIG",
        model=use_model,
        max_output_tokens=max_output_tokens or settings.max_response_length,
        temperature=create_kwargs.get("temperature"),
        reasoning=create_kwargs.get("reasoning"),
        history_len=len(history),
    )
    log_perf("BRAIN_STARTED", model=use_model, session=session_id)
    t_stream = time.perf_counter()
    first_delta_logged = False
    try:
        stream = await client.responses.create(**create_kwargs)
        async for event in stream:
            # event is typed, has .type and data
            event_type = getattr(event, "type", None) or (event.get("type") if isinstance(event, dict) else None)
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", None) or (event.get("delta") if isinstance(event, dict) else "")
                if delta:
                    if not first_delta_logged:
                        first_delta_logged = True
                        log_perf(
                            "BRAIN_FIRST_DELTA",
                            ms=round((time.perf_counter() - t_stream) * 1000),
                            model=use_model,
                            session=session_id,
                        )
                    full_text_parts.append(delta)
                    yield {"delta": delta, "language_context": language_context}
            elif event_type == "response.completed":
                break
            elif event_type == "error":
                err_msg = getattr(event, "error", None) or str(event)
                raise AppError(ErrorCode.PROVIDER_ERROR, provider="openai", cause=Exception(err_msg))
        full_text = "".join(full_text_parts).strip() or "క్షమించండి, నాకు అర్థం కాలేదు."
        conversation_manager.add_turn(session_id, transcript, full_text)
        log_perf(
            "BRAIN_COMPLETED",
            ms=round((time.perf_counter() - t_stream) * 1000),
            chars=len(full_text),
            model=use_model,
            session=session_id,
        )
        yield {"done": True, "text": full_text, "language_context": language_context}
        log_brain("Stream completed", chars=len(full_text))
    except AppError:
        raise
    except Exception as e:
        log_error("Brain stream unexpected", err=str(e)[:500])
        raise AppError(ErrorCode.PROVIDER_ERROR, provider="openai", cause=e) from e
