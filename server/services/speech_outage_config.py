"""Platform-wide speech-outage announcement settings.

One switch decides whether a call that loses its TTS/LLM hears the recorded
apology. Per-agent clips and language choices stay on the agent row, but the
platform switch is authoritative: when it is off no caller hears the clip.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select

from server.db.connection import get_session_factory
from server.db.models.entities import ConfigVersion

_RESOURCE_TYPE = "speech_outage"
_RESOURCE_ID = "global"
_CACHE_TTL_SEC = 5.0
_WRITE_LOCK = asyncio.Lock()
_cache: tuple[float, "SpeechOutageConfig"] | None = None


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    if value is None:
        return default
    return bool(value)


@dataclass(frozen=True)
class SpeechOutageConfig:
    enabled: bool = True
    promise_callback: bool = True
    version: int = 0
    updated_at: str | None = None
    updated_by: str | None = None

    def to_api(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "promiseCallback": self.promise_callback,
            "version": self.version,
            "updatedAt": self.updated_at,
            "updatedBy": self.updated_by,
        }


def _from_row(row: ConfigVersion) -> SpeechOutageConfig:
    payload = row.payload or {}
    return SpeechOutageConfig(
        enabled=_as_bool(payload.get("enabled"), True),
        promise_callback=_as_bool(payload.get("promiseCallback"), True),
        version=int(row.version or 0),
        updated_at=payload.get("updatedAt")
        or (row.created_at.isoformat() if row.created_at else None),
        updated_by=payload.get("updatedBy"),
    )


async def load_speech_outage_config(*, force: bool = False) -> SpeechOutageConfig:
    """Read the platform switch; defaults keep announcements on if the DB fails."""
    global _cache
    now = time.monotonic()
    if not force and _cache is not None and now - _cache[0] < _CACHE_TTL_SEC:
        return _cache[1]
    config = SpeechOutageConfig()
    factory = get_session_factory()
    if factory is not None:
        try:
            async with factory() as session:
                result = await session.execute(
                    select(ConfigVersion)
                    .where(
                        ConfigVersion.resource_type == _RESOURCE_TYPE,
                        ConfigVersion.resource_id == _RESOURCE_ID,
                    )
                    .order_by(desc(ConfigVersion.version), desc(ConfigVersion.created_at))
                    .limit(1)
                )
                row = result.scalar_one_or_none()
                if row is not None:
                    config = _from_row(row)
        except Exception:
            config = SpeechOutageConfig()
    _cache = (now, config)
    return config


async def save_speech_outage_config(
    *,
    enabled: bool,
    promise_callback: bool,
    actor: str | None,
) -> SpeechOutageConfig:
    global _cache
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Speech outage settings require durable storage")
    async with _WRITE_LOCK:
        async with factory() as session:
            result = await session.execute(
                select(ConfigVersion)
                .where(
                    ConfigVersion.resource_type == _RESOURCE_TYPE,
                    ConfigVersion.resource_id == _RESOURCE_ID,
                )
                .order_by(desc(ConfigVersion.version), desc(ConfigVersion.created_at))
                .limit(1)
                .with_for_update()
            )
            latest = result.scalar_one_or_none()
            version = int(latest.version or 0) + 1 if latest is not None else 1
            row = ConfigVersion(
                resource_type=_RESOURCE_TYPE,
                resource_id=_RESOURCE_ID,
                version=version,
                payload={
                    "enabled": bool(enabled),
                    "promiseCallback": bool(promise_callback),
                    "updatedAt": datetime.now(timezone.utc).isoformat(),
                    "updatedBy": actor,
                },
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            config = _from_row(row)
    _cache = (time.monotonic(), config)
    return config
