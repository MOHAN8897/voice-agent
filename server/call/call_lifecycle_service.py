"""Call start/end/finalize — sole lifecycle owner."""
from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any
from weakref import WeakValueDictionary

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
from server.services.dev_runtime import (
    effective_app_environment,
    effective_config_mode,
    effective_voice_tier,
)
from server.utils.errors import AppError, ErrorCode
from server.utils.logger import log_pstn, logger

END_REASONS = {
    "opt_out", "callback_cancelled", "silence_timeout", "max_duration",
    "provider_failure", "runtime_failure", "farewell_timeout", "response_timeout", "response_failure",
    "technical_fallback",
    "user_stop",
    "timeout",
    "error",
    "transfer",
    "browser_unload",
    "pstn_hangup",
    "agent_hangup",
    "goodbye",
    "firm_refusal",
    "not_interested",
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
_start_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _serialize_session_start(start):
    @wraps(start)
    async def locked(self, **kwargs):
        key = kwargs.get("session_id") or "default"
        lock = _start_locks.setdefault(key, asyncio.Lock())
        async with lock:
            return await start(self, **kwargs)
    return locked


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _billable_duration_sec(call_id: str, ended: datetime, fallback: int | None) -> int | None:
    """PSTN/realtime_voice: bill from media connect (answer), not dial/ring."""
    meta = call_ledger.read_meta(call_id) or {}
    # A verified CDR reports talk time; its total duration includes ringing.
    if meta.get("carrier_billable_duration_sec") is not None:
        return max(0, int(meta["carrier_billable_duration_sec"]))
    conn = meta.get("connected_at")
    channel = str(meta.get("channel") or "")
    pipeline = str(meta.get("pipeline") or "")
    if not conn and meta.get("billing_timing_version") == 2:
        return 0
    if not conn or not (channel in {"pstn", "browser"} or pipeline == "realtime_voice"):
        return fallback
    try:
        st = datetime.fromisoformat(str(conn).replace("Z", "+00:00"))
        if st.tzinfo is None:
            st = st.replace(tzinfo=timezone.utc)
        end = ended if ended.tzinfo else ended.replace(tzinfo=timezone.utc)
        if meta.get("disconnected_at"):
            stop = datetime.fromisoformat(str(meta["disconnected_at"]).replace("Z", "+00:00"))
            end = min(end, stop if stop.tzinfo else stop.replace(tzinfo=timezone.utc))
        return max(0, int((end - st).total_seconds()))
    except (ValueError, TypeError):
        return fallback


def status_url(call_id: str) -> str:
    return f"/api/call/{call_id}/finalization"


def apply_recording_disclosure(compiled_text: str, agent: dict[str, Any], language: str) -> str:
    """Use the same disclosure in the dial-time and connected-call snapshots."""
    from server.prompts.agent_voice_rules import inject_recording_disclosure

    return inject_recording_disclosure(
        compiled_text,
        enabled=bool(agent.get("recording_disclosure_enabled")),
        disclosure_text=agent.get("recording_disclosure_text"),
        language=language,
    )


class CallLifecycleService:
    @_serialize_session_start
    async def start(
        self,
        *,
        agent_id: str | None = None,
        tenant_id: str | None = None,
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
        prepared_brain: tuple[str | None, str] | None = None,
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
        if isinstance(stack_override, dict):
            snapshot_tier = (stack_override.get("_voice_stack_snapshot") or {}).get("tier") or stack_override.get("tier")
            if snapshot_tier:
                if tier and tier != str(snapshot_tier):
                    raise AppError(ErrorCode.VALIDATION_ERROR, message="The selected tier does not match the voice profile", status_code=409)
                tier = str(snapshot_tier)
        tier = tier or saved.get("tier")

        agent = await self._resolve_agent(agent_id, tenant_id=tenant_id)
        env = environment or agent.get("environment") or effective_app_environment()
        effective_tier = tier or agent.get("default_tier") or effective_voice_tier()
        from server.config.constants import normalize_supported_language

        language = normalize_supported_language(
            language or (agent.get("languages") or ["te-IN"])[0]
        )

        previous = call_context.get_active_for_session(session_id)
        if previous and str(previous.tenant_id) != str(agent["tenant_id"]):
            raise AppError(ErrorCode.CONFLICT,
                message="This session is unavailable; choose a new session", status_code=409)
        if previous and not settings.call_auto_end_on_start:
            raise AppError(ErrorCode.CONFLICT,
                message="An active call already exists for this session", status_code=409)

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
        composed_snapshot = (
            copy.deepcopy(stack_override.get("_voice_stack_snapshot"))
            if pipeline in {"composed_voice", "realtime_voice"} and isinstance(stack_override, dict)
            and isinstance(stack_override.get("_voice_stack_snapshot"), dict)
            else None
        )
        from server.services.saas.voice_stack_profiles import canonical_voice_tier
        is_composed_tier = False
        try:
            norm_tier = canonical_voice_tier(effective_tier)
            is_composed_tier = bool(norm_tier)
        except Exception:
            is_composed_tier = False

        if pipeline == "composed_voice" and (
            not is_composed_tier or composed_snapshot is None
        ):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="The composed voice profile is not valid for this call.",
                status_code=409,
            )
        if composed_snapshot is not None:
            locked_rate = composed_snapshot.get("webRetailRate" if channel == "browser" else "retailRate")
            if channel == "browser" and locked_rate is None and (composed_snapshot.get("retailRate") or {}).get("complete") is True:
                from server.services.saas.billing_rates import load_current_rates
                from server.services.saas.voice_stack_profiles import _web_tier_retail_rate
                locked_rate = _web_tier_retail_rate(await load_current_rates(), str(effective_tier))
            if (
                not isinstance(locked_rate, dict)
                or locked_rate.get("complete") is not True
                or not locked_rate.get("fxRateInr")
            ):
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    message="The selected voice tier has no complete approved retail rate snapshot.",
                    status_code=409,
                )
        from server.services.saas.campaign_script import campaign_call_script
        # The outbound greeting already belongs to this exact script/session.
        # Recompiling at answer can replace personalized text or recording rules
        # and force Gemini to discard the socket that generated the greeting.
        using_prepared_brain = bool(
            prepared_brain and realtime_prewarm_key and channel == "pstn"
            and direction == "outbound" and pipeline in {"realtime_voice", "composed_voice"}
        )
        campaign_script = None if using_prepared_brain else await campaign_call_script(agent, contact)
        if using_prepared_brain:
            compiled_version, compiled_text = prepared_brain
            brain_source = "dial_snapshot"
        elif campaign_script:
            compiled_version, compiled_text = campaign_script
            brain_source = "campaign_snapshot"
        else:
            compiled_version, compiled_text, brain_source = await self._lock_compiled_brain(
                agent["agent_id"], session_id=lookup_session,
            )
        if pipeline == "composed_voice" and not str(compiled_text or "").strip():
            raise AppError(ErrorCode.VALIDATION_ERROR,
                message="Publish the agent instructions before starting a call", status_code=409)
        if compiled_text and not using_prepared_brain:
            from server.brain.script_entities import realign_compiled_brain_for_session

            compiled_text = realign_compiled_brain_for_session(
                compiled_text,
                language,
                direction=direction,
            )

            compiled_text = apply_recording_disclosure(compiled_text, agent, language)

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

            from server.brain.brain_prompt_validate import validate_rendered_brain

            issues = validate_rendered_brain(compiled_text, language)
            if issues:
                logger.error(
                    "[CALL] Prompt validation rejected agent %s (lang=%s): %s",
                    agent.get("agent_id"),
                    language,
                    "; ".join(issues),
                )
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    message=(
                        "The published agent instructions contain conflicting platform rules. "
                        "Review and republish the agent, then start the call again."
                    ),
                    status_code=409,
                )

        if compiled_text and not using_prepared_brain:
            from server.services.saas.contact_import_service import render_agent_prompt_for_contact
            # Web tests have no imported lead. Resolve fallbacks and system tags
            # there too, so neither prewarm nor Gemini reads raw template braces.
            compiled_text = render_agent_prompt_for_contact(compiled_text, contact or {})

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
            "tier": str(stack.tier or effective_tier),
            "voice_stack_snapshot": composed_snapshot,
            "billed_user_id": billed_user_id,
            "is_test": is_test,
            "contact": contact or {},
            "voicemail_mode": voicemail_mode,
            "billing_timing_version": 2,
            "recording_disclosure": {
                "enabled": bool(agent.get("recording_disclosure_enabled")),
                "text": (agent.get("recording_disclosure_text") or "").strip(),
                "injected": bool(
                    compiled_text and "### RECORDING DISCLOSURE POLICY" in compiled_text
                ),
            },
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

        # Snapshot authoritative billing rate at call start (immutable lock against future rate changes)
        if composed_snapshot is not None:
            native_rate = locked_rate
            snap_rate_micros = int(native_rate["usdMicrosPerMin"])
            snap_rate_cents = (snap_rate_micros + 5_000) // 10_000
            snap_rate_inr_paise = int(native_rate["inrPaisePerMin"])
            snap_fx = float(native_rate["fxRateInr"])
            snap_ver = int(native_rate["version"])
        else:
            try:
                from server.services.saas.billing_rates import load_current_rates

                cur_rates = await load_current_rates()
                tier_slug = str(stack.tier or effective_tier or "medium").lower()
                from server.services.saas.voice_stack_profiles import (
                    _native_tier_retail_rate,
                    _web_tier_retail_rate,
                    load_profile_records,
                )
                tier_rec = (await load_profile_records(env, (tier_slug,))).get(tier_slug)
                custom_rate = (_web_tier_retail_rate if channel == "browser" else _native_tier_retail_rate)(cur_rates, tier_slug, record=tier_rec)
                if channel == "pstn" and custom_rate is None:
                    raise AppError(ErrorCode.VALIDATION_ERROR,
                        message="The selected voice tier has no complete approved rate", status_code=409)
                if custom_rate and custom_rate.get("inrPaisePerMin"):
                    tier_rate_micros = custom_rate.get("usdMicrosPerMin")
                    tier_rate_cents = (tier_rate_micros + 5_000) // 10_000 if tier_rate_micros else None
                    tier_rate_inr = custom_rate.get("inrPaisePerMin")
                else:
                    parent_tier = "low" if (tier_slug == "low" or tier_slug.startswith("low") or "economical" in tier_slug) else ("premium" if (tier_slug == "premium" or "flagship" in tier_slug) else "medium")
                    tier_rate_cents = cur_rates.get(f"pstn_{parent_tier}_rate_usd_cents_per_min") or (cur_rates.get(f"pstn_{parent_tier}_rate_usd_micros_per_min", 0) // 10_000)
                    tier_rate_micros = cur_rates.get(f"pstn_{parent_tier}_rate_usd_micros_per_min")
                    tier_rate_inr = cur_rates.get(f"pstn_{parent_tier}_rate_inr_paise_per_min")

                snap_rate_cents = int(
                    (tier_rate_cents if tier_rate_cents else cur_rates["pstn_rate_usd_cents_per_min"])
                    if channel == "pstn"
                    else ((int(custom_rate["usdMicrosPerMin"]) + 5_000) // 10_000 if custom_rate else cur_rates["web_agent_rate_usd_cents_per_min"])
                )
                snap_rate_micros = int(
                    (tier_rate_micros if tier_rate_micros else cur_rates["pstn_rate_usd_micros_per_min"])
                    if channel == "pstn"
                    else (custom_rate["usdMicrosPerMin"] if custom_rate else cur_rates["web_agent_rate_usd_micros_per_min"])
                )
                snap_rate_inr_paise = int(
                    (tier_rate_inr if tier_rate_inr else cur_rates["pstn_rate_inr_paise_per_min"])
                    if channel == "pstn"
                    else (custom_rate["inrPaisePerMin"] if custom_rate else cur_rates["web_agent_rate_inr_paise_per_min"])
                )
                snap_fx = float(cur_rates.get("fx_rate_inr") or 0)
                if snap_fx <= 0:
                    raise ValueError("A positive INR per USD rate is required to price the call")
                snap_ver = int(cur_rates.get("version") or 1)
                if custom_rate:
                    snap_fx = float(custom_rate["fxRateInr"])
                    snap_ver = int(custom_rate["version"])
            except AppError:
                raise
            except Exception as e:
                raise AppError(ErrorCode.VALIDATION_ERROR,
                    message="Call pricing is unavailable; the call was not started", status_code=503) from e

        record["applied_rate_usd_cents_per_min"] = snap_rate_cents
        record["applied_rate_usd_micros_per_min"] = snap_rate_micros
        record["applied_rate_inr_paise_per_min"] = snap_rate_inr_paise
        record["applied_fx_rate_inr"] = snap_fx
        record["rate_version"] = snap_ver

        meta["rate_snapshot"] = {
            "usdCentsPerMin": snap_rate_cents,
            "usdMicrosPerMin": snap_rate_micros,
            "inrPaisePerMin": snap_rate_inr_paise,
            "fxRateInr": snap_fx,
            "version": snap_ver,
        }
        if pipeline == "composed_voice":
            from server.services.saas.composed_costing import snapshot_provider_costs

            meta["provider_cost_snapshot"] = await snapshot_provider_costs(
                stack.to_safe_dict(), fx_rate_inr=snap_fx,
            )
        # Failed stack/script/rate admission must not disconnect a healthy call.
        if previous:
            await self.end(previous.call_id, reason="superseded")
        await call_ledger.init(call_id, meta)
        audio_archive.init(call_id, record=not is_test)
        from server.call.memory_manager import memory_manager

        memory_manager.init(call_id)
        from server.agent.conversation_manager import conversation_manager
        from server.agent.session_memory import session_memory

        # New call = new dialogue. Compiled brain stays on the config session.
        conversation_manager.clear(session_id)
        session_memory.clear(session_id)
        if caller_id and str(direction or "").strip().lower() not in ("outbound", "outgoing", "outbound-api"):
            memory_manager.apply_proposals(
                call_id,
                [{"op": "set_fact", "key": "phone", "value": str(caller_id)[:200]}],
                turn_seq=0,
                source="telephony",
            )

        await call_store.insert(record)

        max_dur = 900
        if agent.get("tenant_id"):
            try:
                from server.services.saas.billing_wallet_service import (
                    max_allowed_call_duration_sec,
                )
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
        if pipeline == "composed_voice" and compiled_text:
            from server.services.composed_voice_session import composed_system_prompt

            composed_system_prompt(ctx)
        if compiled_text:
            from server.call.call_end_policy import policy_from_brain

            published_policy = policy_from_brain(compiled_text, language)
            if published_policy:
                ctx.call_end_policy = published_policy
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
        ended = _utcnow()
        reason = _normalize_end_reason(reason)
        ctx = call_context.get(call_id)
        issued_reason = getattr(ctx, "agent_hangup_reason", None)
        if reason in {"ws_disconnect", "pstn_hangup"} and issued_reason:
            reason = _normalize_end_reason(issued_reason)
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

        from server.call.billing_timing import mark_call_disconnected
        mark_call_disconnected(call_id, ended.isoformat())

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
        tid = stored.get("tenant_id") if stored else (ctx.tenant_id if ctx else None)
        if tid:
            try:
                from server.services.saas.call_admission import provider_event

                await provider_event(
                    tenant_id=uuid.UUID(str(tid)),
                    call_id=call_id,
                    status="ended",
                )
            except Exception as adm_e:
                logger.debug(f"[CALL] dial admission release notice: {adm_e}")
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
            from server.call.post_call_pipeline import read_outcome
            from server.services.r2_storage import r2_storage

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
            from server.services.vobiz_billing import reconcile_vobiz_call

            await reconcile_vobiz_call(call_id)
            if call_ledger.read_meta(call_id).get("vobiz_call_uuid"):
                from server.services.vobiz_recordings import schedule_recording_retrieval
                schedule_recording_retrieval(call_id)
            meta = call_ledger.read_meta(call_id)
            stored_row = await call_store.get(call_id)
            duration = _billable_duration_sec(call_id, _utcnow(), (stored_row or {}).get("duration_sec"))
            call_ledger.stamp_ended_usage(call_id, reason=meta.get("end_reason") or "ended", duration_sec=duration)
            if duration is not None:
                await call_store.update(call_id, {"duration_sec": duration})
        except Exception as exc:
            logger.warning("[BILLING] supplier cost finalization failed call=%s kind=%s", call_id, type(exc).__name__)
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

    async def _resolve_agent(self, agent_id: str | None, *, tenant_id: str | None = None) -> dict[str, Any]:
        if agent_id:
            try:
                if tenant_id is None:
                    return await agent_service.get_agent(agent_id)
                return await agent_service.get_agent(agent_id, tenant_id=tenant_id)
            except (KeyError, ValueError):
                raise AppError(ErrorCode.NOT_FOUND, message="Agent not found", status_code=404) from None
        if tenant_id:
            raise AppError(ErrorCode.NOT_FOUND, message="Agent not found", status_code=404)
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
        if self._is_server_composed_override(stack_override, tier):
            return resolve_stack(mode=effective_config_mode(), tier=tier, language=language,
                environment=environment, stack_override=stack_override, allow_composed_override=True)
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
                allow_composed_override=self._is_server_composed_override(stack_override, tier),
            )
        return resolve_stack(
            mode="env",
            tier=tier,  # type: ignore[arg-type]
            language=language,
            environment=environment,
            stack_override=stack_override,
            allow_composed_override=self._is_server_composed_override(stack_override, tier),
        )

    @staticmethod
    def _is_server_composed_override(stack_override: dict[str, Any] | None, tier: str) -> bool:
        snapshot = stack_override.get("_voice_stack_snapshot") if isinstance(stack_override, dict) else None
        return bool(
            isinstance(stack_override, dict)
            and ((stack_override.get("pipeline") == "composed_voice" and stack_override.get("voice_flow") == "composed_stages")
                 or (stack_override.get("pipeline") == "realtime_voice" and stack_override.get("voice_flow") == "realtime_e2e"))
            and isinstance(snapshot, dict)
            and snapshot.get("tier") == tier
        )

    def _coerce_pipeline_stack(
        self,
        stack: ResolvedStack,
        *,
        stack_override: dict[str, Any] | None = None,
    ) -> ResolvedStack:
        try:
            provider, model = coerce_live_llm_selection(
                stack.llm.provider,
                stack.llm.model,
                stack_override=stack_override,
            )
        except ValueError as exc:
            raise AppError(ErrorCode.VALIDATION_ERROR,
                message="The selected model does not match the voice pipeline", status_code=409) from exc
        if (provider, model) != (stack.llm.provider, stack.llm.model):
            raise AppError(ErrorCode.VALIDATION_ERROR,
                message="The selected model changed during pipeline validation", status_code=409)
        return stack

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
