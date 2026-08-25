"""
OpenAI Brain service — single brain prompt, prompt caching, token logging.
"""
from __future__ import annotations

import asyncio
import time
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from server.agent.conversation_manager import conversation_manager
from server.agent.instruction_builder import build_brain_request_input, build_live_input
from server.agent.instruction_store import instruction_store
from server.agent.language_resolver import resolve_language
from server.agent.session_memory import session_memory
from server.config.env import get_settings
from server.services.brain_budget import resolve_brain_budget
from server.services.memory_summarizer import (
    compact_history_summary,
    should_update_summary,
    summary_token_estimate,
)
from server.services.openai_model_params import apply_generation_params
from server.services.prompt_cache_key import caching_enabled, compute_cache_key, compute_cache_key_versioned
from server.services.prompt_cache_tracker import prompt_cache_tracker
from server.agent.brain_prompt_composer import compose_brain_prompt, estimate_tokens
from server.utils.errors import AppError, ErrorCode
from server.utils.http_clients import get_openai_client
from server.utils.logger import log_brain, log_error, log_perf
from server.utils.metrics import metrics
from server.utils.token_usage import normalize_usage
import json


def _get_client():
    return get_openai_client()


def _is_quota_error(e: Exception) -> bool:
    body = getattr(e, "body", None)
    text = json.dumps(body) if isinstance(body, dict) else str(e)
    return "insufficient_quota" in text or "quota" in text.lower() and "exceeded" in text.lower()


def _log_token_usage(
    usage_norm: dict,
    *,
    session_id: str,
    turn: int,
    model: str,
    request_id: str | None,
    brain_est: int,
    budget: int,
    history_est: int = 0,
    transcript_est: int = 0,
    summary_est: int = 0,
    cache_key: str | None = None,
    ttft_ms: int | None = None,
    total_ms: int | None = None,
    prep_ms: int | None = None,
) -> None:
    if not usage_norm:
        return
    inp = usage_norm.get("input_tokens", 0)
    out = usage_norm.get("output_tokens", 0)
    total = usage_norm.get("total_tokens", 0)
    cached = usage_norm.get("cached_tokens", 0)
    cache_write = usage_norm.get("cache_write_tokens", 0)
    uncached = max(0, int(inp) - int(cached or 0))
    layers = {
        "brain": brain_est,
        "history": history_est,
        "summary": summary_est,
        "transcript": transcript_est,
    }

    cache_event = prompt_cache_tracker.record(
        cache_key=cache_key,
        session_id=session_id,
        turn=turn,
        input_tokens=int(inp or 0),
        cached_tokens=int(cached or 0),
        cache_write_tokens=int(cache_write or 0),
        request_id=request_id,
    )
    cache_event_name = cache_event.event if cache_event else None

    log_brain(
        "TURN",
        call=session_id,
        turn=turn,
        input=inp,
        cached=cached,
        uncached=uncached,
        output=out,
        cache_write=cache_write,
        brainEst=brain_est,
        historyEst=history_est,
        summaryEst=summary_est,
        transcriptEst=transcript_est,
        budget=budget,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        prep_ms=prep_ms,
        model=model,
        request_id=request_id,
        cache_key=cache_key,
        cache_event=cache_event_name,
    )

    log_brain(
        "TOKENS",
        input=inp,
        output=out,
        total=total,
        cached=cached,
        cache_write=cache_write,
        brainEst=brain_est,
        historyEst=history_est,
        summaryEst=summary_est,
        transcriptEst=transcript_est,
        budget=budget,
        model=model,
        session=session_id,
        turn=turn,
        request_id=request_id,
    )
    metrics.record_brain_tokens(usage_norm, layers=layers)
    metrics.record_brain_turn(
        call_id=session_id,
        turn=turn,
        usage=usage_norm,
        layers=layers,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        prep_ms=prep_ms,
        request_id=request_id,
        cache_key=cache_key,
        cache_event=cache_event_name,
        model=model,
    )

    if cached > 0 and inp > 0:
        log_brain(
            "CACHE_HIT",
            rate=round(cached / inp, 3),
            cached=cached,
            input=inp,
            session=session_id,
            turn=turn,
            model=model,
        )
    elif cache_write > 0:
        diag = {
            "cache_write": cache_write,
            "input": inp,
            "session": session_id,
            "turn": turn,
            "model": model,
            "cache_key": cache_key,
        }
        if cache_event:
            diag["seconds_since_last_hit"] = cache_event.seconds_since_last_hit
            diag["seconds_since_last_write"] = cache_event.seconds_since_last_write
            diag["turns_since_last_write"] = cache_event.turns_since_last_write
            diag["global_turn"] = cache_event.global_turn
        log_brain("CACHE_REWRITE", **diag)


