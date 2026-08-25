"""
Compiled brain service — sole L2 writer (Phase 2).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from server.agent.brain_prompt_composer import estimate_tokens
from server.brain.business_brain_store import assemble_raw_business_prompt, business_brain_store
from server.brain.business_prompt_optimizer import optimize_business_prompt
from server.brain.platform_brain_store import platform_brain_store
from server.brain.sections import STATIC_OUTPUT_RULES, STATIC_OUTPUT_RULES_VERSION
from server.brain.semantic_validation import validate_sections
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.brain_models import CompiledBrainSnapshot
from server.db.models.entities import Agent

_COMPILED_CACHE: dict[str, dict[str, Any]] = {}
_AGENT_ACTIVE: dict[str, str] = {}
_DEFAULT_AGENT_ID: str | None = None


class CompiledBrainService:
    async def compile_for_agent(self, agent_id: str, *, business_version_id: str | None = None) -> dict[str, Any]:
        platform = await platform_brain_store.get_active()
        sections = await business_brain_store.ensure_default_sections(agent_id)
        raw_prompt, source_checksum = assemble_raw_business_prompt(sections)

        latest = await business_brain_store.get_latest_published(agent_id)
        if (
            latest
            and business_version_id is None
            and latest.get("source_checksum") == source_checksum
        ):
            optimized_text = latest["optimized_prompt"]
            business_version = latest["version_id"]
        else:
            opt = await optimize_business_prompt(raw_prompt, source_checksum=source_checksum)
            published = await business_brain_store.save_published_version(
                agent_id,
                optimized_prompt=opt.optimized_business_prompt,
                source_checksum=source_checksum,
                optimizer_report=opt.to_dict(),
            )
            optimized_text = published["optimized_prompt"]
            business_version = published["version_id"]

        compiled_text = f"{platform['body']}\n\n{optimized_text}\n\n{STATIC_OUTPUT_RULES}"
        checksum = hashlib.sha256(compiled_text.encode("utf-8")).hexdigest()
        compiled_version = f"cb_v{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        token_estimate = estimate_tokens(compiled_text)

        snapshot = {
            "compiled_version": compiled_version,
            "platform_version": platform["version_id"],
            "business_version": business_version,
            "static_rules_version": STATIC_OUTPUT_RULES_VERSION,
            "compiled_text": compiled_text,
            "checksum": checksum,
            "token_estimate": token_estimate,
            "compiled_at": datetime.now(timezone.utc).isoformat(),
        }

        factory = get_session_factory()
        if factory is None:
            _COMPILED_CACHE[compiled_version] = snapshot
            _AGENT_ACTIVE[agent_id] = compiled_version
        else:
            async with factory() as session:
                session.add(
                    CompiledBrainSnapshot(
                        compiled_version=compiled_version,
                        platform_version=snapshot["platform_version"],
                        business_version=snapshot["business_version"],
                        static_rules_version=snapshot["static_rules_version"],
                        compiled_text=compiled_text,
                        checksum=checksum,
                        token_estimate=token_estimate,
                    )
                )
                await session.execute(
                    update(Agent)
                    .where(Agent.agent_id == uuid.UUID(agent_id))
                    .values(active_compiled_brain_version=compiled_version)
                )
                await session.commit()

        _COMPILED_CACHE[compiled_version] = snapshot
        _AGENT_ACTIVE[agent_id] = compiled_version
        return snapshot

    async def publish_agent_brain(self, agent_id: str) -> dict[str, Any]:
        sections = await business_brain_store.get_sections(agent_id)
        validation = validate_sections(sections)
        if not validation.ok:
            from server.utils.errors import AppError, ErrorCode

            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="Business brain has blocking validation issues",
                status_code=400,
            )

        settings = get_settings()
        if not settings.allow_publish_during_calls and _count_active_calls(agent_id) > 0:
            from server.utils.errors import AppError, ErrorCode

            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="Publish blocked while active calls exist on this agent",
                status_code=409,
            )

        raw_prompt, source_checksum = assemble_raw_business_prompt(sections)
        previous = await business_brain_store.get_latest_published(agent_id)
        opt = await optimize_business_prompt(
            raw_prompt,
            source_checksum=source_checksum,
            previous_optimized=previous["optimized_prompt"] if previous else None,
        )
        blocking = [c for c in opt.conflicts if c.get("severity") == "blocking"]
        if blocking:
            from server.utils.errors import AppError, ErrorCode

            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="Optimizer reported blocking conflicts",
                status_code=400,
            )

        await business_brain_store.save_published_version(
            agent_id,
            optimized_prompt=opt.optimized_business_prompt,
            source_checksum=source_checksum,
            optimizer_report=opt.to_dict(),
        )
        return await self.compile_for_agent(agent_id)

    async def get_active_for_agent(self, agent_id: str) -> dict[str, Any]:
        version_id = _AGENT_ACTIVE.get(agent_id)
        if version_id and version_id in _COMPILED_CACHE:
            return _COMPILED_CACHE[version_id]

        factory = get_session_factory()
        if factory is not None:
            async with factory() as session:
                result = await session.execute(select(Agent).where(Agent.agent_id == uuid.UUID(agent_id)))
                agent = result.scalar_one_or_none()
                if agent and agent.active_compiled_brain_version:
                    snap = await self.get_snapshot(agent.active_compiled_brain_version)
                    _AGENT_ACTIVE[agent_id] = snap["compiled_version"]
                    return snap

        # Bootstrap compile on first access
        await platform_brain_store.ensure_seed()
        await business_brain_store.ensure_default_sections(agent_id)
        return await self.compile_for_agent(agent_id)

    async def get_snapshot(self, compiled_version: str) -> dict[str, Any]:
        if compiled_version in _COMPILED_CACHE:
            return _COMPILED_CACHE[compiled_version]

        factory = get_session_factory()
        if factory is None:
            raise KeyError(compiled_version)

        async with factory() as session:
            result = await session.execute(
                select(CompiledBrainSnapshot).where(CompiledBrainSnapshot.compiled_version == compiled_version)
            )
            row = result.scalar_one_or_none()
            if not row:
                raise KeyError(compiled_version)
            snap = {
                "compiled_version": row.compiled_version,
                "platform_version": row.platform_version,
                "business_version": row.business_version,
                "static_rules_version": row.static_rules_version,
                "compiled_text": row.compiled_text,
                "checksum": row.checksum,
                "token_estimate": row.token_estimate,
                "compiled_at": row.compiled_at.isoformat(),
            }
            _COMPILED_CACHE[compiled_version] = snap
            return snap

    def redacted_preview(self, compiled_text: str) -> str:
        return compiled_text[:400] + ("..." if len(compiled_text) > 400 else "")


def _count_active_calls(agent_id: str) -> int:
    from server.call.call_context import count_active_for_agent

    return count_active_for_agent(agent_id)


compiled_brain_service = CompiledBrainService()


def get_cached_compiled_brain(agent_id: str | None = None) -> dict[str, Any] | None:
    """Return warmed compiled brain snapshot for live path (sync)."""
    aid = agent_id or _DEFAULT_AGENT_ID
    if not aid:
        return None
    version_id = _AGENT_ACTIVE.get(aid)
    if version_id and version_id in _COMPILED_CACHE:
        return _COMPILED_CACHE[version_id]
    return None


async def warmup_versioned_brains() -> None:
    global _DEFAULT_AGENT_ID
    from server.brain.agent_service import agent_service

    _DEFAULT_AGENT_ID = await agent_service.resolve_default_agent_id()
    await platform_brain_store.ensure_seed()
    await business_brain_store.ensure_default_sections(_DEFAULT_AGENT_ID)
    await compiled_brain_service.get_active_for_agent(_DEFAULT_AGENT_ID)
