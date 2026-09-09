"""Live-turn orchestrator — hot-path sequencing; memory merge never blocks first audio."""
from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from server.call.caller_detail_capture import caller_detail_memory_operations
from server.call import call_context, memory_projection as memory_projection_mod
from server.call.call_ledger import call_ledger
from server.call.end_call_validate import validate_end_call
from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA
from server.call.memory_manager import memory_manager
from server.call.rolling_summary import maybe_refresh_rolling_summary
from server.call.turn_coordinator import drain, lock_for
from server.config.env import get_settings
from server.services.openai_brain_service import generate_response, generate_response_stream
from server.services.voice_pipeline_limits import LiveReplyStreamCap, clamp_live_spoken_reply
from server.utils.logger import log_perf, logger

_LLM_KEYS = {
    "transcript",
    "language_code",
    "session_id",
    "call_id",
    "user_instructions",
    "business_instructions",
    "response_style",
    "brain_prompt",
    "openai_model",
    "temperature",
    "reasoning_effort",
    "max_output_tokens",
    "memory_projection",
    "rolling_summary",
    "structured_live_turn",
    "input_messages",
}

_ONE_SENTENCE_REACTIVE = re.compile(
    r"\b(frustrated|frustrating|annoying|explained this (?:twice|already)|"
    r"you(?:'re| are) repeating|stop repeating|recorded message|"
    r"make up|invent (?:a |the )?|hidden prompt|instructions you were given|"
    r"what(?:'s| is) the weather|weather outside)\b",
    re.I,
)
_SENTENCE_END = re.compile(r"[.!?।](?=\s|$)")
_DIRECT_FACT_ONLY = re.compile(
    r"^\s*(?:(?:quickly|just|త్వరగా)[, ]*)?"
    r"(?:what(?:'s| is) the (?:price|cost)|how much does it cost|"
    r"(?:price|fees?)\s*(?:ఎంత|enti)?|fees?\s+ఎంత|"
    r"what time do you close|is parking included|parking\s*(?:ఉందా|unda))"
    r"[?.!\s]*$",
    re.I,
)
_SEND_REQUEST = re.compile(
    r"(?:\b(?:email|whatsapp)\b.{0,40}\b(?:send|pamp|పంప|చేయండి|chey)\w*|"
    r"\b(?:send|pamp|పంప|చేయండి|chey)\w*.{0,40}\b(?:email|whatsapp)\b)",
    re.I,
)


def _should_cap_response(user_text: str) -> bool:
    text = user_text or ""
    return bool(
        _ONE_SENTENCE_REACTIVE.search(text)
        or _DIRECT_FACT_ONLY.fullmatch(text)
        or _SEND_REQUEST.search(text)
    )


def cap_reactive_response(user_text: str, assistant_text: str) -> str:
    """Keep frustration/repetition recovery to its first spoken sentence."""
    text = (assistant_text or "").strip()
    if not text or not _should_cap_response(user_text):
        return text
    match = _SENTENCE_END.search(text)
    return text[: match.end()].strip() if match else text


def finalize_live_spoken_text(user_text: str, assistant_text: str) -> str:
    """Apply reactive one-sentence cap, collapse repeats, soft length safety, spoken prep."""
    from server.services.spoken_numbers import prepare_spoken_reply
    from server.services.voice_pipeline_limits import (
        collapse_repeated_spoken_reply,
        is_incomplete_spoken_crumb,
    )

    collapsed = collapse_repeated_spoken_reply(cap_reactive_response(user_text, assistant_text))
    capped = clamp_live_spoken_reply(collapsed)
    prepared = prepare_spoken_reply(capped)
    if is_incomplete_spoken_crumb(prepared) or is_incomplete_spoken_crumb(capped):
        return ""
    return prepared


def correction_memory_operation(user_text: str) -> dict[str, str] | None:
    """Persist explicit caller corrections under one latest-wins canonical key."""
    text = " ".join((user_text or "").split()).strip()
    if not text:
        return None
    correction = bool(
        re.search(
            r"\b(?:no,?\s+i said|actually\b|move (?:it|that) to|change (?:it|that) to|"
            r"correction\b|i meant\b|not .{1,40},?\s*(?:it(?:'s| is)|my|the))\b|"
            r"(?:లేదు|కాదు).{0,40}(?:పేరు|అన్నాను|చెప్పాను)",
            text,
            re.I,
        )
    )
    if not correction:
        return None
    return {"op": "set_fact", "key": "latest_caller_correction", "value": text[:200]}