def _instruction_provided(value: str | None) -> bool:
    return value is not None and bool(str(value).strip())


def _resolve_instruction_overrides(
    session_id: str,
    user_instructions: str | None,
    business_instructions: str | None,
    response_style: str | None,
    brain_prompt: str | None = None,
) -> tuple[bool, str, str | None, str | None, str | None]:
    """Empty strings count as not provided. All absent → use stored brainPrompt."""
    if _instruction_provided(brain_prompt):
        return False, "", None, None, str(brain_prompt).strip()
    if not any(_instruction_provided(v) for v in (user_instructions, business_instructions, response_style)):
        return True, "", None, None, None
    try:
        ui = (
            str(user_instructions).strip()
            if _instruction_provided(user_instructions)
            else instruction_store.get_behaviour(session_id)
        )
        bi = (
            str(business_instructions).strip()
            if _instruction_provided(business_instructions)
            else instruction_store.get_business(session_id)
        )
        rs = (
            str(response_style).strip()
            if _instruction_provided(response_style)
            else instruction_store.get_style(session_id)
        )
    except Exception:
        ui = str(user_instructions or "").strip()
        bi = str(business_instructions or "").strip() or None
        rs = str(response_style or "").strip() or None
    return False, ui, bi, rs, None


def _resolve_brain_text(
    *,
    session_id: str,
    language: str,
    user_instructions: str,
    business_instructions: str | None,
    response_style: str | None,
    budget: int,
    use_stored_brain: bool,
    call_id: str | None = None,
) -> tuple[str, str | None]:
    """Returns (brain_text, compiled_brain_version or None)."""
    if call_id:
        from server.call.call_context import get as get_call_ctx

        ctx = get_call_ctx(call_id)
        if ctx and ctx.compiled_brain_text:
            return ctx.compiled_brain_text, ctx.compiled_brain_version

    settings = get_settings()
    if settings.use_versioned_brains:
        from server.brain.compiled_brain_service import get_cached_compiled_brain

        snap = get_cached_compiled_brain()
        if snap:
            return snap["compiled_text"], snap["compiled_version"]
    if use_stored_brain:
        return (
            instruction_store.get_brain_prompt(
                session_id,
                language=language,
                budget_tokens=budget,
            ),
            None,
        )
    return (
        compose_brain_prompt(
            behaviour=user_instructions or instruction_store.get_behaviour(session_id),
            business=business_instructions if business_instructions is not None else instruction_store.get_business(session_id),
            language=language,
            style=response_style or instruction_store.get_style(session_id),
        ),
        None,
    )


def _resolve_memory_blocks(
    *,
    session_id: str,
    call_id: str | None,
    memory_projection: str | None,
    rolling_summary: str | None,
) -> tuple[str | None, str | None, str]:
    """Return (projection C, rolling summary for input[2], legacy session_summary).

    None means the orchestrator did not supply a block (may look up B).
    Empty string means the orchestrator resolved it and it is empty (do not look up B).
    """
    settings = get_settings()
    projection_provided = memory_projection is not None
    rolling_provided = rolling_summary is not None
    projection = (memory_projection or "").strip() or None
    rolling = (rolling_summary or "").strip() or None
    legacy = ""

    if call_id and settings.working_memory_enabled:
        if not projection_provided or not rolling_provided:
            from server.call.memory_manager import memory_manager
            from server.call.memory_projection import build as build_projection

            snap = memory_manager.get_snapshot(call_id)
            if not rolling_provided:
                rolling = (snap.get("summary") or "").strip() or None
            if not projection_provided:
                projection = build_projection(snap, include_summary=not rolling) or None
        return projection, rolling, ""

    if settings.enable_session_summary:
        legacy = session_memory.get_summary(session_id)
    return projection, rolling, legacy


