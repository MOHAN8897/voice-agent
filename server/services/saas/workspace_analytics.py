"""Workspace analytics: one tenant-scoped read of calls, leads, callbacks, follow-ups,
DND, spend and tags for a date range. Counts come from persisted rows, never from a
paginated console list; headline call/lead numbers reuse ``agent_performance``.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select

from server.call.call_status import status_for_record
from server.call.hangup_causes import outcome_for_item
from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Call, CallAttempt, CallCallback
from server.db.models.followup_models import FollowUpJob, LeadAssessment
from server.db.models.language_switch_models import LanguageSwitchRequest
from server.db.models.phase5_models import DncEntry
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction, Lead
from server.services.saas.agent_performance import performance

#: Every date the tenant sees is an Indian calendar day.
IST = timezone(timedelta(hours=5, minutes=30), "IST")
RANGES = ("today", "7d", "30d", "custom")
MAX_RANGE_DAYS = 366

#: Owner-facing call outcome buckets, in display order.
OUTCOMES = ("answered", "no_answer", "busy", "declined", "unreachable", "failed", "voicemail", "in_progress")

#: Follow-up job statuses grouped the way an owner reads them.
FOLLOWUP_GROUPS = {
    "scheduled": ("planning", "resolving", "needs_review", "scheduled", "dispatching", "dialed"),
    "done": ("completed",),
    "failed": ("expired",),
    "cancelled": ("cancelled", "suppressed"),
}
#: Completed jobs whose reason says the number never connected count as failed.
FOLLOWUP_FAILED_REASONS = ("number_invalid", "attempt_limit", "attempt_limit_or_terminal_result")


def outcome_bucket(status: str | None, direction: str | None, end_reason: str | None = None,
                   policy_reason: str | None = None) -> str:
    """Map a call/attempt onto one of ``OUTCOMES`` using the console's own outcome kinds."""
    status = str(status or "").lower()
    if status in ("answered", "outbound"):
        return "answered"
    if status == "in_progress":
        return "in_progress"
    kind = outcome_for_item({"status": status, "direction": direction, "end_reason": end_reason,
                             "policy_reason": policy_reason}).get("outcome_kind")
    return {"no_answer": "no_answer", "missed_call": "no_answer", "busy": "busy", "declined": "declined",
            "unreachable": "unreachable", "invalid_number": "failed", "connect_failed": "failed",
            "voicemail": "voicemail"}.get(kind or "", "failed")


def followup_group(status: str | None, reason: str | None) -> str:
    if status == "completed" and reason in FOLLOWUP_FAILED_REASONS:
        return "failed"
    for group, statuses in FOLLOWUP_GROUPS.items():
        if status in statuses:
            return group
    return "scheduled"


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise HTTPException(422, "Choose valid dates (YYYY-MM-DD)") from None


def resolve_range(range_key: str | None = "7d", since: str | None = None, until: str | None = None,
                  now: datetime | None = None) -> tuple[datetime, datetime, list[date]]:
    """(start, end) in UTC plus the IST days they cover. ``since``/``until`` are inclusive IST dates."""
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    today = now.date()
    key = range_key or "7d"
    if key not in RANGES:
        raise HTTPException(422, "Choose today, 7 days, 30 days or a custom range")
    if key == "custom" or since or until:
        first = _parse_day(since) or today - timedelta(days=6)
        last = _parse_day(until) or today
    else:
        first, last = today - timedelta(days={"today": 0, "7d": 6, "30d": 29}[key]), today
    if last < first:
        raise HTTPException(422, "The end date must be on or after the start date")
    if (last - first).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(422, "Choose a range of one year or less")
    start = datetime.combine(first, datetime.min.time(), IST)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), IST)
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc), days


def ist_day(value: datetime | None) -> date | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST).date()


