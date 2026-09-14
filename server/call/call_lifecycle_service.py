"""Call start/end/finalize — sole lifecycle owner."""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from server.brain.agent_service import agent_service
from server.call import call_context
from server.call.audio_archive import audio_archive
from server.call.call_context import CallContext
from server.call.call_ledger import call_ledger
from server.call.call_store import call_store
from server.call.paths import relative_storage_path
from server.call.post_call_pipeline import enqueue as enqueue_post_call
from server.config.env import get_settings
from server.providers.base import ResolvedStack, StackSelection, StageSelection
from server.providers.resolver import resolve_stack
from server.providers.session_stack import resolve_stack_for_session
from server.realtime.manager import realtime_text_manager
from server.realtime.models import coerce_live_llm_selection, pipeline_mode
from server.realtime.text_session import build_session_instructions
from server.services.dev_runtime import effective_app_environment, effective_config_mode, effective_voice_tier
from server.utils.errors import AppError, ErrorCode
from server.utils.logger import log_pstn, logger

END_REASONS = {
    "user_stop",
    "timeout",
    "error",
    "transfer",
    "browser_unload",
    "pstn_hangup",
    "agent_hangup",
    "goodbye",
    "firm_refusal",
    "goal_complete",
    "abuse",
    "out_of_scope",
    "superseded",
    "stale_recovery",
    "ws_disconnect",
}

END_REASON_ALIASES = {
    "user_hangup": "user_stop",
    "idle_timeout": "timeout",
    "hangup": "user_stop",
    "normal_clearing": "pstn_hangup",
}


def _normalize_end_reason(reason: str) -> str:
    mapped = END_REASON_ALIASES.get(reason, reason)
    return mapped if mapped in END_REASONS else "user_stop"

_idle_tasks: dict[str, asyncio.Task] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def status_url(call_id: str) -> str:
    return f"/api/call/{call_id}/finalization"