def _prepare_brain_context(
    *,
    session_id: str,
    transcript: str,
    language_code: str,
    user_instructions: str,
    business_instructions: str | None,
    response_style: str | None,
    openai_model: str | None,
    use_stored_brain: bool,
    brain_override: str | None = None,
    call_id: str | None = None,
    memory_projection: str | None = None,
    rolling_summary: str | None = None,
) -> tuple[dict, list, str, int, int, str, bool, int, str, int, int, int, str | None]:
    settings = get_settings()
    use_model = openai_model or settings.openai_model
    language_context = resolve_language(language_code, transcript)
    budget = resolve_brain_budget(session_id)

    if brain_override:
        brain_text = brain_override
        compiled_version = None
    else:
        brain_text, compiled_version = _resolve_brain_text(
            session_id=session_id,
            language=language_context["responseLanguage"],
            user_instructions=user_instructions,
            business_instructions=business_instructions,
            response_style=response_style,
            budget=budget,
            use_stored_brain=use_stored_brain,
            call_id=call_id,
        )
    brain_est = estimate_tokens(brain_text)

    projection, rolling, legacy_summary = _resolve_memory_blocks(
        session_id=session_id,
        call_id=call_id,
        memory_projection=memory_projection,
        rolling_summary=rolling_summary,
    )
    session_summary = rolling or legacy_summary

    history = conversation_manager.get_context_for_brain(
        session_id,
        max_turns=settings.brain_context_turns,
    )
    history_est = estimate_tokens(" ".join(str(m.get("content", "")) for m in history))
    summary_est = summary_token_estimate(session_summary)
    transcript_est = estimate_tokens(transcript)

    enable_cache = caching_enabled(use_model, brain_est)
    builder_kwargs = dict(
        history=history,
        transcript=transcript,
        enable_cache=enable_cache,
        session_summary=legacy_summary or None,
        rolling_summary=rolling,
        memory_projection=projection,
    )
    if settings.use_versioned_brains and compiled_version:
        input_messages = build_live_input(compiled_brain_text=brain_text, **builder_kwargs)
    else:
        input_messages = build_brain_request_input(brain_prompt=brain_text, **builder_kwargs)
    return (
        language_context,
        input_messages,
        use_model,
        brain_est,
        budget,
        brain_text,
        enable_cache,
        len(history),
        session_summary,
        history_est,
        summary_est,
        transcript_est,
        compiled_version,
    )


def _apply_cache_kwargs(
    create_kwargs: dict,
    *,
    brain_text: str,
    budget: int,
    enable_cache: bool,
    compiled_version: str | None = None,
) -> None:
    if not enable_cache:
        return
    settings = get_settings()
    if compiled_version:
        create_kwargs["prompt_cache_key"] = compute_cache_key_versioned(compiled_version, budget)
    else:
        create_kwargs["prompt_cache_key"] = compute_cache_key(brain_text, budget)
    create_kwargs["prompt_cache_options"] = {
        "mode": "explicit",
        "ttl": settings.prompt_cache_ttl,
    }


def _after_turn_memory(session_id: str, *, call_id: str | None = None) -> None:
    settings = get_settings()
    if call_id and settings.working_memory_enabled:
        return
    if not settings.enable_session_summary:
        return
    turn_count = session_memory.record_turn(session_id)
    if not should_update_summary(turn_count, settings.summary_every_n_turns):
        return
    full_history = conversation_manager.get_history(session_id)
    summary = compact_history_summary(full_history)
    if summary:
        session_memory.set_summary(session_id, summary)