def tenant_uuid(value: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise HTTPException(422, "Invalid workspace") from None


def agent_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise HTTPException(422, "Invalid agent") from None


async def agent_names(session, tid: uuid.UUID) -> dict[str, str]:
    rows = (await session.execute(select(Agent.agent_id, Agent.name).where(Agent.tenant_id == tid))).all()
    return {str(aid): name for aid, name in rows}


def _call_charge_id(reference: str | None) -> str | None:
    ref = str(reference or "")
    if not ref.startswith("call:"):
        return None
    try:
        return str(uuid.UUID(ref.split(":", 1)[1].strip()))
    except ValueError:
        return None


def wallet_amount(cents: int | None, paise: int | None, currency: str, fx: float) -> float:
    """Both recorded legs rolled into the wallet currency (mirrors ``wallet_debit_display``)."""
    cents, paise = int(cents or 0), int(paise or 0)
    if currency == "INR":
        return round((paise + cents * fx) / 100, 2)
    return round((cents + paise / fx) / 100, 2)


def _fx() -> float:
    try:
        from server.config.env import get_settings
        fx = float(get_settings().fx_rate_inr)
        return fx if fx > 0 else 95.64
    except Exception:  # noqa: BLE001 - analytics must not fail on a settings read.
        return 95.64


async def workspace_analytics(tenant_id: Any, *, agent_id: str | None = None, range_key: str | None = "7d",
                              since: str | None = None, until: str | None = None) -> dict[str, Any]:
    tid = tenant_uuid(tenant_id)
    aid = agent_uuid(agent_id)
    start, end, days = resolve_range(range_key, since, until)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(503, "Analytics need the database")
    headline = await performance(str(tid), str(aid) if aid else None, start.isoformat(), end.isoformat())
    day_keys = [d.isoformat() for d in days]
    per_day = {d: {"date": d, "calls": 0, "answered": 0, "minutes": 0.0} for d in day_keys}

    async with factory() as session:
        names = await agent_names(session, tid)
        if aid and str(aid) not in names:
            raise HTTPException(404, "Agent not found")

        # Calls and never-connected attempts, bucketed by owner-facing outcome and IST day.
        outcomes = {o: 0 for o in OUTCOMES}
        calls = select(Call.started_at, Call.status, Call.direction, Call.end_reason, Call.duration_sec,
                       Call.disposition, Call.ended_at, Call.status_tags).where(
            Call.tenant_id == tid, Call.is_test.is_(False), Call.started_at >= start, Call.started_at < end)
        if aid:
            calls = calls.where(Call.agent_id == aid)
        tags: Counter[str] = Counter()
        for row in (await session.execute(calls)).all():
            status = status_for_record(dict(row._mapping))
            bucket = outcome_bucket(status, row.direction, row.end_reason)
            outcomes[bucket] += 1
            key = ist_day(row.started_at).isoformat()
            if key in per_day:
                per_day[key]["calls"] += 1
                if bucket == "answered":
                    per_day[key]["answered"] += 1
                    if row.ended_at:
                        per_day[key]["minutes"] += max(0, int(row.duration_sec or 0)) / 60
            for tag in row.status_tags or []:
                if str(tag).strip():
                    tags[str(tag).strip()] += 1
        attempts = select(CallAttempt.started_at, CallAttempt.status, CallAttempt.direction,
                          CallAttempt.end_reason, CallAttempt.policy_reason).where(
            CallAttempt.tenant_id == tid, CallAttempt.linked_call_id.is_(None),
            CallAttempt.started_at >= start, CallAttempt.started_at < end)
        if aid:
            attempts = attempts.where(CallAttempt.agent_id == aid)
        for row in (await session.execute(attempts)).all():
            bucket = outcome_bucket(row.status, row.direction, row.end_reason, row.policy_reason)
            outcomes[bucket] += 1
            key = ist_day(row.started_at).isoformat()
            if key in per_day:
                per_day[key]["calls"] += 1
                per_day[key]["answered"] += int(bucket == "answered")
        for item in per_day.values():
            item["minutes"] = round(item["minutes"], 1)

        # Leads by stage (from performance) and by where they came from.
        leads = select(Lead.lead_id, Lead.agent_id).where(Lead.tenant_id == tid, Lead.created_at >= start,
                                                           Lead.created_at < end)
        if aid:
            leads = leads.where(Lead.agent_id == str(aid))
        lead_rows = (await session.execute(leads)).all()
        sources = await lead_sources(session, tid, [r.lead_id for r in lead_rows])
        source_counts = Counter(sources.get(str(r.lead_id)) or ("ai_call" if r.agent_id else "manual")
                                for r in lead_rows)

        # Callback requests (the caller asked to be called) and language callbacks.
        cb = select(CallCallback.status, func.count()).where(
            CallCallback.tenant_id == tid, CallCallback.mode == "requested",
            CallCallback.created_at >= start, CallCallback.created_at < end)
        if aid:
            cb = cb.where(CallCallback.agent_id == str(aid))
        cb_counts = dict((await session.execute(cb.group_by(CallCallback.status))).all())
        ls = select(LanguageSwitchRequest.status, LanguageSwitchRequest.requested_language, func.count()).where(
            LanguageSwitchRequest.tenant_id == tid, LanguageSwitchRequest.created_at >= start,
            LanguageSwitchRequest.created_at < end)
        if aid:
            ls = ls.where(LanguageSwitchRequest.agent_id == str(aid))
        lang_status: Counter[str] = Counter()
        lang_by_language: dict[str, dict[str, int]] = defaultdict(lambda: {"requested": 0, "completed": 0, "pending": 0})
        for status, language, n in (await session.execute(
                ls.group_by(LanguageSwitchRequest.status, LanguageSwitchRequest.requested_language))).all():
            lang_status[status] += n
            entry = lang_by_language[language or "unknown"]
            entry["requested"] += n
            if status == "done":
                entry["completed"] += n
            elif status in ("pending", "calling"):
                entry["pending"] += n

        # Follow-ups created in the period, grouped as an owner reads them.
        fu = select(FollowUpJob.status, FollowUpJob.reason, FollowUpJob.kind, func.count()).where(
            FollowUpJob.tenant_id == tid, FollowUpJob.created_at >= start, FollowUpJob.created_at < end)
        if aid:
            fu = fu.where(FollowUpJob.agent_id == aid)
        fu_groups = {g: 0 for g in FOLLOWUP_GROUPS}
        fu_kinds: Counter[str] = Counter()
        for status, reason, kind, n in (await session.execute(
                fu.group_by(FollowUpJob.status, FollowUpJob.reason, FollowUpJob.kind))).all():
            fu_groups[followup_group(status, reason)] += n
            fu_kinds[kind] += n

        # DND is workspace-wide: the list never belongs to one agent.
        dnc_active = await session.scalar(select(func.count()).select_from(DncEntry).where(
            DncEntry.tenant_id == tid, DncEntry.active.is_(True))) or 0
        dnc_days = Counter()
        dnc_sources: Counter[str] = Counter()
        for added_at, source in (await session.execute(select(DncEntry.added_at, DncEntry.source).where(
                DncEntry.tenant_id == tid, DncEntry.added_at >= start, DncEntry.added_at < end))).all():
            dnc_days[ist_day(added_at).isoformat()] += 1
            dnc_sources[source or "manual"] += 1

        # Spend: wallet debits in the period, per day and per agent (call charges carry the call id).
        wallet = await session.get(BillingWallet, tid)
        currency = (wallet.currency if wallet else "usd").upper()
        fx = _fx()
        debits = (await session.execute(select(
            BillingWalletTransaction.created_at, BillingWalletTransaction.amount_cents,
            BillingWalletTransaction.amount_inr_paise, BillingWalletTransaction.kind,
            BillingWalletTransaction.reference_id).where(
            BillingWalletTransaction.tenant_id == tid, BillingWalletTransaction.created_at >= start,
            BillingWalletTransaction.created_at < end,
            (BillingWalletTransaction.amount_cents < 0) | (BillingWalletTransaction.amount_inr_paise < 0)))).all()
        call_ids = {cid for cid in (_call_charge_id(r.reference_id) for r in debits) if cid}
        call_agent = await _call_agents(session, tid, call_ids)
        spend_day: Counter[str] = Counter()
        spend_agent: Counter[str] = Counter()
        spend_total = 0.0
        for row in debits:
            cid = _call_charge_id(row.reference_id)
            owner = call_agent.get(cid) if cid else None
            if aid and owner != str(aid):
                continue
            amount = -wallet_amount(row.amount_cents, row.amount_inr_paise, currency, fx)
            spend_total += amount
            spend_day[ist_day(row.created_at).isoformat()] += amount
            spend_agent[owner or "other"] += amount

    agent_label = lambda key: names.get(key) or ("Other charges" if key == "other" else "Removed agent")  # noqa: E731
    return {
        "range": {"key": range_key or "7d", "since": day_keys[0], "until": day_keys[-1], "days": len(day_keys),
                  "timezone": "Asia/Kolkata", "agentId": str(aid) if aid else None},
        "calls": {
            "total": sum(outcomes.values()), "outcomes": outcomes,
            "connectRate": headline.get("connectRate"), "avgDurationSec": headline.get("avgDurationSec"),
            "minutes": round((headline.get("totalDurationSec") or 0) / 60, 1),
            "perDay": [per_day[d] for d in day_keys],
        },
        "leads": {"total": headline.get("leadCount", 0), "converted": headline.get("convertedLeads", 0),
                  "conversionRate": headline.get("conversionRate"), "byStage": headline.get("leadStageCounts", {}),
                  "bySource": dict(source_counts)},
        "callbacks": {
            "requested": sum(cb_counts.values()),
            "completed": cb_counts.get("completed", 0) + cb_counts.get("converted", 0),
            "pending": cb_counts.get("requested", 0), "dismissed": cb_counts.get("dismissed", 0),
            "byStatus": cb_counts,
        },
        "languageCallbacks": {
            "requested": sum(lang_status.values()), "completed": lang_status.get("done", 0),
            "pending": lang_status.get("pending", 0) + lang_status.get("calling", 0),
            "dismissed": lang_status.get("dismissed", 0),
            "byLanguage": [{"language": k, **v} for k, v in sorted(lang_by_language.items(), key=lambda kv: -kv[1]["requested"])],
        },
        "followups": {**fu_groups, "total": sum(fu_groups.values()), "byKind": dict(fu_kinds)},
        "dnc": {"active": int(dnc_active), "added": sum(dnc_days.values()), "bySource": dict(dnc_sources),
                "perDay": [{"date": d, "added": dnc_days.get(d, 0)} for d in day_keys]},
        "spend": {"currency": currency, "total": round(spend_total, 2),
                  "perDay": [{"date": d, "amount": round(spend_day.get(d, 0.0), 2)} for d in day_keys],
                  "byAgent": [{"agentId": None if k == "other" else k, "name": agent_label(k), "amount": round(v, 2)}
                              for k, v in spend_agent.most_common()]},
        "topTags": [{"tag": t, "count": n} for t, n in tags.most_common(10)],
    }


async def _call_agents(session, tid: uuid.UUID, call_ids: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    ids = [uuid.UUID(c) for c in call_ids]
    for i in range(0, len(ids), 500):
        rows = (await session.execute(select(Call.call_id, Call.agent_id).where(
            Call.tenant_id == tid, Call.call_id.in_(ids[i:i + 500])))).all()
        out.update({str(cid): str(agent) for cid, agent in rows})
    return out


async def lead_sources(session, tid: uuid.UUID, lead_ids: list) -> dict[str, str]:
    """Where each lead came from: the call that produced it (inbound, outbound or campaign)."""
    if not lead_ids:
        return {}
    source_call: dict[str, str] = {}
    for i in range(0, len(lead_ids), 500):
        rows = (await session.execute(select(LeadAssessment.lead_id, LeadAssessment.source_call_id).where(
            LeadAssessment.tenant_id == tid, LeadAssessment.lead_id.in_(lead_ids[i:i + 500])))).all()
        source_call.update({str(lid): str(cid) for lid, cid in rows if cid})
    valid = {}
    for lid, cid in source_call.items():
        try:
            valid[lid] = uuid.UUID(cid)
        except ValueError:
            continue
    calls: dict[str, tuple[str, Any]] = {}
    ids = list(set(valid.values()))
    for i in range(0, len(ids), 500):
        rows = (await session.execute(select(Call.call_id, Call.direction, Call.campaign_id).where(
            Call.tenant_id == tid, Call.call_id.in_(ids[i:i + 500])))).all()
        calls.update({str(c): (d, camp) for c, d, camp in rows})
    out = {}
    for lid, cid in valid.items():
        found = calls.get(str(cid))
        if found:
            direction, campaign = found
            out[lid] = "campaign" if campaign else ("outbound_call" if direction == "outbound" else "inbound_call")
    return out
