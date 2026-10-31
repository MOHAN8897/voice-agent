"""PSTN outbound prewarm — Realtime + greeting TTS while the phone is ringing."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from server.services.pstn_debug import log_pstn
from server.services.pstn_text_chunker import extract_opening_greeting, extract_prewarm_greeting
from server.services.pstn_voice_core import pstn_call_options

logger = logging.getLogger(__name__)

PREWARM_TTL_SEC = 90.0
PREWARM_ADOPT_WAIT_SEC = 1.5
# First slice at answer is short (C1); keep waiting for a dial-time bundle before giving up.
MAX_PREWARM_ADOPT_TOTAL_SEC = 12.0

_PROVIDER_WIRE: dict[str, dict[str, Any]] = {
    "telnyx": {"sample_rate": 16000, "tts_output_codec": "linear16"},
    "vobiz": {"sample_rate": 16000, "tts_output_codec": "linear16"},
}


def prewarm_realtime_key(provider: str, external_id: str) -> str:
    return f"prewarm-{provider}-{external_id}"


def _runtime_max_output_tokens(session_id: str) -> int | None:
    from server.services.runtime_settings import runtime_settings

    raw = runtime_settings.get(session_id).get("openaiMaxTokens")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@dataclass
class PstnPrewarmBundle:
    provider: str
    external_id: str
    realtime_key: str
    greeting_text: str | None
    greeting_wire_frames: list[bytes] = field(default_factory=list)
    greeting_transcript: str | None = None
    greeting_source: str | None = None
    greeting_usage: dict[str, Any] | None = None
    greeting_model: str | None = None
    compiled_brain_text: str | None = None
    compiled_brain_version: str | None = None
    compiled_brain_checksum: str | None = None
    config_session_id: str | None = None
    language: str = "te-IN"
    agent_id: str | None = None
    cost_record_key: str | None = None
    greeting_sample_rate: int = 16000
    greeting_codec: str = "linear16"
    greeting_tts_usage: dict[str, Any] | None = None
    greeting_text_usage: dict[str, Any] | None = None


class _PrewarmVoiceStub:
    """Minimal PstnVoiceLoop surface for greeting TTS synthesis into a buffer."""

    def __init__(
        self,
        *,
        session_id: str,
        call_id: str | None,
        sample_rate: int,
        tts_output_codec: str,
        language: str,
    ) -> None:
        self.session_id = session_id
        self.config_session_id = session_id
        self.tts_session_id = session_id
        self.call_id = call_id
        self.sample_rate = sample_rate
        self.tts_output_codec = tts_output_codec
        self.language = language
        self.current_output_codec = "L16" if sample_rate >= 16000 else "PCMU"
        self.current_turn_id: str | None = "prewarm"
        self.current_generation_id: str | None = "prewarm"
        self._interrupted_generation: str | None = None
        self._closed = False
        self._wire_frames_out = 0
        self.frames: list[bytes] = []

    def _resolve_language(self) -> str:
        return self.language

    def emission_blocked(self) -> bool:
        """Prewarm always allows TTS emission into the greeting buffer."""
        return False

    async def _emit_agent_wire(self, wire: bytes) -> None:
        if wire:
            self.frames.append(wire)
            self._wire_frames_out += 1


@dataclass
class _PrewarmEntry:
    provider: str
    external_id: str
    task: asyncio.Task
    created_at: float
    realtime_key: str = ""
    bundle: PstnPrewarmBundle | None = None
    error: str | None = None
    exc: BaseException | None = None


class PstnPrewarmRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, _PrewarmEntry] = {}
        self._lock = asyncio.Lock()

    def _key(self, provider: str, external_id: str) -> str:
        return f"{provider}:{external_id}"

    async def prepare(self, provider: str, external_id: str, dial_meta: dict[str, Any],
                      *, timeout_sec: float = 20.0) -> None:
        """Finish the opening before dialing, so a fast pickup cannot cancel it."""
        await self.start(provider, external_id, dial_meta)
        entry = self._entries[self._key(provider, external_id)]
        try:
            await asyncio.wait_for(asyncio.shield(entry.task), timeout=timeout_sec)
            bundle = entry.bundle
            if bundle is None or not bundle.greeting_text or not bundle.greeting_wire_frames:
                # Chain the real cause so callers can tell a vendor outage
                # (Sarvam out of credits) from a local preparation fault.
                raise RuntimeError("Opening audio preparation failed; call was not placed") from entry.exc
        except BaseException:
            await self.cancel(provider, external_id)
            raise

    async def bind(self, provider: str, prepared_id: str, external_id: str) -> None:
        """Move a prepared bundle to its carrier ID after the dial API returns."""
        async with self._lock:
            entry = self._entries.pop(self._key(provider, prepared_id), None)
            if entry is None:
                # A very fast answer may already have claimed the prepared ID
                # from signed stream metadata while the dial HTTP was in flight.
                return
            entry.external_id = external_id
            if entry.bundle:
                entry.bundle.external_id = external_id
            key = self._key(provider, external_id)
            self._entries[key] = entry
        asyncio.create_task(self._expire_if_unclaimed(key, entry.realtime_key, owner=entry.task))
        log_pstn("prewarm.bound", control=external_id, call_id=prepared_id)

    async def start(self, provider: str, external_id: str, dial_meta: dict[str, Any]) -> None:
        key = self._key(provider, external_id)
        async with self._lock:
            existing = self._entries.get(key)
            if existing:
                # Duplicate dial webhooks must not cancel a warming socket.
                # Brain changes are checked against the call snapshot at answer.
                return
            rt_key = f"{prewarm_realtime_key(provider, external_id)}-{uuid.uuid4().hex[:12]}"
            task = asyncio.create_task(
                self._run(provider, external_id, dial_meta, rt_key=rt_key),
                name=f"pstn-prewarm-{provider}-{external_id}",
            )
            self._entries[key] = _PrewarmEntry(
                provider=provider,
                external_id=external_id,
                task=task,
                created_at=time.monotonic(),
                realtime_key=rt_key,
            )

    async def _run(self, provider: str, external_id: str, dial_meta: dict[str, Any], *, rt_key: str) -> None:
        key = self._key(provider, external_id)
        bundle: PstnPrewarmBundle | None = None
        try:
            bundle = await _build_prewarm_bundle(provider, external_id, dial_meta, rt_key)
            if bundle.greeting_usage and bundle.greeting_model:
                from server.services.saas.prewarm_cost_records import record_prepared
                try:
                    bundle.cost_record_key = await record_prepared(rt_key, tenant_id=str(dial_meta.get("tenant_id") or ""), usage=bundle.greeting_usage, model=bundle.greeting_model)
                except Exception as exc:
                    logger.warning("[BILLING] prewarm cost record failed kind=%s", type(exc).__name__)
            async with self._lock:
                entry = self._entries.get(key)
                if entry is not None and entry.task is asyncio.current_task():
                    entry.bundle = bundle
            log_pstn(
                "prewarm.ready",
                control=external_id,
                provider=provider,
                greeting_chars=len(bundle.greeting_text or ""),
                greeting_frames=len(bundle.greeting_wire_frames),
            )
            asyncio.create_task(
                self._expire_if_unclaimed(key, rt_key, owner=asyncio.current_task()),
                name=f"pstn-prewarm-expire-{provider}-{external_id}",
            )
        except asyncio.CancelledError:
            await _destroy_realtime(rt_key)
            raise
        except Exception as exc:
            err = str(exc).strip() or f"{type(exc).__name__}"
            async with self._lock:
                entry = self._entries.get(key)
                if entry is not None and entry.task is asyncio.current_task():
                    entry.error = err[:200]
                    entry.exc = exc
            await _destroy_realtime(rt_key)
            log_pstn("prewarm.failed", control=external_id, provider=provider, error=err[:200])
            logger.warning("[PSTN] prewarm failed %s %s: %s", provider, external_id, err[:200])

    async def take(
        self,
        provider: str,
        external_id: str,
        *,
        wait_sec: float = PREWARM_ADOPT_WAIT_SEC,
    ) -> PstnPrewarmBundle | None:
        key = self._key(provider, external_id)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            task = entry.task
            bundle = entry.bundle
            claimed_entry = entry
        if bundle is None and task and not task.done():
            deadline = time.monotonic() + MAX_PREWARM_ADOPT_TOTAL_SEC
            while bundle is None and not task.done():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    log_pstn(
                        "prewarm.adopt_timeout",
                        control=external_id,
                        provider=provider,
                        wait_sec=wait_sec,
                        reason="greeting_not_ready_at_answer",
                    )
                    break
                try:
                    await asyncio.wait_for(
                        asyncio.shield(task),
                        timeout=min(wait_sec, remaining),
                    )
                except asyncio.TimeoutError:
                    async with self._lock:
                        live = self._entries.get(key)
                        if live is not None:
                            bundle = live.bundle
                    continue
            async with self._lock:
                live = self._entries.get(key)
                if live is not None and bundle is None:
                    bundle = live.bundle
        async with self._lock:
            if self._entries.get(key) is not claimed_entry:
                return None
            entry = self._entries.pop(key, None)
        if entry is None:
            return None
        if entry.bundle is not None:
            log_pstn(
                "prewarm.adopted",
                control=external_id,
                provider=provider,
                greeting_frames=len(entry.bundle.greeting_wire_frames),
            )
            return entry.bundle
        if entry.error:
            log_pstn("prewarm.adopt_miss", control=external_id, provider=provider, error=entry.error)
        if not entry.task.done():
            entry.task.cancel()
            try:
                await entry.task
            except (asyncio.CancelledError, Exception):
                pass
        return None

    async def cancel(self, provider: str, external_id: str) -> None:
        key = self._key(provider, external_id)
        async with self._lock:
            entry = self._entries.pop(key, None)
        if entry is None:
            return
        if not entry.task.done():
            entry.task.cancel()
            try:
                await entry.task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        if entry.bundle and entry.bundle.realtime_key:
            if entry.bundle.cost_record_key:
                from server.services.saas.prewarm_cost_records import mark_usage
                await mark_usage(entry.bundle.cost_record_key)
            await _destroy_realtime(entry.bundle.realtime_key)
        else:
            await _destroy_realtime(getattr(entry, "realtime_key", "") or prewarm_realtime_key(provider, external_id))
        log_pstn("prewarm.cancelled", control=external_id, provider=provider)

    async def _expire_if_unclaimed(self, key: str, rt_key: str, *, owner: asyncio.Task | None = None) -> None:
        await asyncio.sleep(PREWARM_TTL_SEC)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None or (owner is not None and entry.task is not owner):
                return
            self._entries.pop(key, None)
        if entry is not None:
            if entry.bundle and entry.bundle.cost_record_key:
                from server.services.saas.prewarm_cost_records import mark_usage
                await mark_usage(entry.bundle.cost_record_key)
            await _destroy_realtime(rt_key)
            log_pstn("prewarm.expired", control=entry.external_id, provider=entry.provider)


async def take_prewarm_for_answer(
    provider: str,
    external_id: str,
    *,
    fallback_external_id: str | None = None,
    fallback_external_ids: tuple[str, ...] = (),
) -> PstnPrewarmBundle | None:
    bundle = None
    for candidate in dict.fromkeys((external_id, fallback_external_id, *fallback_external_ids)):
        if candidate:
            bundle = await pstn_prewarm_registry.take(provider, candidate)
            if bundle is not None:
                break
    if bundle is None:
        return None
    if provider == "vobiz":
        # Keep the immutable, contact-personalized script that produced this
        # opening. Published edits apply to the next dial, not midway through it.
        return bundle
    # Compare against the same effective brain source used during prewarm. A
    # Test Studio session version (session-vN) is not comparable to the
    # agent's published version (cb_vN); comparing their labels destroyed
    # valid warm sockets at answer.
    if bundle.agent_id and bundle.compiled_brain_checksum:
        try:
            from server.call.call_lifecycle_service import call_lifecycle_service

            current_version, current_text, _src = await call_lifecycle_service._lock_compiled_brain(
                bundle.agent_id,
                session_id=bundle.config_session_id,
            )
            if current_text and bundle.language:
                from server.brain.script_entities import realign_compiled_brain_for_session

                current_text = realign_compiled_brain_for_session(
                    current_text,
                    str(bundle.language),
                    direction="outbound",
                )
            current_checksum = (
                hashlib.sha256(current_text.encode("utf-8")).hexdigest()
                if current_text
                else None
            )
            if current_checksum and current_checksum != bundle.compiled_brain_checksum:
                log_pstn(
                    "prewarm.stale_brain",
                    control=external_id,
                    provider=provider,
                    prewarm=bundle.compiled_brain_version,
                    active=current_version,
                )
                await _destroy_realtime(bundle.realtime_key)
                bundle.realtime_key = None
        except Exception as exc:
            logger.warning("[PSTN] prewarm brain check failed: %s", str(exc)[:160])
    return bundle


async def record_bundle_greeting_usage(call_id: str | None, bundle: PstnPrewarmBundle | None) -> None:
    """Record provider-reported usage for the separate deferred opening."""
    if not call_id or bundle is None:
        return
    usage = bundle.greeting_usage
    if isinstance(usage, dict) and usage:
        from server.services.pstn_realtime_voice_core import record_realtime_voice_usage

        await record_realtime_voice_usage(
            call_id=call_id,
            usage=usage,
            llm_model=bundle.greeting_model or "gpt-realtime-2.1-mini",
            assistant_text=bundle.greeting_text or "",
            prewarm=True,
        )
        if bundle.cost_record_key:
            from server.services.saas.prewarm_cost_records import mark_usage

            await mark_usage(bundle.cost_record_key, call_id=call_id)
    else:
        model = getattr(bundle, "greeting_model", None)
        if model:
            log_pstn("prewarm.usage.unavailable", call_id=call_id, model=model)

    tts_usage = getattr(bundle, "greeting_tts_usage", None)
    text_usage = getattr(bundle, "greeting_text_usage", None)
    if isinstance(text_usage, dict) and text_usage:
        from server.services.saas.composed_costing import composed_llm_usage, record_composed_stage_usage

        record_composed_stage_usage(call_id, "llm", composed_llm_usage(text_usage))
    if isinstance(tts_usage, dict) and tts_usage:
        from server.services.saas.composed_costing import merge_composed_tts_usage

        try:
            merge_composed_tts_usage(call_id, tts_usage, prewarm=True)
        except Exception as exc:
            log_pstn(
                "prewarm.tts_usage.persist_failed",
                call_id=call_id,
                error_type=type(exc).__name__,
            )


pstn_prewarm_registry = PstnPrewarmRegistry()


async def _destroy_realtime(call_key: str) -> None:
    from server.realtime.manager import realtime_text_manager
    from server.realtime.voice_manager import realtime_voice_manager

    try:
        await realtime_text_manager.destroy(call_key)
    except Exception:
        pass
    try:
        await realtime_voice_manager.destroy(call_key)
    except Exception:
        pass


async def _build_prewarm_bundle(
    provider: str,
    external_id: str,
    dial_meta: dict[str, Any],
    rt_key: str,
) -> PstnPrewarmBundle:
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.config.env import get_settings
    from server.realtime.manager import realtime_text_manager
    from server.realtime.text_session import build_session_instructions
    from server.services.dev_runtime import effective_app_environment

    pstn_opts = pstn_call_options(dial_meta)
    config_session = str(pstn_opts.get("config_session_id") or rt_key)
    agent_id = str(dial_meta.get("agent_id") or "")
    agent = await call_lifecycle_service._resolve_agent(agent_id or None)
    from server.config.constants import normalize_supported_language

    language = normalize_supported_language(
        pstn_opts.get("language")
        or dial_meta.get("language")
        or (agent.get("languages") or ["te-IN"])[0]
    )
    stack = call_lifecycle_service._coerce_pipeline_stack(
        call_lifecycle_service._resolve_locked_stack(
            session_id=config_session,
            tier=str(dial_meta.get("tier") or
                     ((pstn_opts.get("stack_override") or {}).get("_voice_stack_snapshot") or {}).get("tier") or
                     agent.get("default_tier") or "medium"),
            environment=agent.get("environment") or effective_app_environment(),
            stack_override=pstn_opts.get("stack_override"),
            language=language,
        ),
        stack_override=pstn_opts.get("stack_override"),
    )
    from server.services.saas.campaign_script import campaign_call_script
    campaign_script = await campaign_call_script(agent, dial_meta.get("contact")) if provider == "vobiz" else None
    if campaign_script:
        _version, compiled = campaign_script
    else:
        _version, compiled, _brain_src = await call_lifecycle_service._lock_compiled_brain(
            agent["agent_id"], session_id=config_session,
        )
    if compiled:
        from server.brain.script_entities import realign_compiled_brain_for_session

        compiled = realign_compiled_brain_for_session(
            compiled,
            language,
            direction="outbound",
        )
    if provider == "vobiz" and compiled:
        from server.call.call_lifecycle_service import apply_recording_disclosure
        from server.services.saas.contact_import_service import render_agent_prompt_for_contact
        compiled = apply_recording_disclosure(compiled, agent, language)
        compiled = render_agent_prompt_for_contact(compiled, dial_meta.get("contact") or {})
    wire = _PROVIDER_WIRE.get(provider, _PROVIDER_WIRE["telnyx"])
    sample_rate = int(wire["sample_rate"])
    tts_codec = str(wire["tts_output_codec"])
    from server.services.saas.telephony_profile import get_profile
    tp = await get_profile(agent.get("agent_id") or agent_id) if (agent.get("agent_id") or agent_id) else None
    tp_greeting = (tp.get("greeting_phrase") or "").strip() if tp else ""
    if not is_prewarm_greeting_enabled():
        greeting = ""
    else:
        greeting = tp_greeting or extract_prewarm_greeting(compiled, language, direction="outbound")
    generated_greeting_transcript = None

    settings = get_settings()
    from server.realtime.models import pipeline_mode

    mode = pipeline_mode(settings=settings, stack_override=pstn_opts.get("stack_override"))
    greeting_text_usage = None
    if greeting and mode == "composed_voice":
        from server.services.composed_voice_session import localize_composed_opening

        greeting, greeting_text_usage = await localize_composed_opening(
            greeting, language=language, llm=stack.llm,
        )
    if mode == "realtime_text":
        await realtime_text_manager.create(
            rt_key,
            compiled_brain=compiled,
            model=stack.llm.model,
            language=language,
            instructions=build_session_instructions(compiled, language=language),
            wait_ready=True,
        )
        log_pstn("prewarm.realtime.ready", control=external_id, provider=provider, model=stack.llm.model)
    elif mode == "realtime_voice":
        from server.realtime.models import resolve_realtime_voice_max_output_tokens
        from server.realtime.voice_instructions import build_realtime_voice_instructions
        from server.realtime.voice_manager import realtime_voice_manager

        tenant_tools = []
        tenant_id = (dial_meta.get("tenant_id") or agent.get("tenant_id")) if provider == "vobiz" else None
        if tenant_id:
            from server.db.connection import get_session_factory
            from server.services.tenant_tool_cache import get_active_app_names
            from server.services.tool_schema_registry import get_tools_for_agent
            factory = get_session_factory()
            active_apps = await get_active_app_names(str(tenant_id), factory)
            tenant_tools = await get_tools_for_agent(active_apps, str(tenant_id), agent_id, factory, None,
                                                    include_platform=True, compiled_text=compiled)

        await realtime_voice_manager.create(
            rt_key,
            compiled_brain=compiled,
            model=stack.llm.model,
            language=language,
            instructions=build_realtime_voice_instructions(
                compiled,
                model=stack.llm.model,
                stack_override=pstn_opts.get("stack_override"),
                language=language,
                direction="outbound",
                opening_greeting=greeting,
            ),
            stack_override=pstn_opts.get("stack_override"),
            max_output_tokens=resolve_realtime_voice_max_output_tokens(
                _runtime_max_output_tokens(config_session)
            ),
            wait_ready=True,
            extra_tools=tenant_tools,
        )
        warm_adapter = realtime_voice_manager.get(rt_key)
        if warm_adapter is not None:
            warm_adapter.pstn_prewarm_brain = compiled
            warm_adapter.pstn_prewarm_tools = tenant_tools
        log_pstn(
            "prewarm.realtime_voice.ready",
            control=external_id,
            provider=provider,
            model=stack.llm.model,
        )

    frames: list[bytes] = []
    greeting_source: str | None = None
    greeting_usage: dict[str, Any] | None = None
    greeting_tts_usage: dict[str, Any] | None = None
    if greeting and mode == "realtime_voice":
        adapter = realtime_voice_manager.get(rt_key)
        if adapter is not None:
            from server.realtime.models import is_gemini_live_voice_model, realtime_voice_config
            from server.services.pstn_realtime_greeting_prewarm import (
                synthesize_gemini_greeting_on_side_session,
                synthesize_realtime_greeting_frames,
            )

            try:
                if is_gemini_live_voice_model(stack.llm.model) and provider == "vobiz":
                    frames, greeting_transcript, greeting_usage = await synthesize_realtime_greeting_frames(
                        adapter, greeting_text=greeting, sample_rate=sample_rate,
                        tts_output_codec=tts_codec, language=language,
                        control_id=external_id, preserve_history=True,
                    )
                elif is_gemini_live_voice_model(stack.llm.model):
                    # Gemini cannot delete conversation items. Speak the opening
                    # on a throwaway Live session so the adopted PSTN session
                    # stays history-clean, matching OpenAI's item.delete flow.
                    cfg = realtime_voice_config(pstn_opts.get("stack_override"))
                    frames, greeting_transcript, greeting_usage = (
                        await synthesize_gemini_greeting_on_side_session(
                            greeting_text=greeting,
                            sample_rate=sample_rate,
                            tts_output_codec=tts_codec,
                            language=language,
                            model=stack.llm.model,
                            voice=str(cfg.get("voice") or ""),
                            speed=cfg.get("speed"),
                            turn_detection=str(cfg.get("turn_detection") or ""),
                            max_output_tokens=resolve_realtime_voice_max_output_tokens(
                                _runtime_max_output_tokens(config_session)
                            ),
                            control_id=external_id,
                        )
                    )
                else:
                    frames, greeting_transcript, greeting_usage = await synthesize_realtime_greeting_frames(
                        adapter,
                        greeting_text=greeting,
                        sample_rate=sample_rate,
                        tts_output_codec=tts_codec,
                        language=language,
                        control_id=external_id,
                    )
                if frames:
                    auto_response = getattr(adapter, "set_auto_response", None)
                    if not callable(auto_response):
                        log_pstn(
                            "prewarm.greeting.realtime.failed",
                            control=external_id,
                            provider=provider,
                            error="adapter_missing_auto_response_control",
                        )
                        frames = []
                    else:
                        # VAD remains active so speech_started/stopped still
                        # arrive; only automatic response.create is disabled.
                        await auto_response(False)
                if frames:
                    # Generated transcript is delivery evidence, not a new opening source.
                    generated_greeting_transcript = greeting_transcript or greeting
                    greeting_source = "realtime_voice"
                    log_pstn(
                        "prewarm.greeting.realtime",
                        control=external_id,
                        provider=provider,
                        frames=len(frames),
                        chars=len(greeting or ""),
                    )
                else:
                    # Silently ending up with no opening meant the agent said nothing
                    # until the callee spoke, on an answered billable call.
                    log_pstn(
                        "prewarm.greeting.realtime.empty",
                        control=external_id,
                        provider=provider,
                        model=stack.llm.model,
                        chars=len(greeting or ""),
                        greeting=(greeting or "")[:120],
                        reason="provider_returned_no_audio",
                    )
            except Exception as exc:
                log_pstn(
                    "prewarm.greeting.realtime.failed",
                    control=external_id,
                    provider=provider,
                    error=str(exc)[:200],
                )
                frames = []
    elif greeting and mode != "realtime_voice":
        frames, greeting_tts_usage = await _synthesize_greeting_frames(
            greeting=greeting,
            session_id=config_session,
            pseudo_call_id=rt_key,
            sample_rate=sample_rate,
            tts_output_codec=tts_codec,
            language=language,
            resolved_stack=stack,
            pipeline=mode,
        )
        if frames:
            greeting_source = "tts"
    elif greeting:
        # greeting is set but the pipeline is neither realtime_voice nor classic.
        log_pstn(
            "prewarm.greeting.skipped",
            control=external_id,
            provider=provider,
            mode=mode,
            chars=len(greeting),
            reason="unsupported_pipeline",
        )

    # While the phone rings, also render the outage announcement in this call's
    # language and voice (cached per tenant/agent/language/voice). It must exist
    # before a failure, because the failing LLM/TTS cannot be asked for it then.
    try:
        from server.services.outage_clip_prewarm import schedule_outage_clip_prewarm

        schedule_outage_clip_prewarm(
            tenant_id=str(dial_meta.get("tenant_id") or agent.get("tenant_id") or "") or None,
            agent_id=str(agent.get("agent_id") or agent_id or "") or None,
            language=language,
            resolved_stack=stack,
            pipeline=mode,
            stack_override=pstn_opts.get("stack_override"),
        )
    except Exception as exc:
        log_pstn("outage_clip.schedule_failed", control=external_id, error_type=type(exc).__name__)

    return PstnPrewarmBundle(
        provider=provider,
        external_id=external_id,
        realtime_key=rt_key,
        greeting_text=greeting,
        greeting_transcript=generated_greeting_transcript,
        greeting_wire_frames=frames,
        greeting_source=greeting_source,
        greeting_usage=greeting_usage,
        greeting_model=stack.llm.model if greeting_source == "realtime_voice" else None,
        compiled_brain_text=compiled,
        compiled_brain_version=str(_version) if _version else None,
        compiled_brain_checksum=(
            hashlib.sha256(compiled.encode("utf-8")).hexdigest()
            if compiled
            else None
        ),
        config_session_id=config_session,
        language=language,
        agent_id=agent_id or None,
        greeting_sample_rate=sample_rate,
        greeting_codec=tts_codec,
        greeting_tts_usage=greeting_tts_usage if greeting_source == "tts" else None,
        greeting_text_usage=greeting_text_usage,
    )


async def _synthesize_greeting_frames(
    *,
    greeting: str,
    session_id: str,
    pseudo_call_id: str,
    sample_rate: int,
    tts_output_codec: str,
    language: str,
    resolved_stack: Any | None = None,
    pipeline: str | None = None,
) -> tuple[list[bytes], dict[str, Any]]:
    from server.services.pstn_turn_tts import PstnTurnTtsSession
    from server.services.spoken_numbers import prepare_spoken_reply

    selection = resolved_stack.get("tts", {}) if isinstance(resolved_stack, dict) else getattr(resolved_stack, "tts", None)
    provider = selection.get("provider") if isinstance(selection, dict) else getattr(selection, "provider", None)
    model = selection.get("model") if isinstance(selection, dict) else getattr(selection, "model", None)
    text = prepare_spoken_reply(greeting or "", provider=provider, model=model, language=language).strip()
    if not text:
        return [], {}
    stub = _PrewarmVoiceStub(
        session_id=session_id,
        # A prewarm has no real call ID. Keep usage in the bundle so it can be
        # attached after answer instead of creating a pseudo-call ledger entry.
        call_id=None,
        sample_rate=sample_rate,
        tts_output_codec=tts_output_codec,
        language=language,
    )
    session = PstnTurnTtsSession(stub)
    try:
        await session.open(language_code=language, resolved_stack=resolved_stack, pipeline=pipeline)
        await session.send_text(text)
        await session.finish()
        if session.had_error or not stub.frames:
            raise RuntimeError("PSTN greeting prewarm produced no usable audio")
    finally:
        await session.close()
    return list(stub.frames), {
        "input_characters": int(getattr(session, "_chars_sent", 0) or 0),
        "output_audio_seconds": round(float(getattr(session, "_tts_audio_seconds", 0) or 0), 6),
        "output_audio_samples": int(getattr(session, "_tts_pcm_samples", 0) or 0),
        "native_usage": dict(getattr(session, "_tts_native_usage", {}) or {}),
    }


def is_prewarm_greeting_enabled() -> bool:
    """Check if prewarm greeting synthesis is enabled globally by admin."""
    try:
        from server.services.dev_secrets_store import dev_secrets_store

        return bool(dev_secrets_store.effective("enable_prewarm_greeting", True))
    except Exception:
        pass
    from server.config.env import get_settings

    return bool(getattr(get_settings(), "enable_prewarm_greeting", True))


def schedule_prewarm(provider: str, external_id: str, dial_meta: dict[str, Any]) -> None:
    """Fire-and-forget prewarm on outbound dial (ring time hides Realtime + greeting TTS)."""
    if not is_prewarm_greeting_enabled():
        log_pstn("prewarm.disabled", control=external_id, provider=provider)
        return
    if not external_id or not dial_meta.get("agent_id"):
        return
    log_pstn("prewarm.start", control=external_id, provider=provider, agent_id=dial_meta.get("agent_id"))
    asyncio.create_task(
        pstn_prewarm_registry.start(provider, external_id, dial_meta),
        name=f"schedule-prewarm-{provider}-{external_id}",
    )


async def cancel_prewarm(provider: str, external_id: str) -> None:
    if not external_id:
        return
    await pstn_prewarm_registry.cancel(provider, external_id)
