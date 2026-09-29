"""
Business brain store — per-agent sections and published versions.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from server.brain.sections import SECTION_LABELS, default_section_seeds
from server.db.connection import get_session_factory
from server.db.models.brain_models import BusinessBrainSection, BusinessBrainVersion

_MEM_SECTIONS: dict[str, list[dict[str, Any]]] = {}
_MEM_VERSIONS: dict[str, list[dict[str, Any]]] = {}

# Exact text of superseded default seeds, keyed by section type. Kept so
# `ensure_default_sections` can tell "still an old default" apart from
# "someone edited this" — only the former is re-seeded. A type can hold several
# because a default may be revised more than once before an agent is recompiled.
_LEGACY_DEFAULT_TEXTS: dict[str, tuple[str, ...]] = {
    "identity_purpose": (
        """VOICE CALL MODE — spoken assistant
- You represent this business on a live phone call. For sales/lead work, act as its sales representative — warm, clear, on-brand.
- Reply in the call language with everyday words the caller uses. Sound like a helpful colleague, not a policy page.
- 1–2 short sentences. Ask a question only when you still need a fact — never a qualification checklist.
- Never use bullet lists, markdown, or numbered steps in voice replies.
- Never say you are an AI unless asked. Never say goodbye unless you are actually hanging up.
- If they object, are busy, want WhatsApp, or say don't call — honor that. Do not keep selling.
- Do not claim you sent a message, opened a ticket, made a booking, changed a contact preference, or handed work to a team unless it really happened.
- Keep implementation details private. Never mention tools, connections, system access, capability, or "on this call"; state the honest business outcome.
- If transcript is unclear, ask them to repeat once — do not guess.
- Hesitation (hmm, umm, let me think) is not a cue to pitch or ask another question.
- Sarcasm is not a buying signal. Missing facts: I'll check and get back to you.
- If corrected, own it briefly and use the corrected fact. Harmless small talk gets one natural beat; do not leave the business role.
- Greet with name + company + brief call purpose only on the first turn. A later hello means they are checking you are there — answer briefly and continue; do not restart the pitch.
- Do not repeat the same pitch, facts, or next-step line every turn. Hang up only when they confirm they are done or confirm the next step — never on okay/thanks, and never just because details are already known. Busy: one callback offer, stay on the line.""",
        # Intermediate revision, superseded within the same change: it dropped the
        # busy-stay-on-the-line rule that test_hangup_judgment_critical requires.
        """VOICE CALL MODE — spoken assistant
- You represent this business on a live phone call. For sales/lead work, act as its sales representative — warm, clear, on-brand.
- Reply in the call language with everyday words the caller uses. Sound like a helpful colleague, not a policy page.
- Sarcasm is not a buying signal. Missing facts: I'll check and get back to you.""",
    ),
    "facts": (
        """You are a helpful voice assistant for this business.
- Prefer practical, accurate answers grounded in the brief and what the user said.
- Keep domain facts conservative — if unsure, say so briefly in the call language.
- Never invent prices, policies, salaries, capabilities, completed actions, or prior conversations.""",
    ),
    "flow_qualification": (
        "Progress like a human on a live phone. Ask-if-unknown only; never re-ask completed fields; "
        "never a numbered Question/Step tree. "
        "Sales/lead loop: Understand → Answer first → ask only unknown fields "
        "(interest, name, preference) → Recommend → Next step. "
        "Dense dumps: use all facts; do not checklist. Send-details: honor and stop asking. "
        "Appointment/service: need → preferred day/time → confirm slot. "
        "Education: goal → availability → answer course/price → trial or enroll. "
        "If they only wanted information, inform and stop converting. "
        "If busy, one callback offer, no pitch, stay on the line.",
        # Intermediate revision that dropped the qualifying-field list.
        "Progress like a human on a live phone. Ask only for fields you do not have. "
        "Send-details: honor and stop asking. "
        "If they only wanted information, inform and stop converting.",
    ),
}


def assemble_raw_business_prompt(sections: list[dict[str, Any]]) -> tuple[str, str]:
    enabled = sorted([s for s in sections if s.get("enabled", True)], key=lambda x: int(x.get("order", 0)))
    parts: list[str] = []
    for s in enabled:
        sid = s.get("section_id", "")
        stype = s.get("type", "custom")
        parts.append(f"<!-- section:{stype}:{sid} -->\n{s.get('raw_text', '')}")
    raw = "\n\n".join(parts)
    checksum = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, checksum