class LiveTurnOrchestrator:
    def _gate_end_call(
        self,
        raw: Any,
        *,
        transcript: str,
        language_code: str,
        call_id: str | None,
        spoken_text: str = "",
    ) -> dict[str, Any]:
        ctx = call_context.get(call_id) if call_id else None
        completed = 0
        snapshot = None
        if call_id:
            from server.agent.conversation_manager import conversation_manager
            from server.call.memory_manager import memory_manager

            completed = conversation_manager.get_completed_turns(ctx.session_id if ctx else "")
            try:
                snapshot = memory_manager.get_snapshot(call_id)
            except Exception:
                snapshot = None
        decision = validate_end_call(
            raw,
            user_text=transcript,
            language=language_code,
            call_status=ctx.status if ctx else "active",
            already_armed=bool(ctx and ctx.agent_hangup_armed),
            barge_in_flight=bool(ctx and ctx.barge_in_flight),
            last_stt_partial_at=ctx.last_stt_partial_at if ctx else None,
            completed_turns=completed,
            memory_snapshot=snapshot,
            call_end_policy=ctx.call_end_policy if ctx else None,
            spoken_text=spoken_text,
        )
        if not decision.accepted:
            return {"should_end": False, "reason": "none", "farewell": ""}
        if ctx:
            ctx.agent_hangup_armed = True
        farewell = decision.farewell or spoken_text
        return {"should_end": True, "reason": decision.reason, "farewell": farewell}

    async def _memory_blocks(self, call_id: str | None) -> tuple[str | None, str | None]:
        settings = get_settings()
        if not call_id or not settings.working_memory_enabled:
            return None, None
        snap = memory_manager.get_snapshot(call_id)
        rolling = (snap.get("summary") or "").strip() or None
        projection = memory_projection_mod.build(snap, include_summary=not rolling) or ""
        return projection, rolling or ""

    def _maybe_build_live_input(
        self,
        *,
        ctx,
        transcript: str,
        session_id: str,
        openai_model: str | None,
        projection: str | None,
        rolling: str | None,
    ) -> list[dict] | None:
        if ctx is None or not ctx.compiled_brain_text:
            return None
        from server.agent.brain_prompt_composer import estimate_tokens
        from server.agent.conversation_manager import conversation_manager
        from server.agent.instruction_builder import build_live_input
        from server.services.prompt_cache_key import caching_enabled

        settings = get_settings()
        history = conversation_manager.get_context_for_brain(
            session_id,
            max_turns=settings.brain_context_turns,
        )
        model = openai_model or ctx.resolved_stack.llm.model
        enable_cache = caching_enabled(model, estimate_tokens(ctx.compiled_brain_text))
        return build_live_input(
            compiled_brain_text=ctx.compiled_brain_text,
            history=history,
            transcript=transcript,
            enable_cache=enable_cache,
            rolling_summary=rolling or None,
            memory_projection=projection or None,
        )

    async def handle_user_turn_stream(
        self,
        *,
        transcript: str,
        language_code: str = "te-IN",
        session_id: str = "default",
        call_id: str | None = None,
        user_instructions: str | None = None,
        business_instructions: str | None = None,
        response_style: str | None = None,
        brain_prompt: str | None = None,
        openai_model: str | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
        stt_latency_ms: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        settings = get_settings()
        ctx = call_context.get(call_id) if call_id else None
        if ctx:
            ctx.heartbeat()
            ctx.barge_in_flight = False
            openai_model = openai_model or ctx.resolved_stack.llm.model

        turn_lock = lock_for(call_id) if call_id else None
        if turn_lock:
            await turn_lock.acquire()

        user_seq = 0
        ledger_task: asyncio.Task | None = None
        try:
            if call_id and settings.enable_call_archive:
                ledger_task = asyncio.create_task(
                    self._safe_append_user(call_id, transcript, stt_latency_ms)
                )

            from server.realtime.manager import realtime_text_manager

            realtime = bool(call_id and realtime_text_manager.get(call_id))
            projection, rolling = await self._memory_blocks(call_id) if call_id else (None, None)
            if realtime:
                structured = False
                input_messages = None
            else:
                structured = bool(call_id) and settings.working_memory_enabled
                input_messages = self._maybe_build_live_input(
                    ctx=ctx,
                    transcript=transcript,
                    session_id=session_id,
                    openai_model=openai_model,
                    projection=projection,
                    rolling=rolling,
                )

            t0 = time.perf_counter()
            brain_latency_ms: int | None = None
            assistant_text = ""
            raw_assistant_text = ""
            reactive_raw = ""
            reactive_emitted = ""
            cap_reactive = _should_cap_response(transcript)
            stream_cap = LiveReplyStreamCap()
            memory_update: dict[str, Any] = {"operations": []}
            memory_parse_failed = False
            stream_usage: dict[str, Any] = {}
            turn_cancelled_empty = False
            async for chunk in self._stream_llm(
                transcript=transcript,
                language_code=language_code,
                session_id=session_id,
                call_id=call_id,
                user_instructions=user_instructions,
                business_instructions=business_instructions,
                response_style=response_style,
                brain_prompt=brain_prompt,
                openai_model=openai_model,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                max_output_tokens=max_output_tokens,
                memory_projection=projection,
                rolling_summary=rolling,
                structured_live_turn=structured,
                input_messages=input_messages,
                ctx=ctx,
            ):
                if chunk.get("delta") and brain_latency_ms is None:
                    brain_latency_ms = int((time.perf_counter() - t0) * 1000)
                if chunk.get("done"):
                    raw_assistant_text = chunk.get("text") or ""
                    assistant_text = finalize_live_spoken_text(transcript, raw_assistant_text)
                    memory_update = chunk.get("memory_update") or {"operations": []}
                    memory_parse_failed = bool(chunk.get("memory_parse_failed"))
                    if realtime and assistant_text.strip() and not (memory_update.get("operations")):
                        memory_parse_failed = True
                    stream_usage = chunk.get("usage") or {}
                    if chunk.get("cancelled") and not assistant_text.strip():
                        turn_cancelled_empty = True
                    gated = dict(chunk)
                    gated["end_call"] = self._gate_end_call(
                        chunk.get("end_call"),
                        transcript=transcript,
                        language_code=language_code,
                        call_id=call_id,
                        spoken_text=assistant_text,
                    )
                    if gated["end_call"].get("should_end") and not assistant_text.strip():
                        assistant_text = str(gated["end_call"].get("farewell") or "").strip()
                    gated["text"] = assistant_text
                    yield gated
                    continue
                delta = str(chunk.get("delta") or "")
                if not delta:
                    yield chunk
                    continue
                if cap_reactive:
                    reactive_raw += delta
                    visible = cap_reactive_response(transcript, reactive_raw)
                    new_delta = visible[len(reactive_emitted) :]
                    reactive_emitted = visible
                    emit = stream_cap.feed(new_delta)
                else:
                    emit = stream_cap.feed(delta)
                if emit:
                    guarded = dict(chunk)
                    guarded["delta"] = emit
                    yield guarded

            if ledger_task is not None:
                user_line = await ledger_task
                user_seq = int(user_line.get("seq") or 0)

            if turn_cancelled_empty:
                # Barge cancelled mid-generation with nothing spoken — keep user utterance,
                # skip empty assistant archive (was showing silence / blank replies).
                if transcript.strip():
                    from server.agent.conversation_manager import conversation_manager

                    conversation_manager.add_user_only(session_id, transcript)
            elif assistant_text.strip():
                from server.agent.conversation_manager import conversation_manager

                conversation_manager.add_turn(session_id, transcript, assistant_text)
            elif transcript.strip():
                from server.agent.conversation_manager import conversation_manager

                conversation_manager.add_user_only(session_id, transcript)

            if call_id and settings.enable_call_archive and not turn_cancelled_empty:
                # Voice path is free; archive/memory merge must not block next turn TTFA.
                asyncio.create_task(
                    self._after_assistant(
                        call_id,
                        assistant_text,
                        brain_latency_ms,
                        stt_latency_ms,
                        memory_update=memory_update,
                        turn_seq=user_seq,
                        user_text=transcript,
                        merge_started_at=time.perf_counter(),
                        projection=projection,
                        rolling=rolling,
                        memory_parse_failed=memory_parse_failed,
                        usage=stream_usage,
                        skip_live_memory=False,
                    )
                )
        finally:
            if turn_lock and turn_lock.locked():
                turn_lock.release()

    async def handle_user_turn(self, **kwargs: Any) -> dict[str, Any]:
        settings = get_settings()
        call_id = kwargs.get("call_id")
        transcript = kwargs["transcript"]
        stt_latency_ms = kwargs.get("stt_latency_ms")
        session_id = kwargs.get("session_id") or "default"
        ctx = call_context.get(call_id) if call_id else None
        if ctx:
            ctx.heartbeat()
            ctx.barge_in_flight = False
            kwargs["openai_model"] = kwargs.get("openai_model") or ctx.resolved_stack.llm.model

        turn_lock = lock_for(call_id) if call_id else None
        if turn_lock:
            await turn_lock.acquire()

        try:
            user_seq = 0
            ledger_task: asyncio.Task | None = None
            if call_id and settings.enable_call_archive:
                ledger_task = asyncio.create_task(
                    self._safe_append_user(call_id, transcript, stt_latency_ms)
                )

            from server.realtime.manager import realtime_text_manager

            realtime = bool(call_id and realtime_text_manager.get(call_id))
            projection, rolling = await self._memory_blocks(call_id) if call_id else (None, None)
            if realtime:
                kwargs["memory_projection"] = projection
                kwargs["rolling_summary"] = rolling
                kwargs["structured_live_turn"] = False
                kwargs["input_messages"] = None
            else:
                kwargs["memory_projection"] = projection
                kwargs["rolling_summary"] = rolling
                kwargs["structured_live_turn"] = bool(call_id) and settings.working_memory_enabled
                kwargs["input_messages"] = self._maybe_build_live_input(
                    ctx=ctx,
                    transcript=transcript,
                    session_id=session_id,
                    openai_model=kwargs.get("openai_model"),
                    projection=projection,
                    rolling=rolling,
                )
            t0 = time.perf_counter()
            if realtime:
                result = {"text": "", "end_call": {}, "memory_update": {"operations": []}, "usage": {}}
                async for chunk in realtime_text_manager.get(call_id).run_turn(  # type: ignore[union-attr]
                    transcript,
                    language=str(kwargs.get("language_code") or "te-IN"),
                ):
                    if chunk.get("done"):
                        result = chunk
            else:
                llm_kwargs = {k: v for k, v in kwargs.items() if k in _LLM_KEYS}
                from server.realtime.models import http_openai_model, is_realtime_llm_model

                model = str(llm_kwargs.get("openai_model") or "")
                if is_realtime_llm_model(model):
                    llm_kwargs["openai_model"] = http_openai_model(settings)
                result = await generate_response(**llm_kwargs)
            raw_text = result.get("text") or ""
            result["text"] = finalize_live_spoken_text(transcript, raw_text)
            if result["text"].strip():
                from server.agent.conversation_manager import conversation_manager

                conversation_manager.add_turn(session_id, transcript, result["text"])
            elif transcript.strip():
                from server.agent.conversation_manager import conversation_manager

                conversation_manager.add_user_only(session_id, transcript)
            result["end_call"] = self._gate_end_call(
                result.get("end_call"),
                transcript=transcript,
                language_code=str(kwargs.get("language_code") or "te-IN"),
                call_id=call_id,
                spoken_text=result.get("text") or "",
            )
            if result["end_call"].get("should_end") and not (result.get("text") or "").strip():
                result["text"] = str(result["end_call"].get("farewell") or "").strip()
            brain_latency_ms = int((time.perf_counter() - t0) * 1000)
            if ledger_task is not None:
                user_line = await ledger_task
                user_seq = int(user_line.get("seq") or 0)
            if call_id and settings.enable_call_archive:
                await self._after_assistant(
                    call_id,
                    result.get("text") or "",
                    brain_latency_ms,
                    stt_latency_ms,
                    memory_update=result.get("memory_update") or {"operations": []},
                    turn_seq=user_seq,
                    user_text=transcript,
                    merge_started_at=time.perf_counter(),
                    projection=projection,
                    rolling=rolling,
                    memory_parse_failed=bool(result.get("memory_parse_failed")),
                    skip_live_memory=False,
                )
            return result
        finally:
            if turn_lock and turn_lock.locked():
                turn_lock.release()

    async def _stream_llm(self, *, ctx, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        settings = get_settings()
        from server.realtime.manager import realtime_text_manager
        from server.realtime.models import http_openai_model, is_realtime_llm_model

        call_id = kwargs.get("call_id")
        session = realtime_text_manager.get(call_id) if call_id else None
        if session is not None:
            async for chunk in session.run_turn(
                str(kwargs.get("transcript") or ""),
                language=str(kwargs.get("language_code") or "te-IN"),
            ):
                yield chunk
            return

        adapter = None
        registry = None
        provider_id = ctx.resolved_stack.llm.provider if ctx else None
        if settings.use_provider_registry and ctx is not None:
            try:
                from server.providers import get_provider_registry

                registry = get_provider_registry()
                adapter = registry.get_llm(provider_id)
            except Exception:
                adapter = None
        stream_kwargs = {k: v for k, v in kwargs.items() if k != "ctx"}
        if ctx and ctx.resolved_stack:
            llm_sel = ctx.resolved_stack.llm
            stream_kwargs.setdefault("model", llm_sel.model)
            stream_kwargs.setdefault("openai_model", llm_sel.model)
        http_model = str(stream_kwargs.get("openai_model") or stream_kwargs.get("model") or "")
        if is_realtime_llm_model(http_model):
            fallback_model = http_openai_model(settings)
            stream_kwargs["openai_model"] = fallback_model
            stream_kwargs["model"] = fallback_model
        input_messages = stream_kwargs.pop("input_messages", None)
        schema = LIVE_TURN_JSON_SCHEMA if stream_kwargs.get("structured_live_turn") else None

        async def _run_with(adapter_inst) -> AsyncIterator[dict[str, Any]]:
            self._align_stream_model(stream_kwargs, adapter_inst, registry)
            model = str(stream_kwargs.get("model") or stream_kwargs.get("openai_model") or "")
            if is_realtime_llm_model(model):
                model = http_openai_model(settings)
                stream_kwargs["model"] = model
                stream_kwargs["openai_model"] = model
            msgs = self._messages_for_model(input_messages, model)
            stream_fn = adapter_inst.stream_structured_turn if schema else adapter_inst.stream_live_turn
            async for chunk in stream_fn(
                input_messages=msgs,
                schema=schema,
                **stream_kwargs,
            ):
                yield chunk

        if adapter is not None:
            try:
                async for chunk in _run_with(adapter):
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"[LLM] primary provider failed {provider_id}: {str(e)[:160]}")
                fallback = self._fallback_llm_adapter(ctx, registry, provider_id)
                if fallback is None:
                    raise
                async for chunk in _run_with(fallback):
                    yield chunk
                return

        if input_messages is not None:
            model = str(stream_kwargs.get("openai_model") or stream_kwargs.get("model") or "")
            stream_kwargs["input_messages"] = self._messages_for_model(input_messages, model)
        http_model = str(stream_kwargs.get("openai_model") or stream_kwargs.get("model") or "")
        if is_realtime_llm_model(http_model):
            fallback = http_openai_model(settings)
            stream_kwargs["openai_model"] = fallback
            stream_kwargs["model"] = fallback
        direct_kwargs = {k: v for k, v in stream_kwargs.items() if k != "model"}
        async for chunk in generate_response_stream(**direct_kwargs):
            yield chunk

    def _messages_for_model(self, messages: list[dict] | None, model: str) -> list[dict] | None:
        from server.services.prompt_cache_key import supports_explicit_prompt_cache

        if not messages or supports_explicit_prompt_cache(model):
            return messages
        return _strip_prompt_cache_breakpoints(messages)

    def _align_stream_model(self, stream_kwargs: dict[str, Any], adapter_inst, registry) -> None:
        """Never send a Gemini model id to OpenAI (or the reverse) after a provider swap."""
        pid = getattr(adapter_inst, "provider_id", None)
        if not pid:
            return
        current = str(stream_kwargs.get("model") or stream_kwargs.get("openai_model") or "")
        allowed = False
        if registry is not None:
            try:
                allowed = registry.is_model_allowed(pid, "llm", current)
            except Exception:
                allowed = False
        if allowed:
            return
        model = self._provider_default_llm_model(registry, pid)
        if not model:
            return
        stream_kwargs["model"] = model
        stream_kwargs["openai_model"] = model

    def _provider_default_llm_model(self, registry, provider_id: str) -> str | None:
        settings = get_settings()
        if provider_id == "openai":
            preferred = (settings.openai_model or "").strip()
            if preferred and (registry is None or registry.is_model_allowed("openai", "llm", preferred)):
                return preferred
        if registry is not None:
            for p in registry.get_catalog().get("providers") or []:
                if p.get("id") != provider_id:
                    continue
                models = (p.get("models") or {}).get("llm") or []
                marked = next((m for m in models if m.get("default")), None)
                row = marked or (models[0] if models else None)
                if row and row.get("id"):
                    return str(row["id"])
        if provider_id == "openai":
            return settings.openai_model
        if provider_id == "deepseek":
            return settings.deepseek_model
        return None

    def _fallback_llm_adapter(self, ctx, registry, failed_provider: str | None):
        if ctx is None or registry is None:
            return None
        from server.services.dev_fallback_store import dev_fallback_store

        chain = dev_fallback_store.get_chains().get("llm") or []
        for pid in chain:
            if pid == failed_provider:
                continue
            try:
                return registry.get_llm(pid)
            except Exception:
                continue
        return None

    async def _safe_append_user(
        self, call_id: str, transcript: str, stt_latency_ms: int | None
    ) -> dict[str, Any]:
        try:
            return await call_ledger.append_user_turn(call_id, transcript, stt_latency_ms=stt_latency_ms)
        except RuntimeError as e:
            logger.warning(f"[LEDGER] user append dropped call={call_id}: {str(e)[:120]}")
            return {"seq": 0}

    async def _after_assistant(
        self,
        call_id: str,
        text: str,
        brain_latency_ms: int | None,
        stt_latency_ms: int | None = None,
        *,
        memory_update: dict[str, Any] | None = None,
        turn_seq: int = 0,
        user_text: str = "",
        merge_started_at: float | None = None,
        projection: str | None = None,
        rolling: str | None = None,
        memory_parse_failed: bool = False,
        usage: dict[str, Any] | None = None,
        skip_live_memory: bool = False,
    ) -> None:
        try:
            line = await call_ledger.append_assistant_turn(
                call_id,
                text,
                brain_latency_ms=brain_latency_ms,
            )
        except RuntimeError as e:
            logger.warning(f"[LEDGER] assistant append dropped call={call_id}: {str(e)[:120]}")
            return
        ops = list((memory_update or {}).get("operations") or [])
        correction_op = correction_memory_operation(user_text)
        if correction_op and not skip_live_memory:
            ops.append(correction_op)
        if not skip_live_memory:
            for detail_op in caller_detail_memory_operations(user_text):
                ops.append(detail_op)
        applied = 0
        merge_ms: int | None = None
        settings = get_settings()
        seq = turn_seq or int(line.get("seq") or 0)
        if settings.working_memory_enabled and not skip_live_memory:
            try:
                if projection is not None:
                    memory_manager.record_projection(
                        call_id,
                        seq,
                        projection,
                        include_summary=not bool(rolling),
                    )
                result = memory_manager.apply_proposals(
                    call_id,
                    ops,
                    turn_seq=seq,
                    source="model",
                )
                applied = len(result["event"].get("operations") or [])
                if memory_parse_failed and settings.memory_extraction_fallback:
                    from server.call.memory_extraction import extract_and_apply

                    fallback = await extract_and_apply(
                        call_id,
                        turn_seq=seq,
                        user_text=user_text,
                        assistant_text=text,
                        snapshot=result["snapshot"],
                    )
                    if fallback:
                        applied = len(fallback["event"].get("operations") or [])
                await maybe_refresh_rolling_summary(call_id, seq)
            except Exception as e:
                logger.warning(f"[MEMORY] merge failed call={call_id}: {str(e)[:160]}")
            if merge_started_at is not None:
                merge_ms = int((time.perf_counter() - merge_started_at) * 1000)
        turn = {
            "turn": line["seq"],
            "stt_final_ms": stt_latency_ms,
            "llm_ttft_ms": brain_latency_ms,
            "tts_first_audio_ms": None,
            "e2e_ms": brain_latency_ms,
            "memory_ops_applied": applied,
            "memory_merge_ms": merge_ms,
            "errors": [],
            "input_tokens": int((usage or {}).get("input_tokens") or 0),
            "output_tokens": int((usage or {}).get("output_tokens") or 0),
            "cached_tokens": int((usage or {}).get("cached_tokens") or 0),
            "cache_write_tokens": int((usage or {}).get("cache_write_tokens") or 0),
            "memory_ops_proposed": len(ops),
        }
        await call_ledger.append_trace_turn(call_id, turn)
        ctx = call_context.get(call_id)
        if ctx:
            ctx.turns.append(turn)
            ctx.heartbeat()
        log_perf("LEDGER_ASSISTANT", call=call_id, seq=line["seq"], ms=brain_latency_ms, memory_ops=applied)


live_turn_orchestrator = LiveTurnOrchestrator()


def _strip_prompt_cache_breakpoints(messages: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for msg in messages:
        cloned = dict(msg)
        content = cloned.get("content")
        if isinstance(content, list):
            cloned["content"] = [
                {k: v for k, v in block.items() if k != "prompt_cache_breakpoint"}
                if isinstance(block, dict)
                else block
                for block in content
            ]
        cleaned.append(cloned)
    return cleaned
