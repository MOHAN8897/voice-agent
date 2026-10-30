"""Window-wide analytics from persisted records; never from a paginated UI timeline."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from sqlalchemy import String, case, func, or_, select

from server.call.call_status import CALL_STATUSES, status_for_record
from server.db.connection import get_session_factory
from server.db.models.entities import Call, CallAttempt
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction, Lead


def window(stmt, model, tenant_id, agent_id, since, until):
    stmt = stmt.where(model.tenant_id == tenant_id)
    if agent_id:
        stmt = stmt.where(model.agent_id == (str(agent_id) if model is Lead else uuid.UUID(str(agent_id))))
    stamp = model.created_at if model is Lead else model.started_at
    if since:
        stmt = stmt.where(stamp >= parse_date(since))
    if until:
        stmt = stmt.where(stamp < parse_date(until))
    return stmt


def parse_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(422, "Choose valid ISO date boundaries") from None


async def performance(tenant_id: str, agent_id=None, since=None, until=None, include_attempts=True) -> dict:
    try:
        tid = uuid.UUID(str(tenant_id))
        if agent_id:
            uuid.UUID(str(agent_id))
    except ValueError:
        raise HTTPException(422, "Invalid workspace or agent") from None
    if since and until and parse_date(since) >= parse_date(until):
        raise HTTPException(422, "The end of the period must be after its start")
    async with get_session_factory()() as session:
        calls = window(select(Call), Call, tid, agent_id, since, until).where(Call.is_test.is_(False))
        attempts = window(select(CallAttempt), CallAttempt, tid, agent_id, since, until).where(CallAttempt.linked_call_id.is_(None))
        counts = {s: 0 for s in CALL_STATUSES}
        total = connected = completed = duration = 0
        known = list(CALL_STATUSES)
        # Materialised statuses are counted by the database; only rows whose status is
        # NULL/unknown (open calls, pre-status legacy rows) go through the classifier.
        call_groups = await session.execute(
            calls.with_only_columns(
                Call.status,
                func.count(),
                func.count(Call.ended_at),
                func.coalesce(func.sum(case((Call.ended_at.isnot(None) & (Call.duration_sec > 0), Call.duration_sec), else_=0)), 0),
            ).where(Call.status.in_(known)).group_by(Call.status)
        )
        for status, n, n_ended, secs in call_groups.all():
            counts[status] += int(n)
            total += int(n)
            connected += int(n)
            completed += int(n_ended)
            duration += int(secs or 0)
        legacy_calls = calls.with_only_columns(
            Call.status, Call.direction, Call.duration_sec, Call.end_reason, Call.disposition, Call.ended_at
        ).where(or_(Call.status.is_(None), Call.status.not_in(known)))
        for row in (await session.execute(legacy_calls)).all():
            status = status_for_record(dict(row._mapping))
            counts[status] = counts.get(status, 0) + 1
            total += 1
            connected += 1
            if row.ended_at:
                completed += 1
                duration += max(0, int(row.duration_sec or 0))
        if include_attempts:
            attempt_groups = await session.execute(
                attempts.with_only_columns(CallAttempt.status, func.count(), func.count(CallAttempt.answered_at))
                .where(CallAttempt.status.in_(known)).group_by(CallAttempt.status)
            )
            for status, n, n_answered in attempt_groups.all():
                counts[status] += int(n)
                total += int(n)
                connected += int(n_answered)
            legacy_attempts = attempts.with_only_columns(
                CallAttempt.status, CallAttempt.direction, CallAttempt.end_reason, CallAttempt.ended_at, CallAttempt.answered_at
            ).where(or_(CallAttempt.status.is_(None), CallAttempt.status.not_in(known)))
            for row in (await session.execute(legacy_attempts)).all():
                status = status_for_record(dict(row._mapping))
                counts[status] = counts.get(status, 0) + 1
                total += 1
                connected += int(bool(row.answered_at))
            # Answered-but-unlinked attempts are rare; read only their two timestamps.
            spans = attempts.with_only_columns(CallAttempt.answered_at, CallAttempt.ended_at).where(
                CallAttempt.answered_at.isnot(None), CallAttempt.ended_at.isnot(None))
            for answered_at, ended_at in (await session.execute(spans)).all():
                completed += 1
                duration += max(0, int((ended_at - answered_at).total_seconds()))
        leads = window(select(Lead), Lead, tid, agent_id, since, until)
        stage_rows = (await session.execute(leads.with_only_columns(Lead.stage, func.count()).group_by(Lead.stage))).all()
        stages = dict(stage_rows)
        lead_count, converted = sum(stages.values()), stages.get("converted", 0)
        # Join charged call references in this exact cohort; credits/topups/provider costs never enter CPL.
        call_ids = calls.with_only_columns(Call.call_id).subquery()
        if session.get_bind().dialect.name == "postgresql":
            # reference_id is written as f"call:{uuid}"; keep the column bare so its index is usable.
            on = BillingWalletTransaction.reference_id == "call:" + call_ids.c.call_id.cast(String)
        else:  # SQLite stores UUIDs as bare hex, so compare without dashes.
            on = func.replace(BillingWalletTransaction.reference_id, "-", "") == "call:" + func.replace(call_ids.c.call_id.cast(String), "-", "")
        charge = select(func.coalesce(func.sum(-BillingWalletTransaction.amount_cents), 0),
                        func.coalesce(func.sum(-BillingWalletTransaction.amount_inr_paise), 0), func.count()).join(call_ids, on)
        charge = charge.where(BillingWalletTransaction.tenant_id == tid,
            (BillingWalletTransaction.amount_cents < 0) | (BillingWalletTransaction.amount_inr_paise < 0))
        cents, paise, charged_count = (await session.execute(charge)).one()
        wallet = await session.get(BillingWallet, tid)
        currency = (wallet.currency if wallet else "usd").upper()
        spend_minor = int(paise if currency == "INR" else cents)
        # A zero spend is valid only if there were no connected calls or every call has a settled charge.
        complete_cost = charged_count >= connected
        return {"total": total, "connected": connected, "missed": counts.get("missed", 0), "counts": counts,
            "completedConnected": completed, "totalDurationSec": duration,
            "avgDurationSec": round(duration / completed) if completed else 0,
            "connectRate": round(connected * 100 / total, 1) if total else None,
            "leadCount": lead_count, "convertedLeads": converted, "leadStageCounts": stages,
            "conversionRate": round(converted * 100 / lead_count, 1) if lead_count else None,
            "cost": {"currency": currency, "settledSpend": spend_minor / 100, "chargedCalls": charged_count,
                     "complete": complete_cost, "costPerLead": round(spend_minor / 100 / lead_count, 2) if lead_count and complete_cost else None},
            "definitions": {"connectRate": "Calls reaching an answered connection / all attempts. May include voicemail; excludes test calls.",
                "avgDuration": "Completed connected call duration / completed connected calls.",
                "conversionRate": "Tenant-confirmed converted leads / leads created in this period, as of now.",
                "costPerLead": "Settled wallet call charges for this period's calls / leads created in this period. Unavailable while charges are incomplete."}}
