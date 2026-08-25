"""Live-turn orchestrator — hot-path sequencing; memory merge never blocks first audio."""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from server.call import call_context, memory_projection as memory_projection_mod
from server.call.call_ledger import call_ledger
from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA
from server.call.memory_manager import memory_manager
from server.call.rolling_summary import maybe_refresh_rolling_summary
from server.call.turn_coordinator import drain, lock_for
from server.config.env import get_settings
from server.services.openai_brain_service import generate_response, generate_response_stream
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


class LiveTurnOrchestrator:
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
            openai_model = openai_model or ctx.resolved_stack.llm.model

        turn_lock = lock_for(call_id) if call_id else None
        if turn_lock:
            await turn_lock.acquire()

        user_seq = 0
        try:
            if call_id and settings.enable_call_archive:
                user_line = await self._safe_append_user(call_id, transcript, stt_latency_ms)
                user_seq = int(user_line.get("seq") or 0)

            projection, rolling = await self._memory_blocks(call_id)
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
            memory_update: dict[str, Any] = {"operations": []}
            memory_parse_failed = False
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
                    assistant_text = chunk.get("text") or ""
                    memory_update = chunk.get("memory_update") or {"operations": []}
                    memory_parse_failed = bool(chunk.get("memory_parse_failed"))
                yield chunk

            if call_id and settings.enable_call_archive:
                await self._after_assistant(
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
            kwargs["openai_model"] = kwargs.get("openai_model") or ctx.resolved_stack.llm.model

        turn_lock = lock_for(call_id) if call_id else None
        if turn_lock:
            await turn_lock.acquire()

        try:
            user_seq = 0
            if call_id and settings.enable_call_archive:
                user_line = await self._safe_append_user(call_id, transcript, stt_latency_ms)
                user_seq = int(user_line.get("seq") or 0)

            projection, rolling = await self._memory_blocks(call_id)
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
            llm_kwargs = {k: v for k, v in kwargs.items() if k in _LLM_KEYS}
            result = await generate_response(**llm_kwargs)
            brain_latency_ms = int((time.perf_counter() - t0) * 1000)
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
                )
            return result
        finally:
            if turn_lock and turn_lock.locked():
                turn_lock.release()

    async def _stream_llm(self, *, ctx, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        settings = get_settings()
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
        input_messages = stream_kwargs.pop("input_messages", None)
        schema = LIVE_TURN_JSON_SCHEMA if stream_kwargs.get("structured_live_turn") else None

        async def _run_with(adapter_inst) -> AsyncIterator[dict[str, Any]]:
            stream_fn = adapter_inst.stream_structured_turn if schema else adapter_inst.stream_live_turn
            async for chunk in stream_fn(
                input_messages=input_messages,
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
            stream_kwargs["input_messages"] = input_messages
        async for chunk in generate_response_stream(**stream_kwargs):
            yield chunk

    def _fallback_llm_adapter(self, ctx, registry, failed_provider: str | None):
        if ctx is None:
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
        ops = (memory_update or {}).get("operations") or []
        applied = 0
        merge_ms: int | None = None
        settings = get_settings()
        seq = turn_seq or int(line.get("seq") or 0)
        if settings.working_memory_enabled:
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
        }
        await call_ledger.append_trace_turn(call_id, turn)
        ctx = call_context.get(call_id)
        if ctx:
            ctx.turns.append(turn)
            ctx.heartbeat()
        log_perf("LEDGER_ASSISTANT", call=call_id, seq=line["seq"], ms=brain_latency_ms, memory_ops=applied)


live_turn_orchestrator = LiveTurnOrchestrator()