class BusinessBrainStore:
    async def ensure_default_sections(self, agent_id: str) -> list[dict[str, Any]]:
        existing = await self.get_sections(agent_id)
        if existing:
            return await self._refresh_untouched_defaults(agent_id, existing)
        seeds = default_section_seeds()
        sections = [
            {
                "section_id": str(uuid.uuid4()),
                "agent_id": agent_id,
                "type": seed.type,
                "title": seed.title,
                "raw_text": seed.raw_text,
                "order": seed.order,
                "enabled": seed.enabled,
            }
            for seed in seeds
        ]
        return await self.save_draft_sections(agent_id, sections)

    async def _refresh_untouched_defaults(
        self, agent_id: str, sections: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Re-seed sections still holding a superseded default, byte for byte.

        The default seeds were slimmed because they restated the platform rules
        every brain already carries. Agents created before that keep the old
        text in the database, so they would never shrink. Matching on the exact
        previous text is what makes this safe: a section the user has edited
        does not match and is left completely alone.
        """
        if not _LEGACY_DEFAULT_TEXTS:
            return sections
        current = {seed.type: seed.raw_text for seed in default_section_seeds()}
        updated = list(sections)
        changed = False
        for idx, section in enumerate(sections):
            stype = section.get("type", "")
            stored = (section.get("raw_text") or "").strip()
            if not any(stored == legacy.strip() for legacy in _LEGACY_DEFAULT_TEXTS.get(stype, ())):
                continue
            replacement = current.get(stype)
            if replacement is None or replacement.strip() == stored:
                continue
            updated[idx] = {**section, "raw_text": replacement}
            changed = True
        if not changed:
            return sections
        return await self.save_draft_sections(agent_id, updated)

    async def get_sections(self, agent_id: str) -> list[dict[str, Any]]:
        factory = get_session_factory()
        if factory is None:
            return list(_MEM_SECTIONS.get(agent_id, []))

        async with factory() as session:
            aid = uuid.UUID(agent_id)
            result = await session.execute(
                select(BusinessBrainSection).where(BusinessBrainSection.agent_id == aid).order_by(BusinessBrainSection.order)
            )
            return [self._section_row(r) for r in result.scalars()]

    async def save_draft_sections(self, agent_id: str, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        factory = get_session_factory()
        normalized = []
        for s in sections:
            normalized.append(
                {
                    "section_id": str(s.get("section_id") or uuid.uuid4()),
                    "agent_id": agent_id,
                    "type": s.get("type", "custom"),
                    "title": s.get("title") or SECTION_LABELS.get(s.get("type", "custom"), "Custom"),
                    "raw_text": str(s.get("raw_text") or ""),
                    "order": int(s.get("order", 0)),
                    "enabled": bool(s.get("enabled", True)),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        if factory is None:
            _MEM_SECTIONS[agent_id] = normalized
            return normalized

        async with factory() as session:
            aid = uuid.UUID(agent_id)
            result = await session.execute(select(BusinessBrainSection).where(BusinessBrainSection.agent_id == aid))
            for row in result.scalars():
                await session.delete(row)
            for s in normalized:
                session.add(
                    BusinessBrainSection(
                        section_id=uuid.UUID(s["section_id"]),
                        agent_id=aid,
                        type=s["type"],
                        title=s["title"],
                        raw_text=s["raw_text"],
                        order=s["order"],
                        enabled=s["enabled"],
                    )
                )
            await session.commit()
        return normalized

    async def save_published_version(
        self,
        agent_id: str,
        *,
        optimized_prompt: str,
        source_checksum: str,
        optimizer_report: dict[str, Any],
    ) -> dict[str, Any]:
        version_id = f"bb_v{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        record = {
            "version_id": version_id,
            "agent_id": agent_id,
            "optimized_prompt": optimized_prompt,
            "optimizer_report": optimizer_report,
            "source_checksum": source_checksum,
            "status": "published",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        factory = get_session_factory()
        if factory is None:
            _MEM_VERSIONS.setdefault(agent_id, []).append(record)
            return record

        async with factory() as session:
            session.add(
                BusinessBrainVersion(
                    version_id=version_id,
                    agent_id=uuid.UUID(agent_id),
                    optimized_prompt=optimized_prompt,
                    optimizer_report=optimizer_report,
                    source_checksum=source_checksum,
                    status="published",
                    published_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
        return record

    async def get_versions(self, agent_id: str) -> list[dict[str, Any]]:
        factory = get_session_factory()
        if factory is None:
            return list(_MEM_VERSIONS.get(agent_id, []))

        async with factory() as session:
            result = await session.execute(
                select(BusinessBrainVersion)
                .where(BusinessBrainVersion.agent_id == uuid.UUID(agent_id))
                .order_by(BusinessBrainVersion.created_at.desc())
            )
            return [
                {
                    "version_id": r.version_id,
                    "agent_id": str(r.agent_id),
                    "optimized_prompt": r.optimized_prompt,
                    "optimizer_report": r.optimizer_report,
                    "source_checksum": r.source_checksum,
                    "status": r.status,
                    "published_at": r.published_at.isoformat() if r.published_at else None,
                }
                for r in result.scalars()
            ]

    async def get_latest_published(self, agent_id: str) -> dict[str, Any] | None:
        versions = await self.get_versions(agent_id)
        published = [v for v in versions if v.get("status") == "published"]
        return published[0] if published else None

    @staticmethod
    def _section_row(row: BusinessBrainSection) -> dict[str, Any]:
        return {
            "section_id": str(row.section_id),
            "agent_id": str(row.agent_id),
            "type": row.type,
            "title": row.title,
            "raw_text": row.raw_text,
            "order": row.order,
            "enabled": row.enabled,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


business_brain_store = BusinessBrainStore()
