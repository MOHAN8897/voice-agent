"""PostgreSQL call index — metadata only; file I/O stays in ledger/archive."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from server.db.connection import get_session_factory
from server.db.models.entities import Call

_MEM: dict[str, dict[str, Any]] = {}


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_dict(row: Call) -> dict[str, Any]:
    return {
        "call_id": str(row.call_id),
        "tenant_id": str(row.tenant_id),
        "agent_id": str(row.agent_id),
        "session_id": row.session_id,
        "channel": row.channel,
        "direction": row.direction,
        "campaign_id": str(row.campaign_id) if row.campaign_id else None,
        "environment": row.environment,
        "tier": row.tier,
        "combination_id": row.combination_id,
        "compiled_brain_version": row.compiled_brain_version,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "duration_sec": row.duration_sec,
        "disposition": row.disposition,
        "finalization_status": row.finalization_status,
        "storage_path": row.storage_path,
        "end_reason": row.end_reason,
        "last_heartbeat_at": row.last_heartbeat_at.isoformat() if row.last_heartbeat_at else None,
    }


class CallStore:
    async def insert(self, record: dict[str, Any]) -> dict[str, Any]:
        factory = get_session_factory()
        if factory is None:
            stored = dict(record)
            for key in ("started_at", "last_heartbeat_at", "ended_at"):
                val = stored.get(key)
                if isinstance(val, datetime):
                    stored[key] = val.isoformat()
            _MEM[record["call_id"]] = stored
            return stored

        async with factory() as session:
            row = Call(
                call_id=uuid.UUID(record["call_id"]),
                tenant_id=uuid.UUID(record["tenant_id"]),
                agent_id=uuid.UUID(record["agent_id"]),
                session_id=record.get("session_id"),
                channel=record.get("channel", "browser"),
                direction=record.get("direction", "inbound"),
                campaign_id=uuid.UUID(record["campaign_id"]) if record.get("campaign_id") else None,
                environment=record.get("environment", "development"),
                tier=record.get("tier", "medium"),
                combination_id=record["combination_id"],
                compiled_brain_version=record.get("compiled_brain_version"),
                started_at=record.get("started_at") or _utcnow(),
                finalization_status=record.get("finalization_status", "pending"),
                storage_path=record["storage_path"],
                last_heartbeat_at=record.get("last_heartbeat_at") or _utcnow(),
            )
            if isinstance(row.started_at, str):
                row.started_at = datetime.fromisoformat(row.started_at.replace("Z", "+00:00"))
            session.add(row)
            await session.commit()
            return _row_to_dict(row)

    async def get(self, call_id: str) -> dict[str, Any] | None:
        factory = get_session_factory()
        if factory is None:
            rec = _MEM.get(call_id)
            return dict(rec) if rec else None

        async with factory() as session:
            result = await session.execute(select(Call).where(Call.call_id == uuid.UUID(call_id)))
            row = result.scalar_one_or_none()
            return _row_to_dict(row) if row else None

    async def update(self, call_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        factory = get_session_factory()
        if factory is None:
            rec = _MEM.get(call_id)
            if not rec:
                return None
            rec.update(fields)
            for key in ("ended_at", "last_heartbeat_at"):
                val = rec.get(key)
                if isinstance(val, datetime):
                    rec[key] = val.isoformat()
            return dict(rec)

        allowed = {
            "ended_at",
            "duration_sec",
            "disposition",
            "finalization_status",
            "end_reason",
            "last_heartbeat_at",
        }
        values = {k: v for k, v in fields.items() if k in allowed}
        async with factory() as session:
            await session.execute(update(Call).where(Call.call_id == uuid.UUID(call_id)).values(**values))
            await session.commit()
        return await self.get(call_id)

    async def list_calls(
        self,
        *,
        tenant_id: str | None = None,
        agent_id: str | None = None,
        disposition: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        factory = get_session_factory()
        if factory is None:
            rows = list(_MEM.values())
            if tenant_id:
                rows = [r for r in rows if r.get("tenant_id") == tenant_id]
            if agent_id:
                rows = [r for r in rows if r.get("agent_id") == agent_id]
            if disposition:
                rows = [r for r in rows if r.get("disposition") == disposition]
            if since:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                rows = [r for r in rows if _as_dt(r.get("started_at")) is not None and _as_dt(r.get("started_at")) >= since_dt]
            if until:
                until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
                rows = [r for r in rows if _as_dt(r.get("started_at")) is not None and _as_dt(r.get("started_at")) <= until_dt]
            rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
            return rows[offset : offset + limit], len(rows)

        async with factory() as session:
            stmt = select(Call)
            count_stmt = select(Call)
            if tenant_id:
                stmt = stmt.where(Call.tenant_id == uuid.UUID(tenant_id))
                count_stmt = count_stmt.where(Call.tenant_id == uuid.UUID(tenant_id))
            if agent_id:
                stmt = stmt.where(Call.agent_id == uuid.UUID(agent_id))
                count_stmt = count_stmt.where(Call.agent_id == uuid.UUID(agent_id))
            if disposition:
                stmt = stmt.where(Call.disposition == disposition)
                count_stmt = count_stmt.where(Call.disposition == disposition)
            if since:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                stmt = stmt.where(Call.started_at >= since_dt)
                count_stmt = count_stmt.where(Call.started_at >= since_dt)
            if until:
                until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
                stmt = stmt.where(Call.started_at <= until_dt)
                count_stmt = count_stmt.where(Call.started_at <= until_dt)
            total_result = await session.execute(count_stmt)
            total = len(total_result.scalars().all())
            result = await session.execute(
                stmt.order_by(Call.started_at.desc()).offset(offset).limit(limit)
            )
            return [_row_to_dict(r) for r in result.scalars()], total

    async def list_stale_open(self, older_than: datetime) -> list[dict[str, Any]]:
        factory = get_session_factory()
        if factory is None:
            out = []
            for rec in _MEM.values():
                if rec.get("ended_at"):
                    continue
                hb = rec.get("last_heartbeat_at") or rec.get("started_at")
                if isinstance(hb, str):
                    hb = datetime.fromisoformat(hb.replace("Z", "+00:00"))
                if hb and hb < older_than:
                    out.append(dict(rec))
            return out

        async with factory() as session:
            result = await session.execute(
                select(Call).where(Call.ended_at.is_(None), Call.last_heartbeat_at < older_than)
            )
            return [_row_to_dict(r) for r in result.scalars()]

    async def list_open(self) -> list[dict[str, Any]]:
        factory = get_session_factory()
        if factory is None:
            return [dict(rec) for rec in _MEM.values() if not rec.get("ended_at")]
        async with factory() as session:
            result = await session.execute(select(Call).where(Call.ended_at.is_(None)))
            return [_row_to_dict(r) for r in result.scalars()]

    def reset_for_tests(self) -> None:
        _MEM.clear()


call_store = CallStore()
