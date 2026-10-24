"""Tenant fallback clips: WAV validation, normalization, and scoped storage."""
from __future__ import annotations

import io
import re
import sys
import uuid
import wave
from array import array
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.entities import Agent, AgentFallbackClip
from server.services.audio_transcode import pcm_resample
from server.services.pstn_technical_fallback import CLIP_VARIANTS, _CLIP_RATE

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_CLIP_SEC = 30.0
MIN_CLIP_SEC = 0.2
_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-zA-Z]{2,4})?$")


class FallbackClipError(ValueError):
    status_code = 400
    code = "invalid_fallback_clip"


def normalize_language(value: str | None) -> str:
    return str(value or "").strip().replace("_", "-")


def validate_language(value: str | None) -> str:
    language = normalize_language(value)
    if not _LANGUAGE_RE.fullmatch(language):
        raise FallbackClipError("Choose a valid language code for the clip.")
    return language


def validate_variant(value: str | None) -> str:
    variant = str(value or "").strip().lower()
    if variant not in CLIP_VARIANTS:
        raise FallbackClipError("Choose a supported announcement variant.")
    return variant


def _downmix_stereo(frames: bytes) -> bytes:
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    mono = array("h", ((samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)))
    if sys.byteorder == "big":
        mono.byteswap()
    return mono.tobytes()


def normalize_wav(raw: bytes) -> tuple[bytes, int]:
    """Return (mono 8 kHz PCM16, duration_ms) or raise a clear validation error."""
    if not raw:
        raise FallbackClipError("The audio file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise FallbackClipError("The audio file must be 2 MB or smaller.")
    try:
        with wave.open(io.BytesIO(raw), "rb") as source:
            channels = source.getnchannels()
            width = source.getsampwidth()
            rate = source.getframerate()
            frames = source.readframes(source.getnframes())
    except (wave.Error, EOFError) as exc:
        raise FallbackClipError("Upload a valid WAV audio file.") from exc
    if width != 2:
        raise FallbackClipError("The audio must be 16-bit PCM WAV.")
    if channels not in (1, 2) or not frames or rate <= 0:
        raise FallbackClipError("The audio must be mono or stereo WAV.")
    if channels == 2:
        frames = _downmix_stereo(frames)
    if rate != _CLIP_RATE:
        frames = pcm_resample(frames, rate, _CLIP_RATE)
    duration_sec = len(frames) / 2 / _CLIP_RATE
    if duration_sec < MIN_CLIP_SEC:
        raise FallbackClipError("The recording is too short to be an announcement.")
    if duration_sec > MAX_CLIP_SEC:
        raise FallbackClipError("Keep the recording under 30 seconds.")
    return frames, int(round(duration_sec * 1000))


def _meta(row: AgentFallbackClip) -> dict[str, Any]:
    updated = row.updated_at or row.created_at
    return {
        "language": row.language,
        "variant": row.variant,
        "source": "custom",
        "durationMs": int(row.duration_ms or 0),
        "updatedAt": updated.isoformat() if isinstance(updated, datetime) else None,
    }


async def _owned_agent(session, tenant_id: str, agent_id: str) -> Agent | None:
    result = await session.execute(
        select(Agent).where(
            Agent.agent_id == uuid.UUID(agent_id),
            Agent.tenant_id == uuid.UUID(tenant_id),
        )
    )
    return result.scalar_one_or_none()


def _factory_or_error():
    factory = get_session_factory()
    if factory is None:
        raise FallbackClipError("Fallback clips require durable database storage.")
    return factory


def _tenant_uuid(value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise FallbackClipError("A tenant is required to manage fallback clips.") from exc


async def list_clips(*, tenant_id: str | None, agent_id: str) -> list[dict[str, Any]]:
    factory = _factory_or_error()
    tenant_uuid = _tenant_uuid(tenant_id)
    agent_uuid = uuid.UUID(agent_id)
    async with factory() as session:
        if await _owned_agent(session, str(tenant_uuid), str(agent_uuid)) is None:
            raise KeyError(agent_id)
        rows = await session.execute(
            select(AgentFallbackClip)
            .where(
                AgentFallbackClip.tenant_id == tenant_uuid,
                AgentFallbackClip.agent_id == agent_uuid,
            )
            .order_by(AgentFallbackClip.language, AgentFallbackClip.variant)
        )
        return [_meta(row) for row in rows.scalars().all()]


async def upsert_clip(
    *,
    tenant_id: str | None,
    agent_id: str,
    language: str,
    variant: str,
    raw: bytes,
) -> dict[str, Any]:
    language = validate_language(language)
    variant = validate_variant(variant)
    pcm, duration_ms = normalize_wav(raw)
    factory = _factory_or_error()
    tenant_uuid = _tenant_uuid(tenant_id)
    agent_uuid = uuid.UUID(agent_id)
    async with factory() as session:
        if await _owned_agent(session, str(tenant_uuid), str(agent_uuid)) is None:
            raise KeyError(agent_id)
        result = await session.execute(
            select(AgentFallbackClip).where(
                AgentFallbackClip.tenant_id == tenant_uuid,
                AgentFallbackClip.agent_id == agent_uuid,
                AgentFallbackClip.language == language,
                AgentFallbackClip.variant == variant,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = AgentFallbackClip(
                tenant_id=tenant_uuid,
                agent_id=agent_uuid,
                language=language,
                variant=variant,
                pcm_bytes=pcm,
                sample_rate=_CLIP_RATE,
                duration_ms=duration_ms,
            )
            session.add(row)
        else:
            row.pcm_bytes = pcm
            row.sample_rate = _CLIP_RATE
            row.duration_ms = duration_ms
            row.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(row)
        return _meta(row)


async def delete_clip(
    *,
    tenant_id: str | None,
    agent_id: str,
    language: str,
    variant: str,
) -> None:
    language = validate_language(language)
    variant = validate_variant(variant)
    factory = _factory_or_error()
    tenant_uuid = _tenant_uuid(tenant_id)
    agent_uuid = uuid.UUID(agent_id)
    async with factory() as session:
        if await _owned_agent(session, str(tenant_uuid), str(agent_uuid)) is None:
            raise KeyError(agent_id)
        result = await session.execute(
            select(AgentFallbackClip).where(
                AgentFallbackClip.tenant_id == tenant_uuid,
                AgentFallbackClip.agent_id == agent_uuid,
                AgentFallbackClip.language == language,
                AgentFallbackClip.variant == variant,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise KeyError(f"{language}/{variant}")
        await session.delete(row)
        await session.commit()
