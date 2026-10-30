"""
Tier assignment persistence — server/db/tier_store.py
DB is authoritative for L1 when VOICE_AGENT_CONFIG_MODE=env (per environment+tier).
"""
from __future__ import annotations

import asyncio
import copy
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from server.config.constants import constants
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.entities import ConfigVersion, TierAssignment
from server.providers.base import StackSelection, StageSelection
from server.providers.registry import get_provider_registry
from server.providers.resolver import StackResolver

# In-memory cache: environment -> tier -> resolved safe dict (from stack_payload)
_TIER_CACHE: dict[str, dict[str, dict[str, Any]]] = {}
# API, voice and worker processes each keep their own cache and only the saving
# process updates it directly. Reads older than this TTL trigger a background
# reload so admin changes reach every process without a restart.
TIER_CACHE_TTL_S = 30.0
_TIER_CACHE_LOADED_AT = 0.0
_REFRESH_TASK: Any = None


def _schedule_refresh_if_stale() -> None:
    global _REFRESH_TASK
    if time.monotonic() - _TIER_CACHE_LOADED_AT < TIER_CACHE_TTL_S:
        return
    if _REFRESH_TASK is not None and not _REFRESH_TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if get_session_factory() is None:
        return

    async def _refresh() -> None:
        try:
            await load_tier_cache()
        except Exception:
            pass

    _REFRESH_TASK = loop.create_task(_refresh())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_cached_tier_stack(environment: str, tier: str) -> StackSelection | None:
    """Sync read for StackResolver — populated by load_tier_cache / upsert."""
    _schedule_refresh_if_stale()
    payload = _TIER_CACHE.get(environment, {}).get(tier)
    if not payload or not isinstance(payload, dict):
        return None
    try:
        stt = payload.get("stt") or {}
        llm = payload.get("llm") or {}
        tts = payload.get("tts") or {}
        return StackSelection(
            stt=StageSelection(stt.get("provider", ""), stt.get("model", ""), stt.get("config") or {}),
            llm=StageSelection(llm.get("provider", ""), llm.get("model", ""), llm.get("config") or {}),
            tts=StageSelection(tts.get("provider", ""), tts.get("model", ""), tts.get("config") or {}),
            language=payload.get("language") or "te-IN",
            voice_preset=payload.get("voice_preset"),
        )
    except Exception:
        return None


def _cache_put(environment: str, tier: str, resolved_safe: dict[str, Any]) -> None:
    if environment not in _TIER_CACHE:
        _TIER_CACHE[environment] = {}
    _TIER_CACHE[environment][tier] = resolved_safe


async def load_tier_cache() -> int:
    """Load all tier_assignments into memory cache."""
    factory = get_session_factory()
    if factory is None:
        return 0
    global _TIER_CACHE_LOADED_AT
    count = 0
    fresh: dict[str, dict[str, dict[str, Any]]] = {}
    async with factory() as session:
        result = await session.execute(select(TierAssignment))
        for row in result.scalars().all():
            if row.stack_payload:
                fresh.setdefault(row.environment, {})[row.tier] = row.stack_payload
                count += 1
    # Replace wholesale so tiers deleted in another process disappear here too.
    _TIER_CACHE.clear()
    _TIER_CACHE.update(fresh)
    _TIER_CACHE_LOADED_AT = time.monotonic()
    return count


