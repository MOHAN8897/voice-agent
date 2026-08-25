"""
Platform brain store — developer-only versioned platform rules.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select

from server.db.connection import get_session_factory
from server.db.models.brain_models import PlatformBrainVersion
from server.prompts.brain_prompt import CORE_SYSTEM_PROMPT

_MEM_PLATFORM: dict[str, dict[str, Any]] = {}
_ACTIVE_PLATFORM_ID: str | None = None
_LATEST_DRAFT_ID: str | None = None


def _default_platform_body() -> str:
    # CORE_SYSTEM_PROMPT already embeds safety + telugu sections — avoid duplication
    return CORE_SYSTEM_PROMPT


class PlatformBrainStore:
    async def ensure_seed(self) -> str:
        factory = get_session_factory()
        if factory is None:
            global _ACTIVE_PLATFORM_ID
            if not _MEM_PLATFORM:
                vid = "pb_v1"
                _MEM_PLATFORM[vid] = {
                    "version_id": vid,
                    "body": _default_platform_body(),
                    "status": "active",
                    "activated_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "system",
                }
                _ACTIVE_PLATFORM_ID = vid
            return _ACTIVE_PLATFORM_ID or "pb_v1"

        async with factory() as session:
            result = await session.execute(select(PlatformBrainVersion).where(PlatformBrainVersion.status == "active"))
            active = result.scalar_one_or_none()
            if active:
                return active.version_id
            vid = "pb_v1"
            row = PlatformBrainVersion(
                version_id=vid,
                body=_default_platform_body(),
                status="active",
                activated_at=datetime.now(timezone.utc),
                created_by="system",
            )
            session.add(row)
            await session.commit()
            return vid

    async def get_active(self) -> dict[str, Any]:
        factory = get_session_factory()
        if factory is None:
            await self.ensure_seed()
            vid = _ACTIVE_PLATFORM_ID or "pb_v1"
            return dict(_MEM_PLATFORM[vid])

        async with factory() as session:
            result = await session.execute(select(PlatformBrainVersion).where(PlatformBrainVersion.status == "active"))
            row = result.scalar_one_or_none()
            if not row:
                vid = await self.ensure_seed()
                return await self.get_version(vid)
            return self._row_to_dict(row)

    async def get_version(self, version_id: str) -> dict[str, Any]:
        factory = get_session_factory()
        if factory is None:
            return dict(_MEM_PLATFORM[version_id])

        async with factory() as session:
            result = await session.execute(
                select(PlatformBrainVersion).where(PlatformBrainVersion.version_id == version_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                raise KeyError(version_id)
            return self._row_to_dict(row)

    async def save_draft(self, body: str, *, created_by: str = "developer") -> dict[str, Any]:
        vid = f"pb_draft_{uuid.uuid4().hex[:8]}"
        factory = get_session_factory()
        if factory is None:
            global _LATEST_DRAFT_ID
            _MEM_PLATFORM[vid] = {
                "version_id": vid,
                "body": body,
                "status": "draft",
                "activated_at": None,
                "created_by": created_by,
            }
            _LATEST_DRAFT_ID = vid
            return dict(_MEM_PLATFORM[vid])

        async with factory() as session:
            row = PlatformBrainVersion(version_id=vid, body=body, status="draft", created_by=created_by)
            session.add(row)
            await session.commit()
            return self._row_to_dict(row)

    async def get_draft(self) -> dict[str, Any] | None:
        factory = get_session_factory()
        if factory is None:
            await self.ensure_seed()
            if _LATEST_DRAFT_ID and _LATEST_DRAFT_ID in _MEM_PLATFORM:
                row = _MEM_PLATFORM[_LATEST_DRAFT_ID]
                if row.get("status") == "draft":
                    return dict(row)
            drafts = [v for v in _MEM_PLATFORM.values() if v.get("status") == "draft"]
            return dict(drafts[-1]) if drafts else None

        async with factory() as session:
            result = await session.execute(
                select(PlatformBrainVersion)
                .where(PlatformBrainVersion.status == "draft")
                .order_by(desc(PlatformBrainVersion.created_at))
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return self._row_to_dict(row) if row else None

    async def activate(self, version_id: str) -> dict[str, Any]:
        factory = get_session_factory()
        if factory is None:
            global _ACTIVE_PLATFORM_ID
            for v in _MEM_PLATFORM.values():
                v["status"] = "archived"
            _MEM_PLATFORM[version_id]["status"] = "active"
            _MEM_PLATFORM[version_id]["activated_at"] = datetime.now(timezone.utc).isoformat()
            _ACTIVE_PLATFORM_ID = version_id
            return dict(_MEM_PLATFORM[version_id])

        async with factory() as session:
            result = await session.execute(select(PlatformBrainVersion))
            for row in result.scalars():
                row.status = "archived" if row.version_id != version_id else "active"
                if row.version_id == version_id:
                    row.activated_at = datetime.now(timezone.utc)
            await session.commit()
        return await self.get_version(version_id)

    async def list_versions(self, limit: int = 50) -> list[dict[str, Any]]:
        factory = get_session_factory()
        if factory is None:
            await self.ensure_seed()
            rows = sorted(_MEM_PLATFORM.values(), key=lambda v: v.get("activated_at") or "", reverse=True)
            return [
                {
                    "version_id": r["version_id"],
                    "status": r["status"],
                    "activated_at": r.get("activated_at"),
                    "created_by": r.get("created_by"),
                    "preview": self.redacted_preview(r["body"]),
                    "char_count": len(r.get("body") or ""),
                }
                for r in rows[:limit]
            ]

        async with factory() as session:
            result = await session.execute(
                select(PlatformBrainVersion).order_by(desc(PlatformBrainVersion.created_at)).limit(limit)
            )
            out: list[dict[str, Any]] = []
            for row in result.scalars():
                out.append(
                    {
                        "version_id": row.version_id,
                        "status": row.status,
                        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
                        "created_by": row.created_by,
                        "preview": self.redacted_preview(row.body),
                        "char_count": len(row.body or ""),
                    }
                )
            return out

    async def rollback(self, version_id: str) -> dict[str, Any]:
        """Emergency rollback — re-activate a prior archived version."""
        version = await self.get_version(version_id)
        if version.get("status") == "draft":
            raise ValueError("Cannot rollback to a draft — activate or archive it first")
        return await self.activate(version_id)

    def redacted_preview(self, body: str) -> str:
        lines = [ln for ln in body.splitlines() if ln.strip()]
        return f"Platform rules active — {len(lines)} constraint blocks (redacted)"

    @staticmethod
    def _row_to_dict(row: PlatformBrainVersion) -> dict[str, Any]:
        return {
            "version_id": row.version_id,
            "body": row.body,
            "status": row.status,
            "activated_at": row.activated_at.isoformat() if row.activated_at else None,
            "created_by": row.created_by,
        }


platform_brain_store = PlatformBrainStore()
