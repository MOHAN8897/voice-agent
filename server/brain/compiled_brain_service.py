"""
Compiled brain service — sole L2 writer (Phase 2).
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from server.agent.brain_prompt_composer import estimate_tokens
from server.brain.business_brain_store import (
    assemble_raw_business_prompt,
    business_brain_store,
    draft_revision,
)
from server.brain.business_prompt_optimizer import optimize_business_prompt
from server.brain.compiled_brain_artifact import (
    assemble_unified_brain,
    checksum_instructions,
    is_unified_compiled_brain,
    platform_body_for_agent_language,
)
from server.brain.platform_brain_store import platform_brain_store
from server.brain.sections import STATIC_OUTPUT_RULES_VERSION
from server.brain.semantic_validation import validate_sections
from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.brain_models import CompiledBrainSnapshot
from server.db.models.entities import Agent
from server.prompts.agent_voice_rules import normalize_compile_language
from server.utils.errors import AppError, ErrorCode

_COMPILED_CACHE: dict[str, dict[str, Any]] = {}
_AGENT_ACTIVE: dict[str, str] = {}
_DEFAULT_AGENT_ID: str | None = None


class CompiledBrainService:
    def _reject_contradictory_brain(self, compiled_text: str, language: str, *, agent_id: str, status_code: int) -> None:
        from server.brain.brain_prompt_validate import validate_rendered_brain
        from server.utils.logger import logger

        issues = validate_rendered_brain(compiled_text, language)
        if not issues:
            return
        logger.error(
            "[BRAIN] Rejected contradictory instructions for agent %s (lang=%s): %s",
            agent_id,
            language,
            "; ".join(issues),
        )
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            message="The agent instructions contain conflicting platform rules: " + "; ".join(issues[:3]),
            status_code=status_code,
        )

    async def _agent_info(self, agent_id: str) -> tuple[str, bool, str | None]:
        factory = get_session_factory()
        if factory is None:
            from server.brain.agent_service import agent_service
            try:
                row = await agent_service.get_agent(agent_id)
            except (KeyError, ValueError):
                return "te-IN", False, None
            languages = row.get("languages") or ["te-IN"]
            return normalize_compile_language(languages[0]), bool(row.get("recording_disclosure_enabled")), row.get("recording_disclosure_text")
        async with factory() as session:
            try:
                row = await session.get(Agent, uuid.UUID(agent_id))
            except (ValueError, TypeError):
                return "te-IN", False, None
            if row:
                lang = normalize_compile_language(row.languages[0]) if row.languages else "te-IN"
                disclosure_enabled = bool(getattr(row, "recording_disclosure_enabled", False))
                disclosure_text = getattr(row, "recording_disclosure_text", None)
                return lang, disclosure_enabled, disclosure_text
        return "te-IN", False, None

    async def _primary_language(self, agent_id: str) -> str:
        lang, _, _ = await self._agent_info(agent_id)
        return lang

    async def compile_for_agent(self, agent_id: str, *, business_version_id: str | None = None) -> dict[str, Any]:
        platform = await platform_brain_store.get_active()
        lang, disclosure_enabled, disclosure_text = await self._agent_info(agent_id)
        sections = await business_brain_store.ensure_default_sections(agent_id)
        raw_prompt, source_checksum = assemble_raw_business_prompt(sections)

        latest = await business_brain_store.get_latest_published(agent_id)
        if business_version_id is not None:
            latest = next((row for row in await business_brain_store.get_versions(agent_id) if row["version_id"] == business_version_id), None)
            if latest is None:
                raise KeyError(business_version_id)
        if latest:
            optimized_text = latest["optimized_prompt"]
            business_version = latest["version_id"]
        else:
            opt = await optimize_business_prompt(raw_prompt, source_checksum=source_checksum, preserve_source=True)
            published = await business_brain_store.save_published_version(
                agent_id,
                optimized_prompt=opt.optimized_business_prompt,
                source_checksum=source_checksum,
                optimizer_report=opt.to_dict(),
            )
            optimized_text = published["optimized_prompt"]
            business_version = published["version_id"]

        # The create flow historically stored a full platform assembly as the
        # published business text. Rewrapping it duplicates packs and policies.
        exact_artifact = bool(latest and (latest.get("optimizer_report") or {}).get("compiled_artifact_checksum") == checksum_instructions(optimized_text))
        if is_unified_compiled_brain(optimized_text) and not exact_artifact:
            if latest and latest.get("source_checksum") == source_checksum:
                optimized_text = raw_prompt
            else:
                # A restart/recompile must not publish newer, unapproved draft
                # edits. Legacy versions saved their approved script in the report.
                report = (latest or {}).get("optimizer_report") or {}
                approved_script = report.get("agent_script")
                if approved_script:
                    optimized_text = approved_script
                else:
                    from server.brain.compiled_brain_artifact import business_from_unified_brain
                    optimized_text = business_from_unified_brain(optimized_text)

        platform_rules = platform_body_for_agent_language(platform["body"], lang)
        compiled_text = optimized_text if exact_artifact else assemble_unified_brain(
            language=lang,
            script=optimized_text,
            platform_call_rules=platform_rules,
        )
        # Exact artifacts bypass platform assembly; apply the disclosure to both
        # shapes so toggling it always reaches the compiled snapshot a call uses.
        from server.prompts.agent_voice_rules import inject_recording_disclosure

        compiled_text = inject_recording_disclosure(
            compiled_text,
            enabled=disclosure_enabled,
            disclosure_text=disclosure_text,
            language=lang,
        )
        self._reject_contradictory_brain(compiled_text, lang, agent_id=agent_id, status_code=409)
        checksum = checksum_instructions(compiled_text)
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

    async def validate_publication(self, agent_id: str, sections: list[dict[str, Any]], optimizer_report: dict[str, Any] | None = None) -> None:
        validation = validate_sections(sections)
        if not validation.ok:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="Business brain has blocking validation issues",
                status_code=400,
            )
        from server.brain.brief_contract import validate_brief_requirements
        lang = await self._primary_language(agent_id)
        for section in sections:
            source = str(section.get("raw_text") or "")
            if section.get("enabled", True) and source.strip():
                issues = validate_brief_requirements(source, language=lang)
                if issues:
                    raise AppError(ErrorCode.VALIDATION_ERROR, "Resolve unsafe or conflicting script instructions before publishing.", status_code=422)

        settings = get_settings()
        if not settings.allow_publish_during_calls and _count_active_calls(agent_id) > 0:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                message="Publish blocked while active calls exist on this agent",
                status_code=409,
            )
        report = optimizer_report or {}
        if any(issue.get("severity") in ("blocking", "error") for issue in [*report.get("conflicts", []), *report.get("issues", [])]):
            raise AppError(ErrorCode.VALIDATION_ERROR, "Resolve blocking generation issues before publishing", status_code=422)
        if report.get("status") == "needs_clarification":
            raise AppError(ErrorCode.VALIDATION_ERROR, "Generation needs clarification before publication", status_code=422)

    async def publish_agent_brain(
        self, agent_id: str, *, expected_revision: str | None = None,
        sections: list[dict[str, Any]] | None = None,
        optimized_prompt: str | None = None,
        optimizer_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = await business_brain_store.get_sections(agent_id)
        revision = draft_revision(current)
        if expected_revision is not None and expected_revision != revision:
            raise AppError(ErrorCode.CONFLICT, "This draft changed. Review the latest revision before publishing.", status_code=409)
        source_sections = copy.deepcopy(current if sections is None else sections)
        for section in source_sections:
            section.setdefault("section_id", str(uuid.uuid4()))
            section.setdefault("enabled", True)
            section.setdefault("order", 0)
            section["agent_id"] = agent_id
        await self.validate_publication(agent_id, source_sections, optimizer_report)

        raw_prompt, source_checksum = assemble_raw_business_prompt(source_sections)
        if optimized_prompt is None:
            previous = await business_brain_store.get_latest_published(agent_id)
            opt = await optimize_business_prompt(
                raw_prompt, source_checksum=source_checksum,
                previous_optimized=previous["optimized_prompt"] if previous else None,
                preserve_source=True,
            )
            optimized_prompt, optimizer_report = opt.optimized_business_prompt, opt.to_dict()
        report = dict(optimizer_report or {})
        await self.validate_publication(agent_id, source_sections, report)
        platform = await platform_brain_store.get_active()
        lang, disclosure_enabled, disclosure_text = await self._agent_info(agent_id)
        if is_unified_compiled_brain(optimized_prompt):
            compiled_text = optimized_prompt
            # Keep the stored checksum on the artifact as published; the
            # disclosure is re-applied on every compile for the active config.
            report["compiled_artifact_checksum"] = checksum_instructions(optimized_prompt)
        else:
            platform_rules = platform_body_for_agent_language(platform["body"], lang)
            compiled_text = assemble_unified_brain(language=lang, script=optimized_prompt, platform_call_rules=platform_rules)
        from server.prompts.agent_voice_rules import inject_recording_disclosure

        compiled_text = inject_recording_disclosure(
            compiled_text,
            enabled=disclosure_enabled,
            disclosure_text=disclosure_text,
            language=lang,
        )
        self._reject_contradictory_brain(compiled_text, lang, agent_id=agent_id, status_code=422)
        published = {
            "version_id": f"bb_v{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}",
            "agent_id": agent_id, "optimized_prompt": optimized_prompt,
            "source_checksum": source_checksum, "optimizer_report": {**report, "draft_revision": draft_revision(source_sections)},
            "status": "published", "published_at": datetime.now(timezone.utc).isoformat(),
        }
        snapshot = {
            "compiled_version": f"cb_v{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}",
            "platform_version": platform["version_id"], "business_version": published["version_id"],
            "static_rules_version": STATIC_OUTPUT_RULES_VERSION, "compiled_text": compiled_text,
            "checksum": checksum_instructions(compiled_text), "token_estimate": estimate_tokens(compiled_text),
            "compiled_at": datetime.now(timezone.utc).isoformat(),
        }
        # The optimizer may await a provider. Recheck under the same row lock as
        # version creation and activation so concurrent edits cannot slip through.
        await business_brain_store.commit_reviewed_publication(
            agent_id, expected_revision=revision, published=published, snapshot=snapshot,
            sections=source_sections if sections is not None else None,
        )
        _COMPILED_CACHE[snapshot["compiled_version"]] = snapshot
        _AGENT_ACTIVE[agent_id] = snapshot["compiled_version"]
        return snapshot

    async def get_active_for_agent(self, agent_id: str) -> dict[str, Any]:
        factory = get_session_factory()
        db_active: str | None = None
        if factory is not None:
            async with factory() as session:
                result = await session.execute(select(Agent).where(Agent.agent_id == uuid.UUID(agent_id)))
                agent = result.scalar_one_or_none()
                if agent and agent.active_compiled_brain_version:
                    db_active = agent.active_compiled_brain_version

        cached_active = _AGENT_ACTIVE.get(agent_id)
        if db_active and cached_active and cached_active != db_active:
            _AGENT_ACTIVE.pop(agent_id, None)

        version_id = db_active or cached_active
        if version_id and version_id in _COMPILED_CACHE:
            if db_active:
                _AGENT_ACTIVE[agent_id] = db_active
            return _COMPILED_CACHE[version_id]

        if factory is not None and db_active:
            snap = await self.get_snapshot(db_active)
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
