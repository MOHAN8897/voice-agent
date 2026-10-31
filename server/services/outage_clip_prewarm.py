"""Render the outage announcement in the agent's own voice before it is needed.

The technical-failure message must play when the LLM or TTS is down, so it can
never be synthesized at the moment of failure. Instead it is rendered at call
setup (outbound: while the phone rings; inbound: right after the greeting) with
the call's TTS voice and language, and cached on disk per
(tenant, agent, language, voice, variant, text). Later calls with the same
agent/voice/language reuse the file and make no TTS request at all.

If that synthesis fails (often because the TTS provider *is* the thing that is
down) nothing is cached and the call falls back to the shipped platform clip in
a stock voice of the same gender, which exists for every supported language.
Selection order at failure time lives in ``pstn_technical_fallback``:
tenant upload > agent-voice clip from this cache > platform clip.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any

from server.utils.logger import log_pstn

#: Bump to invalidate every cached render (e.g. after changing the wording).
_CACHE_VERSION = "v1"
_CLIP_RATE = 8000
#: Generous: this runs off the call's critical path.
PREWARM_TIMEOUT_SEC = 20.0
#: After a failed render, do not hammer a TTS that is probably down.
_NEGATIVE_TTL_SEC = 600.0

_inflight: dict[str, asyncio.Task] = {}
_failed_at: dict[str, float] = {}
_BACKGROUND: set[asyncio.Task] = set()


def _cache_dir() -> Path:
    from server.config.env import get_settings

    return Path(get_settings().data_path) / "outage_clips"


def _variants() -> tuple[str, ...]:
    from server.services.pstn_technical_fallback import CALL_BACK, CALLBACK_PROMISE

    return (CALLBACK_PROMISE, CALL_BACK)


def clip_key(
    *,
    tenant_id: str | None,
    agent_id: str | None,
    language: str,
    provider: str,
    model: str,
    voice: str,
    variant: str,
) -> str:
    from server.services.pstn_technical_fallback import fallback_text, resolve_fallback_language

    resolved = resolve_fallback_language(language)
    text = fallback_text(resolved, variant)
    raw = "|".join(
        (
            _CACHE_VERSION,
            str(tenant_id or ""),
            str(agent_id or ""),
            resolved,
            provider.casefold(),
            model.casefold(),
            voice.casefold(),
            variant,
            text,
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _path_for(key: str) -> Path:
    return _cache_dir() / f"{key}.wav"


@lru_cache(maxsize=128)
def _read_wav(path: str, mtime: float) -> bytes:  # noqa: ARG001 - mtime keys the cache
    try:
        with wave.open(path, "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() != _CLIP_RATE:
                return b""
            return source.readframes(source.getnframes())
    except (OSError, EOFError, wave.Error):
        return b""


def cached_clip(key: str) -> bytes:
    path = _path_for(key)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return b""
    return _read_wav(str(path), mtime)


def _write_wav(key: str, pcm: bytes) -> None:
    path = _path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as sink:
        sink.setnchannels(1)
        sink.setsampwidth(2)
        sink.setframerate(_CLIP_RATE)
        sink.writeframes(pcm)
    tmp.replace(path)


def voice_identity(resolved_stack: Any | None, stack_override: dict[str, Any] | None = None) -> tuple[str, str, str]:
    from server.services.pstn_technical_fallback import infer_voice_identity

    return infer_voice_identity(resolved_stack=resolved_stack, stack_override=stack_override)


def agent_voice_clip(
    *,
    tenant_id: str | None,
    agent_id: str | None,
    language: str,
    variant: str,
    resolved_stack: Any | None,
    stack_override: dict[str, Any] | None = None,
) -> bytes:
    """The pre-rendered agent-voice clip for this call, or b"" when none was made."""
    provider, model, voice = voice_identity(resolved_stack, stack_override)
    if not (provider and voice):
        return b""
    return cached_clip(
        clip_key(
            tenant_id=tenant_id,
            agent_id=agent_id,
            language=language,
            provider=provider,
            model=model,
            voice=voice,
            variant=variant,
        )
    )


async def _render(text: str, *, language: str, resolved_stack: Any, pipeline: str | None) -> bytes:
    from server.services.audio_transcode import mulaw_to_pcm16
    from server.services.pstn_prewarm import _synthesize_greeting_frames

    frames, _usage = await _synthesize_greeting_frames(
        greeting=text,
        session_id=f"outage-clip-{int(time.time() * 1000)}",
        pseudo_call_id="outage-clip",
        sample_rate=_CLIP_RATE,
        tts_output_codec="mulaw",
        language=language,
        resolved_stack=resolved_stack,
        pipeline=pipeline,
    )
    return mulaw_to_pcm16(b"".join(frames), target_rate=_CLIP_RATE) if frames else b""


async def ensure_outage_clips(
    *,
    tenant_id: str | None,
    agent_id: str | None,
    language: str,
    resolved_stack: Any | None,
    pipeline: str | None = None,
    stack_override: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Make sure every outage variant is playable for this call; returns variant -> source.

    ``agent_voice`` means a cached render in the call's TTS voice exists;
    ``platform`` means the call will use the shipped stock-voice clip.
    """
    from server.services.pstn_technical_fallback import _platform_clip, resolve_voice_gender

    provider, model, voice = voice_identity(resolved_stack, stack_override)
    realtime_voice = bool((stack_override or {}).get("realtime_voice")) or pipeline == "realtime_voice"
    gender = resolve_voice_gender(provider=provider, model=model, voice_id=voice)
    out: dict[str, str] = {}
    for variant in _variants():
        # Always warm the static clip too: it is the guaranteed last resort.
        platform = _platform_clip(language, variant, gender)
        if realtime_voice or not (provider and voice) or resolved_stack is None:
            out[variant] = "platform" if platform.pcm else "none"
            continue
        key = clip_key(
            tenant_id=tenant_id,
            agent_id=agent_id,
            language=language,
            provider=provider,
            model=model,
            voice=voice,
            variant=variant,
        )
        if cached_clip(key):
            out[variant] = "agent_voice"
            continue
        failed = _failed_at.get(key)
        if failed is not None and time.monotonic() - failed < _NEGATIVE_TTL_SEC:
            out[variant] = "platform" if platform.pcm else "none"
            continue
        task = _inflight.get(key)
        if task is None or task.done():
            from server.services.pstn_technical_fallback import fallback_text

            task = asyncio.ensure_future(
                _render(fallback_text(language, variant), language=language, resolved_stack=resolved_stack, pipeline=pipeline)
            )
            _inflight[key] = task
        try:
            pcm = await asyncio.shield(task)
        except Exception as exc:
            pcm = b""
            log_pstn("outage_clip.render_failed", variant=variant, language=language, provider=provider, error_type=type(exc).__name__)
        finally:
            if _inflight.get(key) is task and task.done():
                _inflight.pop(key, None)
        if pcm:
            try:
                await asyncio.to_thread(_write_wav, key, pcm)
                _failed_at.pop(key, None)
                out[variant] = "agent_voice"
                continue
            except OSError as exc:
                log_pstn("outage_clip.write_failed", variant=variant, error_type=type(exc).__name__)
        _failed_at[key] = time.monotonic()
        out[variant] = "platform" if platform.pcm else "none"
    log_pstn("outage_clip.ready", language=language, provider=provider, sources=out)
    return out


def schedule_outage_clip_prewarm(
    *,
    tenant_id: str | None,
    agent_id: str | None,
    language: str,
    resolved_stack: Any | None,
    pipeline: str | None = None,
    stack_override: dict[str, Any] | None = None,
    call_id: str | None = None,
) -> asyncio.Task | None:
    """Fire-and-forget render; never blocks or fails the call that started it."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    async def _run() -> None:
        try:
            sources = await asyncio.wait_for(
                ensure_outage_clips(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    language=language,
                    resolved_stack=resolved_stack,
                    pipeline=pipeline,
                    stack_override=stack_override,
                ),
                timeout=PREWARM_TIMEOUT_SEC,
            )
        except Exception as exc:
            log_pstn("outage_clip.prewarm_failed", call_id=call_id, error_type=type(exc).__name__)
            return
        # Logged, not written to call meta: a background read-modify-write of
        # meta.json could clobber a concurrent write (e.g. an opt-out).
        log_pstn("outage_clip.prewarmed", call_id=call_id, language=language, sources=sources)

    task = loop.create_task(_run(), name="outage-clip-prewarm")
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)
    return task
