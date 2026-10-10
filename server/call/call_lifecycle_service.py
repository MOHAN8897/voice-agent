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
    "opt_out", "callback_cancelled", "silence_timeout", "max_duration",
    "provider_failure", "runtime_failure", "farewell_timeout", "response_timeout", "response_failure",
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
_max_duration_tasks: dict[str, asyncio.Task] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _billable_duration_sec(call_id: str, ended: datetime, fallback: int | None) -> int | None:
    """PSTN/realtime_voice: bill from media connect (answer), not dial/ring."""
    meta = call_ledger.read_meta(call_id) or {}
    conn = meta.get("connected_at")
    channel = str(meta.get("channel") or "")
    pipeline = str(meta.get("pipeline") or "")
    if not conn or not (channel == "pstn" or pipeline == "realtime_voice"):
        return fallback
    try:
        st = datetime.fromisoformat(str(conn).replace("Z", "+00:00"))
        if st.tzinfo is None:
            st = st.replace(tzinfo=timezone.utc)
        end = ended if ended.tzinfo else ended.replace(tzinfo=timezone.utc)
        return max(0, int((end - st).total_seconds()))
    except (ValueError, TypeError):
        return fallback


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
        language: str | None = None,
        realtime_prewarm_key: str | None = None,
        billed_user_id: str | None = None,
        is_test: bool | None = None,
        contact: dict[str, Any] | None = None,
        voicemail_mode: bool = False,
    ) -> dict[str, Any]:
        settings = get_settings()
        session_id = session_id or "default"
        channel = channel if channel in ("browser", "pstn") else "browser"
        # A browser session is a practice run unless the caller says otherwise;
        # PSTN is always a real call regardless of the flag.
        is_test = (channel == "browser") if is_test is None else bool(is_test)
        direction = direction if direction in ("inbound", "outbound") else "inbound"
        lookup_session = (config_session_id or session_id).strip() or session_id
        from server.services.test_studio_config import saved_call_config

        saved = saved_call_config(lookup_session)
        # Explicit dial/web stack wins. Merging saved Test Studio prefs here
        # overwrote the SaaS Gemini platform stack with leftover OpenAI settings.
        if not stack_override:
            stack_override = saved.get("stack_override")
        tier = tier or saved.get("tier")

        agent = await self._resolve_agent(agent_id)
        env = environment or agent.get("environment") or effective_app_environment()
        effective_tier = tier or agent.get("default_tier") or effective_voice_tier()
        from server.config.constants import normalize_supported_language

        language = normalize_supported_language(
            language or (agent.get("languages") or ["te-IN"])[0]
        )

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
                language=language,
            ),
            stack_override=stack_override,
        )
        pipeline = pipeline_mode(settings=settings, stack_override=stack_override)
        compiled_version, compiled_text, brain_source = await self._lock_compiled_brain(
            agent["agent_id"],
            session_id=lookup_session,
        )
        if compiled_text:
            from server.brain.script_entities import realign_compiled_brain_for_session

            compiled_text = realign_compiled_brain_for_session(
                compiled_text,
                language,
                direction=direction,
            )

            # Dynamically sync recording disclosure setting with agent configuration
            import re
            from server.prompts.agent_voice_rules import build_recording_disclosure_instruction

            compiled_text = re.sub(
                r"\n*### RECORDING DISCLOSURE POLICY[^\n]*\n.*?(?=\n---|\n###|\Z)",
                "",
                compiled_text,
                flags=re.DOTALL,
            ).strip()

            disc_enabled = bool(agent.get("recording_disclosure_enabled"))
            if disc_enabled:
                disc_text = agent.get("recording_disclosure_text")
                disc_block = build_recording_disclosure_instruction(
                    disclosure_text=disc_text,
                    language=language,
                )
                safety_idx = compiled_text.find("\n--- SAFETY ---")
                if safety_idx >= 0:
                    compiled_text = compiled_text[:safety_idx] + disc_block + "\n" + compiled_text[safety_idx:]
                else:
                    compiled_text = compiled_text + disc_block

            if voicemail_mode:
                voicemail_block = (
                    "\n\n### AFTER-HOURS VOICEMAIL MODE:\n"
                    "The business is currently closed. You are operating in voicemail capture mode:\n"
                    "1. If not already stated in your opening greeting, politely let the caller know the office is closed.\n"
                    "2. Ask the caller for their name, best contact phone number, and a brief message or reason for calling.\n"
                    "3. Acknowledge what they share concisely. Confirm that you have noted their details.\n"
                    "4. Assure them that a team member will follow up promptly during regular business hours.\n"
                    "5. Thank them politely and conclude the call.\n"
                )
                safety_idx = compiled_text.find("\n--- SAFETY ---")
                if safety_idx >= 0:
                    compiled_text = compiled_text[:safety_idx] + voicemail_block + "\n" + compiled_text[safety_idx:]
                else:
                    compiled_text = compiled_text + voicemail_block

            from server.brain.brain_prompt_validate import assert_rendered_brain_valid

            assert_rendered_brain_valid(compiled_text, language)

        if compiled_text and contact:
            from server.services.saas.contact_import_service import render_agent_prompt_for_contact
            compiled_text = render_agent_prompt_for_contact(compiled_text, contact)

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
            "compiled_brain_text": compiled_text,
            "brain_source": brain_source,
            "config_session_id": lookup_session,
            "language": language,
            "started_at": started.isoformat(),
            "environment": env,
            "resolved_stack": stack.to_safe_dict(),
            "pipeline": pipeline,
            "billed_user_id": billed_user_id,
            "is_test": is_test,
            "contact": contact or {},
            "voicemail_mode": voicemail_mode,
        }
        from server.services.transcription_policy import attach_normalized_stack_override

        attach_normalized_stack_override(
            meta,
            stack_override,
            language=language,
            tier=str(effective_tier or "medium"),
        )
        if stack_override:
            from server.realtime.models import is_gemini_live_voice_model
            from server.services.transcription_policy import (
                pstn_stack_from_meta,
                transcription_billing_tag,
                transcription_policy_from_meta,
            )

            pstn = pstn_stack_from_meta(meta)
            llm = pstn.get("llm") if isinstance(pstn.get("llm"), dict) else {}
            gemini = is_gemini_live_voice_model(str(llm.get("model") or ""))
            policy = transcription_policy_from_meta(meta)
            tag = transcription_billing_tag(policy, gemini_live=gemini)
            usage_seed = {"transcription_billing": tag, "transcription_model": policy.live_model if policy.live_enabled else policy.post_call_model}
            meta["usage"] = usage_seed
        if channel == "pstn" or pipeline == "realtime_voice":
            try:
                from server.services.telnyx_client import TelnyxClient
                _tc = TelnyxClient()
                _bal_data = await _tc.get_balance()
                _val = _bal_data.get("balance") or _bal_data.get("available_credit")
                if _val is not None:
                    meta["telnyx_balance_start"] = float(_val)
            except Exception as _bal_err:
                logger.debug(f"[TELNYX] start balance check skipped: {_bal_err}")
        await call_ledger.init(call_id, meta)
        audio_archive.init(call_id, record=not is_test)
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
            inbound = str(direction or "").strip().lower() not in (
                "outbound",
                "outgoing",
                "outbound-api",
            )
            if inbound:
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
            "billed_user_id": billed_user_id,
            "is_test": is_test,
        }
        await call_store.insert(record)

        max_dur = 900
        if agent.get("tenant_id"):
            try:
                from server.services.saas.billing_wallet_service import max_allowed_call_duration_sec
                tid = uuid.UUID(str(agent["tenant_id"]))
                max_dur = await max_allowed_call_duration_sec(tid, channel=channel, global_cap_sec=900)
            except Exception as e:
                logger.debug(f"[CALL] max duration calc skipped: {e}")
                max_dur = 900

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
            max_duration_sec=max_dur,
            call_end_policy=self._load_call_end_policy(lookup_session, language),
            pipeline=pipeline,
        )
        call_context.put(ctx)
        self._schedule_max_duration_watchdog(call_id, max_dur)
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
        self._cancel_max_duration_watchdog(call_id)

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

        duration = _billable_duration_sec(call_id, ended, duration)

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
        try:
            from server.services.r2_storage import r2_storage

            if r2_storage.is_configured():
                mix_file = audio_archive.file_for(call_id, "mix")
                if mix_file:
                    ext = mix_file.suffix.lstrip(".").lower() or "wav"
                    await r2_storage.upload_audio_file(call_id, mix_file, fmt=ext)
        except Exception as e:
            logger.warning(f"[CALL] R2 audio upload failed {call_id}: {str(e)[:160]}")
        try:
            from server.call.post_call_transcription import schedule_post_call_transcription

            schedule_post_call_transcription(call_id)
        except Exception as e:
            logger.warning(f"[CALL] post_call_transcript schedule failed {call_id}: {str(e)[:120]}")
        try:
            from server.call.post_call_pipeline import process_now

            await process_now(call_id)
        except Exception as e:
            logger.warning(f"[CALL] post-call outcome failed {call_id}: {str(e)[:200]}")
            await enqueue_post_call(call_id)
        try:
            from server.services.r2_storage import r2_storage
            from server.call.post_call_pipeline import read_outcome

            if r2_storage.is_configured():
                outcome_data = read_outcome(call_id)
                if outcome_data:
                    await r2_storage.upload_outcome(call_id, outcome_data)
        except Exception as e:
            logger.warning(f"[CALL] R2 outcome upload failed {call_id}: {str(e)[:160]}")
        try:
            from server.services.dev_telephony_store import dev_telephony_store

            dev_telephony_store.sync_internal_call(call_id)
        except Exception:
            pass
        try:
            meta = call_ledger.read_meta(call_id)
            channel = str(meta.get("channel") or "")
            pipeline = str(meta.get("pipeline") or (meta.get("usage") or {}).get("pipeline") or "")
            if channel == "pstn" or pipeline == "realtime_voice":
                from server.services.telnyx_client import TelnyxClient
                _tc = TelnyxClient()
                _bal_end_data = await _tc.get_balance()
                _val_end = _bal_end_data.get("balance") or _bal_end_data.get("available_credit")
                if _val_end is not None:
                    bal_end = float(_val_end)
                    meta["telnyx_balance_end"] = bal_end
                    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
                    bal_start = meta.get("telnyx_balance_start")
                    if bal_start is not None:
                        delta = round(max(0.0, float(bal_start) - bal_end), 5)
                        usage["telnyx_balance_start"] = float(bal_start)
                        usage["telnyx_balance_end"] = bal_end
                        usage["telnyx_balance_delta_usd"] = delta
                        if delta > 0:
                            fx = float(usage.get("fx_rate_inr") or 95.64)
                            usage["telnyx_usd"] = delta
                            usage["telnyx_inr"] = delta * fx
                            usage["telnyx_cost_is_actual"] = True
                            usage["telnyx_cost_source"] = "live_telnyx_balance_delta"
                            model_usd = float(usage.get("model_cost_usd") or 0.0)
                            model_inr = float(usage.get("model_cost_inr") or (model_usd * fx))
                            tx_usd = float(usage.get("post_call_transcript_usd") or 0.0) + float(usage.get("live_transcript_usd") or 0.0)
                            tx_inr = float(usage.get("post_call_transcript_inr") or 0.0) + float(usage.get("live_transcript_inr") or 0.0)
                            total_usd = model_usd + delta + tx_usd
                            total_inr = model_inr + (delta * fx) + tx_inr
                            usage["cost_usd"] = total_usd
                            usage["cost_inr"] = total_inr
                            duration_sec = float(usage.get("duration_sec") or meta.get("duration_sec") or 0.0)
                            minutes = duration_sec / 60.0 if duration_sec > 0 else 0.0
                            usage["cost_usd_per_min"] = (total_usd / minutes) if minutes > 0 else 0.0
                            usage["cost_inr_per_min"] = (total_inr / minutes) if minutes > 0 else 0.0
                            usage["telnyx_usd_per_min"] = (delta / minutes) if minutes > 0 else 0.0
                            usage["telnyx_inr_per_min"] = ((delta * fx) / minutes) if minutes > 0 else 0.0
                        else:
                            usage["telnyx_cost_is_actual"] = False
                            usage["telnyx_cost_source"] = "tariff_rate_deck"
                    meta["usage"] = usage
                    call_ledger.write_meta(call_id, meta)
                    await call_store.update(call_id, {
                        "cost_usd": usage.get("cost_usd"),
                        "cost_inr": usage.get("cost_inr"),
                    })
        except Exception as _bal_exc:
            logger.debug(f"[TELNYX] finalize balance check skipped {call_id}: {_bal_exc}")
        try:
            from server.config.env import get_settings
            from server.services.saas.billing_wallet_service import bill_pstn_call_if_applicable

            if get_settings().saas_auth_enabled:
                asyncio.create_task(bill_pstn_call_if_applicable(call_id))
        except Exception as e:
            logger.warning(f"[CALL] wallet bill skipped {call_id}: {str(e)[:120]}")
        try:
            from server.services.saas.dnc_service import handle_call_opt_out

            stored_row = await call_store.get(call_id)
            disposition = (stored_row or {}).get("disposition")
            end_reason = (stored_row or {}).get("end_reason")
            await handle_call_opt_out(call_id, reason=end_reason, disposition=disposition)
        except Exception as e:
            logger.warning(f"[CALL] opt-out DND auto-enroll check failed {call_id}: {str(e)[:120]}")

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
        if not body.get("pipeline") and stored:
            body["pipeline"] = stored.get("pipeline")
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

    def _schedule_max_duration_watchdog(self, call_id: str, max_sec: int) -> None:
        self._cancel_max_duration_watchdog(call_id)
        if max_sec <= 0:
            return

        async def _fire() -> None:
            await asyncio.sleep(max_sec)
            ctx = call_context.get(call_id)
            if ctx and ctx.status == "active":
                logger.info("[CALL] max allowed duration reached (%ds) for %s; terminating", max_sec, call_id)
                await self.end(call_id, reason="max_duration")

        try:
            _max_duration_tasks[call_id] = asyncio.create_task(_fire())
        except RuntimeError:
            pass

    def _cancel_max_duration_watchdog(self, call_id: str) -> None:
        task = _max_duration_tasks.pop(call_id, None)
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
    ) -> tuple[str | None, str | None, str]:
        """Lock brain for call duration. Session fine-tune overrides take priority."""
        from server.call.call_brain_lock import resolve_locked_compiled_brain

        version, text, source = await resolve_locked_compiled_brain(
            agent_id,
            session_id=session_id,
        )
        return version, text, source


call_lifecycle_service = CallLifecycleService()
