"""PSTN outbound prewarm — Realtime + greeting TTS while the phone is ringing."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from server.services.pstn_debug import log_pstn
from server.services.pstn_text_chunker import extract_opening_greeting
from server.services.pstn_voice_core import pstn_call_options

logger = logging.getLogger(__name__)

PREWARM_TTL_SEC = 90.0
PREWARM_ADOPT_WAIT_SEC = 0.15

_PROVIDER_WIRE: dict[str, dict[str, Any]] = {
    "telnyx": {"sample_rate": 16000, "tts_output_codec": "linear16"},
    "exotel": {"sample_rate": 8000, "tts_output_codec": "mulaw"},
    "plivo": {"sample_rate": 8000, "tts_output_codec": "mulaw"},
}


def prewarm_realtime_key(provider: str, external_id: str) -> str:
    return f"prewarm-{provider}-{external_id}"


@dataclass
class PstnPrewarmBundle:
    provider: str
    external_id: str
    realtime_key: str
    greeting_text: str | None
    greeting_wire_frames: list[bytes] = field(default_factory=list)
    compiled_brain_text: str | None = None
    compiled_brain_version: str | None = None
    language: str = "te-IN"
    agent_id: str | None = None


class _PrewarmVoiceStub:
    """Minimal PstnVoiceLoop surface for greeting TTS synthesis into a buffer."""

    def __init__(
        self,
        *,
        session_id: str,
        call_id: str,
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
    bundle: PstnPrewarmBundle | None = None
    error: str | None = None


class PstnPrewarmRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, _PrewarmEntry] = {}
        self._lock = asyncio.Lock()

    def _key(self, provider: str, external_id: str) -> str:
        return f"{provider}:{external_id}"

    async def start(self, provider: str, external_id: str, dial_meta: dict[str, Any]) -> None:
        key = self._key(provider, external_id)
        async with self._lock:
            existing = self._entries.get(key)
            if existing and not existing.task.done():
                existing.task.cancel()
            task = asyncio.create_task(
                self._run(provider, external_id, dial_meta),
                name=f"pstn-prewarm-{provider}-{external_id}",
            )
            self._entries[key] = _PrewarmEntry(
                provider=provider,
                external_id=external_id,
                task=task,
                created_at=time.monotonic(),
            )

    async def _run(self, provider: str, external_id: str, dial_meta: dict[str, Any]) -> None:
        key = self._key(provider, external_id)
        rt_key = prewarm_realtime_key(provider, external_id)
        bundle: PstnPrewarmBundle | None = None
        try:
            bundle = await _build_prewarm_bundle(provider, external_id, dial_meta, rt_key)
            async with self._lock:
                entry = self._entries.get(key)
                if entry is not None:
                    entry.bundle = bundle
            log_pstn(
                "prewarm.ready",
                control=external_id,
                provider=provider,
                greeting_chars=len(bundle.greeting_text or ""),
                greeting_frames=len(bundle.greeting_wire_frames),
            )
            asyncio.create_task(
                self._expire_if_unclaimed(key, rt_key),
                name=f"pstn-prewarm-expire-{provider}-{external_id}",
            )
        except asyncio.CancelledError:
            await _destroy_realtime(rt_key)
            raise
        except Exception as exc:
            async with self._lock:
                entry = self._entries.get(key)
                if entry is not None:
                    entry.error = str(exc)[:200]
            await _destroy_realtime(rt_key)
            log_pstn("prewarm.failed", control=external_id, provider=provider, error=str(exc)[:200])
            logger.warning("[PSTN] prewarm failed %s %s: %s", provider, external_id, str(exc)[:200])

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
        if bundle is None and task and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=wait_sec)
            except asyncio.TimeoutError:
                pass
        async with self._lock:
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
        await _destroy_realtime(prewarm_realtime_key(provider, external_id))
        log_pstn("prewarm.cancelled", control=external_id, provider=provider)

    async def _expire_if_unclaimed(self, key: str, rt_key: str) -> None:
        await asyncio.sleep(PREWARM_TTL_SEC)
        async with self._lock:
            entry = self._entries.pop(key, None)
        if entry is not None:
            await _destroy_realtime(rt_key)
            log_pstn("prewarm.expired", control=entry.external_id, provider=entry.provider)


async def take_prewarm_for_answer(
    provider: str,
    external_id: str,
    *,
    fallback_external_id: str | None = None,
) -> PstnPrewarmBundle | None:
    bundle = await pstn_prewarm_registry.take(provider, external_id)
    if bundle is None and fallback_external_id:
        bundle = await pstn_prewarm_registry.take(provider, fallback_external_id)
    if bundle is None:
        return None
    # Drop stale prewarm if the agent brain was republished while the phone was ringing (9.1).
    if bundle.agent_id and bundle.compiled_brain_version:
        try:
            from server.call.call_lifecycle_service import call_lifecycle_service

            agent = await call_lifecycle_service._resolve_agent(bundle.agent_id)
            active = agent.get("active_compiled_brain_version") if isinstance(agent, dict) else None
            if active and str(active) != str(bundle.compiled_brain_version):
                log_pstn(
                    "prewarm.stale_brain",
                    control=external_id,
                    provider=provider,
                    prewarm=bundle.compiled_brain_version,
                    active=active,
                )
                await _destroy_realtime(bundle.realtime_key)
                bundle.realtime_key = None
        except Exception as exc:
            logger.warning("[PSTN] prewarm brain check failed: %s", str(exc)[:160])
    return bundle


pstn_prewarm_registry = PstnPrewarmRegistry()


async def _destroy_realtime(call_key: str) -> None:
    from server.realtime.manager import realtime_text_manager

    try:
        await realtime_text_manager.destroy(call_key)
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
    language = str(pstn_opts.get("language") or dial_meta.get("language") or "te-IN")
    agent_id = str(dial_meta.get("agent_id") or "")
    agent = await call_lifecycle_service._resolve_agent(agent_id or None)
    stack = call_lifecycle_service._coerce_pipeline_stack(
        call_lifecycle_service._resolve_locked_stack(
            session_id=config_session,
            tier=str(dial_meta.get("tier") or "medium"),
            environment=agent.get("environment") or effective_app_environment(),
            stack_override=pstn_opts.get("stack_override"),
            language=language,
        ),
        stack_override=pstn_opts.get("stack_override"),
    )
    _version, compiled = await call_lifecycle_service._lock_compiled_brain(
        agent["agent_id"],
        session_id=config_session,
    )
    wire = _PROVIDER_WIRE.get(provider, _PROVIDER_WIRE["telnyx"])
    sample_rate = int(wire["sample_rate"])
    tts_codec = str(wire["tts_output_codec"])
    greeting = extract_opening_greeting(compiled, language)

    settings = get_settings()
    from server.realtime.models import pipeline_mode

    if pipeline_mode(settings=settings, stack_override=pstn_opts.get("stack_override")) == "realtime_text":
        await realtime_text_manager.create(
            rt_key,
            compiled_brain=compiled,
            model=stack.llm.model,
            language=language,
            instructions=build_session_instructions(compiled, language=language),
            wait_ready=True,
        )
        log_pstn("prewarm.realtime.ready", control=external_id, provider=provider, model=stack.llm.model)

    frames: list[bytes] = []
    if greeting:
        frames = await _synthesize_greeting_frames(
            greeting=greeting,
            session_id=config_session,
            pseudo_call_id=rt_key,
            sample_rate=sample_rate,
            tts_output_codec=tts_codec,
            language=language,
            resolved_stack=stack,
        )

    return PstnPrewarmBundle(
        provider=provider,
        external_id=external_id,
        realtime_key=rt_key,
        greeting_text=greeting,
        greeting_wire_frames=frames,
        compiled_brain_text=compiled,
        compiled_brain_version=str(_version) if _version else None,
        language=language,
        agent_id=agent_id or None,
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
) -> list[bytes]:
    from server.services.pstn_turn_tts import PstnTurnTtsSession
    from server.services.spoken_numbers import prepare_spoken_reply

    text = prepare_spoken_reply(greeting or "").strip()
    if not text:
        return []
    stub = _PrewarmVoiceStub(
        session_id=session_id,
        call_id=pseudo_call_id,
        sample_rate=sample_rate,
        tts_output_codec=tts_output_codec,
        language=language,
    )
    session = PstnTurnTtsSession(stub)
    try:
        await session.open(language_code=language, resolved_stack=resolved_stack)
        await session.send_text(text)
        await session.finish()
        if session.had_error or not stub.frames:
            raise RuntimeError("PSTN greeting prewarm produced no usable audio")
    finally:
        await session.close()
    return list(stub.frames)


def schedule_prewarm(provider: str, external_id: str, dial_meta: dict[str, Any]) -> None:
    """Fire-and-forget prewarm on outbound dial (ring time hides Realtime + greeting TTS)."""
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