def _merge_preserving_profile(existing: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    """Stage-only writers must never delete the composed voice profile.

    When a composed profile exists it stays authoritative: it is kept, and the
    legacy stage keys are re-derived from it so both views describe one runtime.
    """
    merged = copy.deepcopy(incoming) if isinstance(incoming, dict) else {}
    if not isinstance(existing, dict):
        return merged
    record = existing.get("composed_voice_profile")
    if isinstance(record, dict) and "composed_voice_profile" not in merged:
        merged["composed_voice_profile"] = copy.deepcopy(record)
        profile = record.get("profile")
        if isinstance(profile, dict) and profile.get("engines"):
            try:
                from server.services.saas.voice_stack_profiles import mirror_stage_payload

                merged.update(mirror_stage_payload(profile, existing))
            except Exception:
                pass
    return merged


async def upsert_tier_assignment(
    environment: str,
    tier: str,
    combination_id: str,
    stack_payload: dict[str, Any],
    *,
    actor: str | None = None,
) -> None:
    factory = get_session_factory()
    if factory is None:
        _cache_put(environment, tier, stack_payload)
        return

    async with factory() as session:
        result = await session.execute(
            select(TierAssignment).where(
                TierAssignment.environment == environment,
                TierAssignment.tier == tier,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = TierAssignment(
                id=uuid.uuid4(),
                environment=environment,
                tier=tier,
                combination_id=combination_id,
                stack_payload=stack_payload,
            )
            session.add(row)
        else:
            if row.combination_id != combination_id:
                session.add(
                    ConfigVersion(
                        id=uuid.uuid4(),
                        resource_type="tier_assignment",
                        resource_id=f"{environment}:{tier}",
                        version=1,
                        payload={
                            "previous_combination_id": row.combination_id,
                            "combination_id": combination_id,
                            "resolved": stack_payload,
                            "actor": actor,
                        },
                        created_at=_utcnow(),
                    )
                )
            stack_payload = _merge_preserving_profile(row.stack_payload, stack_payload)
            row.combination_id = combination_id
            row.stack_payload = stack_payload
            row.updated_at = _utcnow()
        await session.commit()
    _cache_put(environment, tier, stack_payload)


async def sync_tier_assignments_from_env(environment: str | None = None, *, force: bool = False) -> int:
    """Upsert tier_assignments from env bundles (bootstrap / rollback).

    When force=False (default during server startup), existing tier assignments
    in the database are preserved and only missing tiers are seeded.
    """
    factory = get_session_factory()
    if factory is None:
        return 0

    settings = get_settings()
    env = environment or settings.app_environment
    registry = get_provider_registry()
    resolver = StackResolver(settings, registry)
    count = 0

    existing_tiers: set[str] = set()
    if not force:
        try:
            async with factory() as session:
                result = await session.execute(
                    select(TierAssignment.tier).where(TierAssignment.environment == env)
                )
                existing_tiers = set(result.scalars().all())
        except Exception:
            existing_tiers = set()

    for tier in constants.TIER_NAMES:
        if not force and tier in existing_tiers:
            continue
        resolved = resolver.resolve(mode="env", tier=tier, environment=env)  # type: ignore[arg-type]
        await upsert_tier_assignment(env, tier, resolved.combination_id, resolved.to_safe_dict())
        count += 1
    return count


async def promote_tier_assignments(
    source_environment: str,
    target_environment: str,
    *,
    actor: str | None = None,
    snapshot: list[dict[str, Any]] | None = None,
) -> int:
    """Copy tier rows (combination_id + stack_payload) from source env to target.

    When ``snapshot`` is given, the target's prior state of every touched tier is
    appended to it (``stack_payload`` None when the tier did not exist) so the
    promotion can be rolled back exactly with ``restore_tier_assignments``.
    """
    factory = get_session_factory()
    if factory is None:
        return 0

    count = 0
    async with factory() as session:
        result = await session.execute(
            select(TierAssignment).where(TierAssignment.environment == source_environment)
        )
        rows = list(result.scalars().all())
        for src in rows:
            target_result = await session.execute(
                select(TierAssignment).where(
                    TierAssignment.environment == target_environment,
                    TierAssignment.tier == src.tier,
                )
            )
            target = target_result.scalar_one_or_none()
            if snapshot is not None:
                snapshot.append({
                    "tier": src.tier,
                    "combination_id": target.combination_id if target is not None else None,
                    "stack_payload": copy.deepcopy(target.stack_payload) if target is not None else None,
                })
            payload = src.stack_payload or {}
            if target is None:
                target = TierAssignment(
                    id=uuid.uuid4(),
                    environment=target_environment,
                    tier=src.tier,
                    combination_id=src.combination_id,
                    stack_payload=payload,
                )
                session.add(target)
            else:
                target.combination_id = src.combination_id
                target.stack_payload = payload
                target.updated_at = _utcnow()
            session.add(
                ConfigVersion(
                    id=uuid.uuid4(),
                    resource_type="promotion",
                    resource_id=f"{source_environment}->{target_environment}:{src.tier}",
                    version=1,
                    payload={
                        "source_environment": source_environment,
                        "target_environment": target_environment,
                        "tier": src.tier,
                        "combination_id": src.combination_id,
                        "actor": actor,
                    },
                    created_at=_utcnow(),
                )
            )
            _cache_put(target_environment, src.tier, payload)
            count += 1
        await session.commit()
    return count


async def restore_tier_assignments(
    environment: str, rows: list[dict[str, Any]], *, actor: str | None = None,
) -> int:
    """Put tier rows back exactly as captured by a promotion snapshot."""
    factory = get_session_factory()
    if factory is None:
        return 0
    restored = 0
    async with factory() as session:
        for item in rows:
            tier = str(item.get("tier") or "")
            if not tier:
                continue
            result = await session.execute(
                select(TierAssignment).where(
                    TierAssignment.environment == environment,
                    TierAssignment.tier == tier,
                ).with_for_update()
            )
            row = result.scalar_one_or_none()
            payload = item.get("stack_payload")
            if payload is None:
                if row is not None:
                    await session.delete(row)
                _TIER_CACHE.get(environment, {}).pop(tier, None)
            else:
                if row is None:
                    row = TierAssignment(
                        id=uuid.uuid4(), environment=environment, tier=tier,
                        combination_id=str(item.get("combination_id") or uuid.uuid4().hex[:16]),
                        stack_payload=payload,
                    )
                    session.add(row)
                else:
                    row.combination_id = str(item.get("combination_id") or row.combination_id)
                    row.stack_payload = payload
                    row.updated_at = _utcnow()
                _cache_put(environment, tier, payload)
            session.add(ConfigVersion(
                id=uuid.uuid4(), resource_type="tier_assignment_restore",
                resource_id=f"{environment}:{tier}", version=1,
                payload={"actor": actor, "restored": payload is not None}, created_at=_utcnow(),
            ))
            restored += 1
        await session.commit()
    try:
        from server.services.saas.voice_stack_profiles import invalidate_profile_caches

        invalidate_profile_caches(None)
    except Exception:
        pass
    return restored


async def get_tier_combination_id(environment: str, tier: str) -> str | None:
    factory = get_session_factory()
    if factory is None:
        return None
    async with factory() as session:
        result = await session.execute(
            select(TierAssignment.combination_id).where(
                TierAssignment.environment == environment,
                TierAssignment.tier == tier,
            )
        )
        return result.scalar_one_or_none()


def clear_tier_cache_for_tests() -> None:
    global _TIER_CACHE_LOADED_AT
    _TIER_CACHE.clear()
    _TIER_CACHE_LOADED_AT = 0.0
