"""PostgreSQL call index — metadata only; file I/O stays in ledger/archive."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from server.call.call_status import CALL_STATUSES, is_valid_call_status, status_for_record
from server.db.connection import get_session_factory
from server.db.models.entities import Call, CallAttempt

_MEM: dict[str, dict[str, Any]] = {}


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_dict(row: Call) -> dict[str, Any]:
    record: dict[str, Any] = {
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
    # Rows written before the status column keep status=None; derive it so every
    # consumer (console, callbacks, analytics) sees the same canonical value.
    record["status"] = status_for_record(record)
    return record


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

        parsed = _parse_uuid(call_id)
        if parsed is None:
            return None

        async with factory() as session:
            result = await session.execute(select(Call).where(Call.call_id == parsed))
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
            rec["status"] = status_for_record(rec)
            return dict(rec)

        allowed = {
            "ended_at",
            "duration_sec",
            "disposition",
            "finalization_status",
            "end_reason",
            "status",
            "last_heartbeat_at",
        }
        parsed = _parse_uuid(call_id)
        if parsed is None:
            return None
        values = {k: v for k, v in fields.items() if k in allowed}
        if not values:
            return await self.get(call_id)
        values = await self._with_materialized_status(call_id, values)
        async with factory() as session:
            await session.execute(update(Call).where(Call.call_id == parsed).values(**values))
            await session.commit()
        return await self.get(call_id)

    async def _with_materialized_status(self, call_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """Keep the materialised ``status`` column in step with the lifecycle fields.

        A caller may pass an explicit status; otherwise it is recomputed from the
        merged current+incoming row so the column always equals what
        ``status_for_record`` would derive on read.
        """
        explicit = values.pop("status", None)
        if is_valid_call_status(explicit):
            values["status"] = str(explicit).strip().lower()
            return values
        if not ({"ended_at", "duration_sec", "disposition", "end_reason"} & set(values)):
            return values
        current = await self.get(call_id)
        probe = {**(current or {}), **values}
        probe["ended_at"] = _as_dt(values.get("ended_at")) or current.get("ended_at")
        values["status"] = status_for_record(probe)
        return values

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
        statuses: list[str] | None = None,
        direction: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        wanted = {s for s in (statuses or []) if s in CALL_STATUSES}
        factory = get_session_factory()
        if factory is None:
            rows = list(_MEM.values())
            if tenant_id:
                rows = [r for r in rows if r.get("tenant_id") == tenant_id]
            if agent_id:
                rows = [r for r in rows if r.get("agent_id") == agent_id]
            if disposition:
                rows = [r for r in rows if r.get("disposition") == disposition]
            if direction:
                rows = [r for r in rows if (r.get("direction") or "") == direction]
            if since:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                rows = [r for r in rows if _as_dt(r.get("started_at")) is not None and _as_dt(r.get("started_at")) >= since_dt]
            if until:
                until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
                rows = [r for r in rows if _as_dt(r.get("started_at")) is not None and _as_dt(r.get("started_at")) <= until_dt]
            rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
            if wanted:
                # in_progress is derived (ended_at IS NULL), so it can never match
                # the materialised column — filter it in Python alongside the rest.
                rows = [r for r in rows if _matches_status(r, wanted)]
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
            if direction:
                stmt = stmt.where(Call.direction == direction)
                count_stmt = count_stmt.where(Call.direction == direction)
            if since:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                stmt = stmt.where(Call.started_at >= since_dt)
                count_stmt = count_stmt.where(Call.started_at >= since_dt)
            if until:
                until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
                stmt = stmt.where(Call.started_at <= until_dt)
                count_stmt = count_stmt.where(Call.started_at <= until_dt)
            if wanted:
                in_sql = [s for s in wanted if s != "in_progress"]
                clauses = []
                if in_sql:
                    clauses.append(Call.status.in_(in_sql))
                if "in_progress" in wanted:
                    clauses.append(Call.ended_at.is_(None))
                if clauses:
                    from sqlalchemy import or_ as _or_

                    cond = clauses[0] if len(clauses) == 1 else _or_(*clauses)
                    stmt = stmt.where(cond)
                    count_stmt = count_stmt.where(cond)
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
        _ATTEMPT_MEM.clear()


def _matches_status(record: dict[str, Any], wanted: set[str]) -> bool:
    return status_for_record(record) in wanted


def _attempt_row_to_dict(row: CallAttempt) -> dict[str, Any]:
    return {
        "attempt_id": str(row.attempt_id),
        "tenant_id": str(row.tenant_id),
        "agent_id": str(row.agent_id) if row.agent_id else None,
        "provider": row.provider,
        "provider_call_control_id": row.provider_call_control_id,
        "direction": row.direction,
        "from_number": row.from_number,
        "to_number": row.to_number,
        "linked_call_id": str(row.linked_call_id) if row.linked_call_id else None,
        "status": status_for_record(
            {
                "status": row.status,
                "direction": row.direction,
                "duration_sec": _attempt_duration(row),
                "end_reason": row.end_reason,
                "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            }
        ),
        "policy_reason": row.policy_reason,
        "end_reason": row.end_reason,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "answered_at": row.answered_at.isoformat() if row.answered_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "duration_sec": _attempt_duration(row),
    }


def _attempt_duration(row: CallAttempt) -> int | None:
    if not row.started_at or not row.ended_at:
        return None
    return max(0, int((row.ended_at - row.started_at).total_seconds()))


_ATTEMPT_MEM: dict[str, dict[str, Any]] = {}


class CallAttemptStore:
    """Ringing events, persisted even when the call never connects.

    Every method is failure-tolerant by contract: the carrier webhook must never be
    blocked or failed by this store, so callers wrap these in try/except and the
    in-memory path is used when no database is configured.
    """

    async def upsert_by_control(
        self,
        control_id: str,
        *,
        tenant_id: str,
        agent_id: str | None = None,
        provider: str = "telnyx",
        direction: str = "inbound",
        from_number: str | None = None,
        to_number: str | None = None,
        status: str = "in_progress",
        policy_reason: str | None = None,
        started_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        control = str(control_id or "").strip()
        if not control:
            return None
        factory = get_session_factory()
        if factory is None:
            rec = _ATTEMPT_MEM.get(control) or {
                "attempt_id": str(uuid.uuid4()),
                "tenant_id": str(tenant_id),
                "provider_call_control_id": control,
            }
            rec.update(
                {
                    "agent_id": agent_id,
                    "provider": provider,
                    "direction": direction,
                    "from_number": from_number,
                    "to_number": to_number,
                    "status": status,
                    "policy_reason": policy_reason,
                    "started_at": (started_at or _utcnow()).isoformat(),
                    "answered_at": None,
                    "ended_at": None,
                }
            )
            _ATTEMPT_MEM[control] = rec
            return dict(rec)

        async with factory() as session:
            result = await session.execute(
                select(CallAttempt).where(CallAttempt.provider_call_control_id == control)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = CallAttempt(
                    attempt_id=uuid.uuid4(),
                    tenant_id=uuid.UUID(str(tenant_id)),
                    provider_call_control_id=control,
                )
                session.add(row)
            row.provider = provider
            row.direction = direction
            row.from_number = from_number
            row.to_number = to_number
            row.status = status
            row.policy_reason = policy_reason
            if agent_id:
                parsed = _parse_uuid(agent_id)
                if parsed is not None:
                    row.agent_id = parsed
            if started_at is not None:
                row.started_at = started_at
            elif row.started_at is None:
                row.started_at = _utcnow()
            await session.commit()
            await session.refresh(row)
            return _attempt_row_to_dict(row)

    async def finalize_by_control(
        self,
        control_id: str,
        *,
        status: str,
        end_reason: str | None = None,
        linked_call_id: str | None = None,
        answered: bool = False,
    ) -> dict[str, Any] | None:
        control = str(control_id or "").strip()
        if not control:
            return None
        now = _utcnow()
        factory = get_session_factory()
        if factory is None:
            rec = _ATTEMPT_MEM.get(control)
            if not rec:
                return None
            rec["status"] = status
            rec["end_reason"] = end_reason
            rec["ended_at"] = now.isoformat()
            if answered:
                rec["answered_at"] = (now).isoformat()
            if linked_call_id:
                rec["linked_call_id"] = linked_call_id
            return dict(rec)

        async with factory() as session:
            result = await session.execute(
                select(CallAttempt).where(CallAttempt.provider_call_control_id == control)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.status = status
            row.end_reason = end_reason
            row.ended_at = now
            if answered:
                row.answered_at = now
            parsed_call = _parse_uuid(linked_call_id) if linked_call_id else None
            if parsed_call is not None:
                row.linked_call_id = parsed_call
            await session.commit()
            await session.refresh(row)
            return _attempt_row_to_dict(row)

    async def link_to_call(self, control_id: str, call_id: str) -> None:
        await self.finalize_by_control(
            control_id, status="answered", end_reason="answered", linked_call_id=call_id, answered=True
        )

    async def list_attempts(
        self,
        *,
        tenant_id: str | None = None,
        agent_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        factory = get_session_factory()
        if factory is None:
            rows = list(_ATTEMPT_MEM.values())
            if tenant_id:
                rows = [r for r in rows if str(r.get("tenant_id")) == str(tenant_id)]
            if agent_id:
                rows = [r for r in rows if str(r.get("agent_id") or "") == str(agent_id)]
            rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
            return [dict(r) for r in rows[offset : offset + limit]], len(rows)

        async with factory() as session:
            stmt = select(CallAttempt)
            count_stmt = select(CallAttempt)
            if tenant_id:
                stmt = stmt.where(CallAttempt.tenant_id == uuid.UUID(tenant_id))
                count_stmt = count_stmt.where(CallAttempt.tenant_id == uuid.UUID(tenant_id))
            if agent_id:
                stmt = stmt.where(CallAttempt.agent_id == uuid.UUID(agent_id))
                count_stmt = count_stmt.where(CallAttempt.agent_id == uuid.UUID(agent_id))
            if since:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                stmt = stmt.where(CallAttempt.started_at >= since_dt)
                count_stmt = count_stmt.where(CallAttempt.started_at >= since_dt)
            if until:
                until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
                stmt = stmt.where(CallAttempt.started_at <= until_dt)
                count_stmt = count_stmt.where(CallAttempt.started_at <= until_dt)
            total = len((await session.execute(count_stmt)).scalars().all())
            result = await session.execute(
                stmt.order_by(CallAttempt.started_at.desc()).offset(offset).limit(limit)
            )
            return [_attempt_row_to_dict(r) for r in result.scalars()], total

    def reset_for_tests(self) -> None:
        _ATTEMPT_MEM.clear()


call_attempt_store = CallAttemptStore()
call_store = CallStore()
