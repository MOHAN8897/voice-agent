"""
Tier assignment persistence — server/db/tier_store.py
DB is authoritative for L1 when VOICE_AGENT_CONFIG_MODE=env (per environment+tier).
"""
from __future__ import annotations

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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_cached_tier_stack(environment: str, tier: str) -> StackSelection | None:
    """Sync read for StackResolver — populated by load_tier_cache / upsert."""
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
    count = 0
    async with factory() as session:
        result = await session.execute(select(TierAssignment))
        for row in result.scalars().all():
            if row.stack_payload:
                _cache_put(row.environment, row.tier, row.stack_payload)
                count += 1
    return count


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
            row.combination_id = combination_id
            row.stack_payload = stack_payload
            row.updated_at = _utcnow()
        await session.commit()
    _cache_put(environment, tier, stack_payload)


async def sync_tier_assignments_from_env(environment: str | None = None) -> int:
    """Upsert tier_assignments from env bundles (bootstrap / rollback)."""
    factory = get_session_factory()
    if factory is None:
        return 0

    settings = get_settings()
    env = environment or settings.app_environment
    registry = get_provider_registry()
    resolver = StackResolver(settings, registry)
    count = 0

    for tier in constants.TIER_NAMES:
        resolved = resolver.resolve(mode="env", tier=tier, environment=env)  # type: ignore[arg-type]
        await upsert_tier_assignment(env, tier, resolved.combination_id, resolved.to_safe_dict())
        count += 1
    return count


async def promote_tier_assignments(source_environment: str, target_environment: str, *, actor: str | None = None) -> int:
    """Copy tier rows (combination_id + stack_payload) from source env to target."""
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
    _TIER_CACHE.clear()