def _structured_live_turn_enabled(*, call_id: str | None, explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    return bool(call_id) and get_settings().working_memory_enabled


def _spoken_and_memory(raw_text: str) -> tuple[str, dict, bool]:
    from server.call.live_turn_schema import SpokenResponseExtractor

    extractor = SpokenResponseExtractor()
    extractor.feed(raw_text)
    spoken = (extractor.spoken_text or raw_text).strip()
    return spoken, extractor.parse_memory_update(), extractor.structured_parse_failed()


async def generate_response(
    *,
    transcript: str,
    language_code: str = "te-IN",
    session_id: str = "default",
    user_instructions: str | None = None,
    business_instructions: str | None = None,
    response_style: str | None = None,
    brain_prompt: str | None = None,
    openai_model: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    timeout_ms: int | None = None,
    call_id: str | None = None,
    memory_projection: str | None = None,
    rolling_summary: str | None = None,
    structured_live_turn: bool | None = None,
    input_messages: list | None = None,
) -> dict:
    settings = get_settings()
    timeout_s = (timeout_ms or settings.request_timeout_ms) / 1000
    use_max_tokens = max_output_tokens or settings.max_response_length

    use_stored_brain, user_instructions, business_instructions, response_style, brain_override = _resolve_instruction_overrides(
        session_id,
        user_instructions,
        business_instructions,
        response_style,
        brain_prompt,
    )

    t0 = time.perf_counter()
    turn = conversation_manager.get_turn_number(session_id)

    (
        language_context,
        built_input,
        use_model,
        brain_est,
        budget,
        brain_text,
        enable_cache,
        history_len,
        session_summary,
        history_est,
        summary_est,
        transcript_est,
        compiled_version,
    ) = _prepare_brain_context(
        session_id=session_id,
        transcript=transcript,
        language_code=language_code,
        user_instructions=user_instructions or "",
        business_instructions=business_instructions,
        response_style=response_style,
        openai_model=openai_model,
        use_stored_brain=use_stored_brain,
        brain_override=brain_override,
        call_id=call_id,
        memory_projection=memory_projection,
        rolling_summary=rolling_summary,
    )
    if not input_messages:
        input_messages = built_input
    prep_ms = int((time.perf_counter() - t0) * 1000)
    prep_ms = max(prep_ms, 0)
    cache_key = (
        compute_cache_key_versioned(compiled_version, budget)
        if enable_cache and compiled_version
        else compute_cache_key(brain_text, budget) if enable_cache else None
    )

    log_brain(
        "Request started",
        model=use_model,
        session=session_id,
        turn=turn,
        historyLen=history_len,
        brainEst=brain_est,
        budget=budget,
        caching=enable_cache,
        cache_key=cache_key,
        summary=bool(session_summary),
        prep_ms=prep_ms,
    )

    client = _get_client()
    retries = 0
    max_retries = settings.max_retries

    create_kwargs: dict = {
        "model": use_model,
        "input": input_messages,
        "max_output_tokens": use_max_tokens,
        "store": False,
    }
    use_structured = _structured_live_turn_enabled(call_id=call_id, explicit=structured_live_turn)
    if use_structured:
        from server.call.live_turn_schema import TEXT_FORMAT_LIVE_TURN

        create_kwargs["text"] = TEXT_FORMAT_LIVE_TURN
    _apply_cache_kwargs(
        create_kwargs,
        brain_text=brain_text,
        budget=budget,
        enable_cache=enable_cache,
        compiled_version=compiled_version,
    )
    apply_generation_params(
        create_kwargs,
        model=use_model,
        temperature=temperature,
        default_temperature=settings.openai_temperature,
        voice_optimized=True,
        reasoning_effort=reasoning_effort,
    )
    log_brain(
        "CONFIG",
        model=use_model,
        max_output_tokens=use_max_tokens,
        temperature=create_kwargs.get("temperature"),
        reasoning=create_kwargs.get("reasoning"),
        caching=enable_cache,
        brainEst=brain_est,
        budget=budget,
        cache_key=cache_key,
    )

    t_api0 = time.perf_counter()
    while True:
        try:
            response = await asyncio.wait_for(
                client.responses.create(**create_kwargs),
                timeout=timeout_s,
            )
            text = getattr(response, "output_text", None)
            if not text:
                parts = []
                for item in getattr(response, "output", []) or []:
                    if isinstance(item, dict):
                        if item.get("type") in ("message", "output_text"):
                            c = item.get("content") or []
                            for ch in c:
                                if isinstance(ch, dict) and ch.get("text"):
                                    parts.append(ch["text"])
                                elif isinstance(ch, str):
                                    parts.append(ch)
                    else:
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

            memory_update = {"operations": []}
            memory_parse_failed = False
            if use_structured:
                text, memory_update, memory_parse_failed = _spoken_and_memory(text)
                if not text:
                    text = "క్షమించండి, నాకు అర్థం కాలేదు. మళ్లీ ప్రయత్నించండి."

            conversation_manager.add_turn(session_id, transcript, text)
            _after_turn_memory(session_id, call_id=call_id)

            usage_norm = normalize_usage(getattr(response, "usage", None))
            request_id = getattr(response, "id", None)
            total_ms = int((time.perf_counter() - t_api0) * 1000)
            _log_token_usage(
                usage_norm,
                session_id=session_id,
                turn=turn,
                model=use_model,
                request_id=request_id,
                brain_est=brain_est,
                budget=budget,
                history_est=history_est,
                transcript_est=transcript_est,
                summary_est=summary_est,
                cache_key=cache_key,
                total_ms=total_ms,
                prep_ms=prep_ms,
            )

            log_brain("Response received", chars=len(text), usage=usage_norm)
            return {
                "text": text,
                "language_context": language_context,
                "usage": usage_norm,
                "request_id": request_id,
                "memory_update": memory_update,
                "memory_parse_failed": memory_parse_failed,
            }

        except asyncio.TimeoutError as e:
            if retries < max_retries:
                retries += 1
                await asyncio.sleep(0.2 * (2**retries))
                continue
            raise AppError(ErrorCode.TIMEOUT, provider="openai", retryable=True, cause=e) from e

        except RateLimitError as e:
            if _is_quota_error(e):
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
                    text_err = json.dumps(body) if isinstance(body, dict) else str(e)
                    quota = "insufficient_quota" in text_err
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
    user_instructions: str | None = None,
    business_instructions: str | None = None,
    response_style: str | None = None,
    brain_prompt: str | None = None,
    openai_model: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    timeout_ms: int | None = None,
    call_id: str | None = None,
    memory_projection: str | None = None,
    rolling_summary: str | None = None,
    structured_live_turn: bool | None = None,
    live_turn_schema: dict | None = None,
    input_messages: list | None = None,
):
    settings = get_settings()
    use_max_tokens = max_output_tokens or settings.max_response_length

    use_stored_brain, user_instructions, business_instructions, response_style, brain_override = _resolve_instruction_overrides(
        session_id,
        user_instructions,
        business_instructions,
        response_style,
        brain_prompt,
    )

    t0 = time.perf_counter()
    turn = conversation_manager.get_turn_number(session_id)

    (
        language_context,
        built_input,
        use_model,
        brain_est,
        budget,
        brain_text,
        enable_cache,
        history_len,
        session_summary,
        history_est,
        summary_est,
        transcript_est,
        compiled_version,
    ) = _prepare_brain_context(
        session_id=session_id,
        transcript=transcript,
        language_code=language_code,
        user_instructions=user_instructions or "",
        business_instructions=business_instructions,
        response_style=response_style,
        openai_model=openai_model,
        use_stored_brain=use_stored_brain,
        brain_override=brain_override,
        call_id=call_id,
        memory_projection=memory_projection,
        rolling_summary=rolling_summary,
    )
    if not input_messages:
        input_messages = built_input
    prep_ms = int((time.perf_counter() - t0) * 1000)
    prep_ms = max(prep_ms, 0)
    cache_key = (
        compute_cache_key_versioned(compiled_version, budget)
        if enable_cache and compiled_version
        else compute_cache_key(brain_text, budget) if enable_cache else None
    )

    log_brain(
        "Stream started",
        model=use_model,
        session=session_id,
        turn=turn,
        historyLen=history_len,
        brainEst=brain_est,
        budget=budget,
        caching=enable_cache,
        cache_key=cache_key,
        summary=bool(session_summary),
        prep_ms=prep_ms,
    )
    client = _get_client()
    full_text_parts: list[str] = []
    create_kwargs: dict = {
        "model": use_model,
        "input": input_messages,
        "max_output_tokens": use_max_tokens,
        "store": False,
        "stream": True,
    }
    use_structured = _structured_live_turn_enabled(call_id=call_id, explicit=structured_live_turn) or live_turn_schema is not None
    if use_structured:
        from server.call.live_turn_schema import TEXT_FORMAT_LIVE_TURN, SpokenResponseExtractor

        create_kwargs["text"] = (
            {"format": {"type": "json_schema", "name": "live_turn", "strict": True, "schema": live_turn_schema}}
            if live_turn_schema
            else TEXT_FORMAT_LIVE_TURN
        )
        extractor = SpokenResponseExtractor()
    else:
        extractor = None
    _apply_cache_kwargs(
        create_kwargs,
        brain_text=brain_text,
        budget=budget,
        enable_cache=enable_cache,
        compiled_version=compiled_version,
    )
    apply_generation_params(
        create_kwargs,
        model=use_model,
        temperature=temperature,
        default_temperature=settings.openai_temperature,
        voice_optimized=True,
        reasoning_effort=reasoning_effort,
    )
    log_brain(
        "CONFIG",
        model=use_model,
        max_output_tokens=use_max_tokens,
        temperature=create_kwargs.get("temperature"),
        reasoning=create_kwargs.get("reasoning"),
        caching=enable_cache,
        brainEst=brain_est,
        budget=budget,
        cache_key=cache_key,
        structured=use_structured,
    )
    log_perf("BRAIN_STARTED", model=use_model, session=session_id, turn=turn, prep_ms=prep_ms)
    t_stream = time.perf_counter()
    first_delta_logged = False
    ttft_ms: int | None = None
    stream_usage: dict = {}
    request_id: str | None = None
    try:
        stream = await client.responses.create(**create_kwargs)
        async for event in stream:
            event_type = getattr(event, "type", None) or (event.get("type") if isinstance(event, dict) else None)
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", None) or (event.get("delta") if isinstance(event, dict) else "")
                if delta:
                    spoken_delta = extractor.feed(delta) if extractor is not None else delta
                    if spoken_delta and not first_delta_logged:
                        first_delta_logged = True
                        ttft_ms = round((time.perf_counter() - t_stream) * 1000)
                        log_perf(
                            "BRAIN_FIRST_DELTA",
                            ms=ttft_ms,
                            model=use_model,
                            session=session_id,
                            turn=turn,
                            prep_ms=prep_ms,
                            is_first_turn=turn <= 1,
                        )
                    full_text_parts.append(delta)
                    if spoken_delta:
                        yield {"delta": spoken_delta, "language_context": language_context}
            elif event_type == "response.completed":
                resp = getattr(event, "response", None)
                if resp is not None:
                    request_id = getattr(resp, "id", None)
                    stream_usage = normalize_usage(getattr(resp, "usage", None))
                break
            elif event_type == "error":
                err_msg = getattr(event, "error", None) or str(event)
                raise AppError(ErrorCode.PROVIDER_ERROR, provider="openai", cause=Exception(err_msg))

        raw_text = "".join(full_text_parts).strip()
        memory_update = {"operations": []}
        memory_parse_failed = False
        if extractor is not None:
            full_text = extractor.spoken_text.strip() or "క్షమించండి, నాకు అర్థం కాలేదు."
            memory_update = extractor.parse_memory_update()
            memory_parse_failed = extractor.structured_parse_failed()
        else:
            full_text = raw_text or "క్షమించండి, నాకు అర్థం కాలేదు."
        conversation_manager.add_turn(session_id, transcript, full_text)
        _after_turn_memory(session_id, call_id=call_id)
        total_ms = round((time.perf_counter() - t_stream) * 1000)
        _log_token_usage(
            stream_usage,
            session_id=session_id,
            turn=turn,
            model=use_model,
            request_id=request_id,
            brain_est=brain_est,
            budget=budget,
            history_est=history_est,
            transcript_est=transcript_est,
            summary_est=summary_est,
            cache_key=cache_key,
            ttft_ms=ttft_ms,
            total_ms=total_ms,
            prep_ms=prep_ms,
        )
        log_perf(
            "BRAIN_COMPLETED",
            ms=total_ms,
            chars=len(full_text),
            model=use_model,
            session=session_id,
            turn=turn,
            prep_ms=prep_ms,
            ttft_ms=ttft_ms,
            input_tokens=stream_usage.get("input_tokens"),
            output_tokens=stream_usage.get("output_tokens"),
            cached_tokens=stream_usage.get("cached_tokens"),
            cache_write_tokens=stream_usage.get("cache_write_tokens"),
        )
        yield {
            "done": True,
            "text": full_text,
            "language_context": language_context,
            "usage": stream_usage,
            "memory_update": memory_update,
            "memory_parse_failed": memory_parse_failed,
        }
        log_brain("Stream completed", chars=len(full_text), usage=stream_usage)
    except AppError:
        raise
    except Exception as e:
        log_error("Brain stream unexpected", err=str(e)[:500])
        raise AppError(ErrorCode.PROVIDER_ERROR, provider="openai", cause=e) from e