class CallLifecycleService:
    async def start(
        self,
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
        channel: str = "browser",
        direction: str = "inbound",
        campaign_id: str | None = None,
        environment: str | None = None,
        tier: str | None = None,
        stack_override: dict[str, Any] | None = None,
        config_session_id: str | None = None,
        caller_id: str | None = None,
        language: str = "te-IN",
        realtime_prewarm_key: str | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        session_id = session_id or "default"
        channel = channel if channel in ("browser", "pstn") else "browser"
        direction = direction if direction in ("inbound", "outbound") else "inbound"
        lookup_session = (config_session_id or session_id).strip() or session_id
        from server.services.test_studio_config import merge_stack, saved_call_config

        saved = saved_call_config(lookup_session)
        stack_override = merge_stack(saved.get("stack_override"), stack_override)
        if channel != "pstn" and isinstance(stack_override, dict):
            pipeline_slug = str(stack_override.get("pipeline") or "").strip().lower()
            flow_slug = str(stack_override.get("voice_flow") or "").strip().lower()
            if pipeline_slug in ("realtime_voice", "realtime_e2e") or flow_slug in (
                "realtime_e2e",
                "realtime_voice",
            ):
                stack_override = dict(stack_override)
                stack_override["pipeline"] = "realtime_text"
                stack_override.pop("voice_flow", None)
                stack_override.pop("realtime_voice", None)
        tier = tier or saved.get("tier")

        agent = await self._resolve_agent(agent_id)
        env = environment or agent.get("environment") or effective_app_environment()
        effective_tier = tier or agent.get("default_tier") or effective_voice_tier()

        previous = call_context.get_active_for_session(session_id)
        if previous:
            if settings.call_auto_end_on_start:
                await self.end(previous.call_id, reason="superseded")
            else:
                raise AppError(
                    ErrorCode.CONFLICT,
                    message="An active call already exists for this session",
                    status_code=409,
                )

        stack = self._coerce_pipeline_stack(
            self._resolve_locked_stack(
                session_id=lookup_session,
                tier=effective_tier,  # type: ignore[arg-type]
                environment=env,
                stack_override=stack_override,
                language=language or (agent.get("languages") or ["te-IN"])[0],
            ),
            stack_override=stack_override,
        )
        pipeline = pipeline_mode(settings=settings, stack_override=stack_override)
        compiled_version, compiled_text = await self._lock_compiled_brain(
            agent["agent_id"],
            session_id=lookup_session,
        )
        if config_session_id and lookup_session != session_id and not compiled_text:
            logger.warning(
                "[CALL] config session %s has no saved script; using agent published brain",
                lookup_session,
            )

        call_id = str(uuid.uuid4())
        started = _utcnow()
        storage_path = relative_storage_path(call_id)
        meta = {
            "call_id": call_id,
            "tenant_id": agent["tenant_id"],
            "agent_id": agent["agent_id"],
            "session_id": session_id,
            "channel": channel,
            "direction": direction,
            "campaign_id": campaign_id,
            "caller_id": caller_id,
            "tier": stack.tier,
            "combination_id": stack.combination_id,
            "compiled_brain_version": compiled_version,
            "started_at": started.isoformat(),
            "environment": env,
            "resolved_stack": stack.to_safe_dict(),
            "pipeline": pipeline,
        }
        await call_ledger.init(call_id, meta)
        audio_archive.init(call_id)
        from server.call.memory_manager import memory_manager

        memory_manager.init(call_id)
        from server.agent.conversation_manager import conversation_manager
        from server.agent.session_memory import session_memory

        # New call = new dialogue. Compiled brain stays on the config session.
        conversation_manager.clear(session_id)
        session_memory.clear(session_id)
        # lookup_session owns shared Test Studio configuration, not this call's
        # conversation. Clearing it here could erase another active browser call.
        if caller_id:
            memory_manager.apply_proposals(
                call_id,
                [{"op": "set_fact", "key": "phone", "value": str(caller_id)[:200]}],
                turn_seq=0,
                source="telephony",
            )

        record = {
            "call_id": call_id,
            "tenant_id": agent["tenant_id"],
            "agent_id": agent["agent_id"],
            "session_id": session_id,
            "channel": channel,
            "direction": direction,
            "campaign_id": campaign_id,
            "environment": env,
            "tier": stack.tier or effective_tier,
            "combination_id": stack.combination_id,
            "compiled_brain_version": compiled_version,
            "started_at": started,
            "finalization_status": "pending",
            "storage_path": storage_path,
            "last_heartbeat_at": started,
        }
        await call_store.insert(record)

        ctx = CallContext(
            call_id=call_id,
            tenant_id=agent["tenant_id"],
            agent_id=agent["agent_id"],
            session_id=session_id,
            channel=channel,
            direction=direction,
            environment=env,
            tier=stack.tier or effective_tier,
            resolved_stack=stack,
            compiled_brain_version=compiled_version,
            compiled_brain_text=compiled_text,
            started_at=started,
            storage_path=storage_path,
            call_end_policy=self._load_call_end_policy(lookup_session, language),
            pipeline=pipeline,
        )
        call_context.put(ctx)
        realtime_status: dict[str, Any] = {"status": "n/a"}
        if pipeline == "realtime_voice":
            realtime_status = {"status": "voice_loop"}
            try:
                from server.realtime.voice_manager import realtime_voice_manager

                adopted = (
                    realtime_voice_manager.adopt_session(realtime_prewarm_key, call_id)
                    if realtime_prewarm_key
                    else None
                )
                if adopted is not None:
                    log_pstn(
                        "prewarm.realtime_voice.adopted",
                        call_id=call_id,
                        from_key=realtime_prewarm_key,
                    )
                    realtime_status = {"status": "ready"}
            except Exception as e:
                logger.warning("[CALL] realtime voice adopt failed %s: %s", call_id, str(e)[:200])
        elif pipeline == "realtime_text":
            try:
                from server.realtime.manager import realtime_text_manager

                adopted = (
                    realtime_text_manager.adopt_session(realtime_prewarm_key, call_id)
                    if realtime_prewarm_key
                    else None
                )
                boot_ready = channel == "browser"
                if adopted is None:
                    await realtime_text_manager.create(
                        call_id,
                        compiled_brain=compiled_text,
                        model=stack.llm.model,
                        language=language or "te-IN",
                        caller_id=caller_id,
                        instructions=build_session_instructions(
                            compiled_text,
                            caller_id=caller_id,
                            language=language or "te-IN",
                        ),
                        wait_ready=boot_ready,
                    )
                    realtime_status = {"status": "ready" if boot_ready else "booting"}
                else:
                    log_pstn(
                        "prewarm.realtime.adopted",
                        call_id=call_id,
                        from_key=realtime_prewarm_key,
                    )
                    session = realtime_text_manager.get(call_id)
                    realtime_status = {
                        "status": "ready" if session and session.is_ready else "booting",
                    }
            except Exception as e:
                err = str(e)[:200]
                logger.warning("[CALL] realtime session failed %s: %s", call_id, err)
                realtime_status = {"status": "failed", "error": err}
        logger.info(f"[CALL] started {call_id} agent={agent['agent_id']} combo={stack.combination_id} pipeline={pipeline}")
        if channel == "pstn":
            log_pstn(
                "lifecycle.started",
                timer_key=call_id,
                call_id=call_id,
                agent_id=agent["agent_id"],
                combo=stack.combination_id,
                direction=direction,
                config_session=lookup_session if lookup_session != session_id else None,
                brain=compiled_version,
            )

        return {
            "call_id": call_id,
            "session_id": session_id,
            "compiled_brain_version": compiled_version,
            "locked_versions": {
                "combination_id": stack.combination_id,
                "compiled_brain_version": compiled_version,
                "channel": channel,
            },
            "resolved_stack": stack.to_safe_dict(),
            "pipeline": pipeline,
            "realtime": realtime_status,
            "ws_urls": {
                "stt": f"/ws/stt-realtime?call_id={call_id}&sessionId={session_id}",
                "tts": f"/ws/tts?call_id={call_id}&sessionId={session_id}",
            },
            "started_at": started.isoformat(),
        }

    async def end(self, call_id: str, *, reason: str = "user_stop") -> dict[str, Any]:
        reason = _normalize_end_reason(reason)
        ctx = call_context.get(call_id)
        stored = await call_store.get(call_id)
        if ctx is None and stored is None:
            raise AppError(ErrorCode.NOT_FOUND, message="Call not found", status_code=404)

        if ctx and ctx.status in ("finalizing", "complete", "failed"):
            return self._accepted_payload(call_id, ctx.status)
        if stored and stored.get("ended_at") and stored.get("finalization_status") in (
            "complete",
            "failed",
            "processing",
        ):
            return self._accepted_payload(call_id, stored.get("finalization_status") or "processing")

        if ctx:
            ctx.status = "finalizing"
            ctx.end_reason = reason
            call_context.drop_session_pointer(ctx.session_id, call_id)
        self._cancel_idle(call_id)

        from server.call.turn_coordinator import drain

        await drain(call_id)
        await realtime_text_manager.destroy(call_id)
        try:
            from server.realtime.voice_manager import realtime_voice_manager

            await realtime_voice_manager.destroy(call_id)
        except Exception:
            pass

        await call_ledger.seal(call_id)
        if ctx:
            ctx.components["ledger"] = "complete"

        ended = _utcnow()
        started = ctx.started_at if ctx else None
        duration = None
        if started:
            duration = max(0, int((ended - started).total_seconds()))
        elif stored and stored.get("started_at"):
            raw = stored["started_at"]
            st = datetime.fromisoformat(raw.replace("Z", "+00:00")) if isinstance(raw, str) else raw
            duration = max(0, int((ended - st).total_seconds()))

        try:
            call_ledger.stamp_ended_usage(call_id, reason=reason, duration_sec=duration)
        except Exception:
            pass

        await call_store.update(
            call_id,
            {
                "ended_at": ended,
                "duration_sec": duration,
                "finalization_status": "processing",
                "end_reason": reason,
            },
        )
        asyncio.create_task(self._finalize_async(call_id))
        logger.info(f"[CALL] end {call_id} reason={reason}")
        return self._accepted_payload(call_id, "processing")

    async def _finalize_async(self, call_id: str) -> None:
        ctx = call_context.get(call_id)
        try:
            from server.call.memory_manager import memory_manager
            from server.call.paths import call_dir

            snap_path = memory_manager.snapshot_path(call_id)
            wm_path = call_dir(call_id) / "working_memory.json"
            if snap_path.exists():
                wm_path.write_text(snap_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[CALL] working_memory export failed {call_id}: {str(e)[:160]}")
        try:
            audio_status = await audio_archive.flush(call_id)
            if ctx:
                ctx.components["audio"] = "complete" if audio_status.get("mix") == "complete" else "failed"
        except Exception as e:
            logger.warning(f"[CALL] audio flush failed {call_id}: {str(e)[:200]}")
            if ctx:
                ctx.components["audio"] = "failed"
        await enqueue_post_call(call_id)

    def _accepted_payload(self, call_id: str, status: str) -> dict[str, Any]:
        return {
            "call_id": call_id,
            "status": status,
            "status_url": status_url(call_id),
        }

    async def get_call(self, call_id: str) -> dict[str, Any]:
        stored = await call_store.get(call_id)
        ctx = call_context.get(call_id)
        if not stored and not ctx:
            raise AppError(ErrorCode.NOT_FOUND, message="Call not found", status_code=404)
        body = stored or ctx.to_public_dict()  # type: ignore[union-attr]
        fin = await self.finalization(call_id)
        body["finalization"] = fin
        if ctx:
            body["resolved_stack"] = ctx.resolved_stack.to_safe_dict()
            body["status"] = ctx.status
            body["pipeline"] = ctx.pipeline
        review = call_ledger.review_fields(call_id)
        if review.get("resolved_stack") and body.get("resolved_stack"):
            review = {k: v for k, v in review.items() if k != "resolved_stack"}
        body.update(review)
        body["audio"] = {
            "mix": audio_archive.file_for(call_id, "mix") is not None,
            "user": audio_archive.file_for(call_id, "user") is not None,
            "agent": audio_archive.file_for(call_id, "agent") is not None,
        }
        return body

    async def finalization(self, call_id: str) -> dict[str, Any]:
        ctx = call_context.get(call_id)
        stored = await call_store.get(call_id)
        if not ctx and not stored:
            raise AppError(ErrorCode.NOT_FOUND, message="Call not found", status_code=404)
        components = dict(ctx.components) if ctx else self._infer_components(stored)
        status = (ctx.status if ctx else None) or (stored or {}).get("finalization_status") or "pending"
        if status == "finalizing":
            status = "processing"
        return {
            "call_id": call_id,
            "status": status,
            "ledger": components.get("ledger", "pending"),
            "audio": components.get("audio", "pending"),
            "outcome": components.get("outcome", "pending"),
            "components": components,
            "ended_at": (stored or {}).get("ended_at"),
            "retry_available": components.get("outcome") == "failed",
        }

    def _infer_components(self, stored: dict[str, Any] | None) -> dict[str, str]:
        from server.call.post_call_pipeline import read_outcome

        ended = bool(stored and stored.get("ended_at"))
        ledger = "complete" if ended else "pending"
        call_id = (stored or {}).get("call_id")
        mix_ok = bool(call_id and audio_archive.file_for(str(call_id), "mix"))
        row_status = (stored or {}).get("finalization_status")
        if mix_ok:
            audio = "complete"
        elif ended:
            audio = "processing" if row_status == "processing" else "empty"
        else:
            audio = "pending"
        outcome_file = read_outcome(call_id) if call_id else None
        if outcome_file is not None:
            if outcome_file.get("generation_ok") is False:
                outcome = "failed"
            else:
                outcome = "complete"
        elif row_status == "processing":
            outcome = "processing"
        elif row_status == "complete":
            outcome = "skipped"
        else:
            outcome = "pending"
        return {"ledger": ledger, "audio": audio, "outcome": outcome}

    def note_ws_open(self, call_id: str) -> None:
        ctx = call_context.get(call_id)
        if not ctx:
            return
        ctx.ws_clients += 1
        ctx.heartbeat()
        self._cancel_idle(call_id)

    def note_ws_close(self, call_id: str) -> None:
        ctx = call_context.get(call_id)
        if not ctx:
            return
        ctx.ws_clients = max(0, ctx.ws_clients - 1)
        ctx.heartbeat()
        if ctx.ws_clients == 0 and ctx.status == "active":
            self._schedule_idle_end(call_id)

    def heartbeat(self, call_id: str) -> None:
        ctx = call_context.get(call_id)
        if ctx:
            ctx.heartbeat()

    def _schedule_idle_end(self, call_id: str) -> None:
        self._cancel_idle(call_id)
        timeout = get_settings().call_idle_timeout_sec

        async def _fire() -> None:
            await asyncio.sleep(timeout)
            ctx = call_context.get(call_id)
            if ctx and ctx.status == "active" and ctx.ws_clients == 0:
                await self.end(call_id, reason="timeout")

        try:
            _idle_tasks[call_id] = asyncio.create_task(_fire())
        except RuntimeError:
            pass

    def _cancel_idle(self, call_id: str) -> None:
        task = _idle_tasks.pop(call_id, None)
        if task:
            task.cancel()

    async def recover_stale_calls(self) -> int:
        """On process start RAM is empty, so every open call is dead and must finalize."""
        stale = await call_store.list_open()
        count = 0
        for rec in stale:
            try:
                await self.end(rec["call_id"], reason="stale_recovery")
                count += 1
            except Exception as e:
                logger.warning(f"[CALL] stale recovery failed {rec.get('call_id')}: {str(e)[:160]}")
                await call_store.update(
                    rec["call_id"],
                    {"finalization_status": "failed", "end_reason": "stale_recovery"},
                )
        if count:
            logger.info(f"[CALL] recovered {count} stale calls")
        return count

    async def _resolve_agent(self, agent_id: str | None) -> dict[str, Any]:
        if agent_id:
            try:
                return await agent_service.get_agent(agent_id)
            except KeyError:
                raise AppError(ErrorCode.NOT_FOUND, message="Agent not found", status_code=404) from None
        return await agent_service.ensure_default_agent()

    def _resolve_locked_stack(
        self,
        *,
        session_id: str,
        tier: str,
        environment: str,
        stack_override: dict[str, Any] | None,
        language: str,
    ) -> ResolvedStack:
        if effective_config_mode() == "frontend":
            base = resolve_stack_for_session(session_id, language=language)
            return resolve_stack(
                mode="frontend",
                tier=tier or base.tier,  # type: ignore[arg-type]
                user_selection=StackSelection(
                    stt=base.stt,
                    llm=base.llm,
                    tts=base.tts,
                    language=base.language,
                    voice_preset=base.voice_preset,
                ),
                language=language,
                environment=environment,
                stack_override=stack_override,
            )
        return resolve_stack(
            mode="env",
            tier=tier,  # type: ignore[arg-type]
            language=language,
            environment=environment,
            stack_override=stack_override,
        )

    def _coerce_pipeline_stack(
        self,
        stack: ResolvedStack,
        *,
        stack_override: dict[str, Any] | None = None,
    ) -> ResolvedStack:
        provider, model = coerce_live_llm_selection(
            stack.llm.provider,
            stack.llm.model,
            stack_override=stack_override,
        )
        if provider == stack.llm.provider and model == stack.llm.model:
            return stack
        llm = StageSelection(provider, model, dict(stack.llm.config))
        payload = {
            "stt": {"provider": stack.stt.provider, "model": stack.stt.model},
            "llm": {"provider": llm.provider, "model": llm.model},
            "tts": {"provider": stack.tts.provider, "model": stack.tts.model},
        }
        combination_id = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        return replace(stack, llm=llm, combination_id=combination_id)

    def _load_call_end_policy(self, session_id: str | None, language: str | None) -> dict | None:
        if not session_id:
            return None
        from server.agent.instruction_store import instruction_store
        from server.call.call_end_policy import default_call_end_policy, normalize_call_end_policy

        lang = language
        if not session_id:
            return default_call_end_policy(lang)
        raw = instruction_store.get_call_end_policy(session_id)
        lang = language or instruction_store.get_language(session_id)
        return normalize_call_end_policy(raw, language=lang)

    async def _lock_compiled_brain(
        self,
        agent_id: str,
        *,
        session_id: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Lock brain for call duration. Session fine-tune overrides take priority."""
        if session_id:
            from server.agent.instruction_store import instruction_store

            meta = instruction_store.get_with_meta(session_id)
            brain = (meta.get("brainPrompt") or "").strip()
            version = meta.get("compiledVersion") or 0
            if brain and (meta.get("present") or version or meta.get("agentBrief") or meta.get("agentScript")):
                label = f"session-v{version}" if version else "session"
                return label, brain

        from server.brain.compiled_brain_service import compiled_brain_service

        try:
            snap = await compiled_brain_service.get_active_for_agent(agent_id)
            text = (snap.get("compiled_text") or "").strip()
            if text:
                return snap.get("compiled_version"), text
        except Exception as e:
            logger.warning(f"[CALL] compiled brain lock skipped: {str(e)[:160]}")

        settings = get_settings()
        if settings.use_versioned_brains:
            return None, None

        if session_id:
            from server.agent.instruction_store import instruction_store

            brain = instruction_store.get_brain_prompt(session_id)
            if brain and brain.strip():
                return "session-default", brain.strip()

        return None, None


call_lifecycle_service = CallLifecycleService()
