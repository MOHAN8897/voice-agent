"""Tenant data exports (CSV and Excel) for calls, leads, DND, callbacks, language
callbacks, follow-ups and wallet transactions.

Every query is scoped to the caller's tenant. Phone numbers are formatted, dates are
IST, and every text cell that a spreadsheet could read as a formula is neutralised.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator

from fastapi import HTTPException
from sqlalchemy import or_, select

from server.call.call_status import normalize_call_statuses, status_for_record
from server.db.connection import get_session_factory
from server.db.models.entities import Call, CallAttempt, CallCallback
from server.db.models.followup_models import FollowUpJob, LeadAssessment
from server.db.models.language_switch_models import LanguageSwitchRequest
from server.db.models.phase5_models import DncEntry
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction, Lead
from server.services.saas.activity_feed_service import format_phone
from server.services.saas.workspace_analytics import (
    FOLLOWUP_GROUPS, IST, OUTCOMES, _call_charge_id, _call_agents, _fx, agent_names, agent_uuid,
    followup_group, lead_sources, outcome_bucket, resolve_range, tenant_uuid, wallet_amount,
)

#: Most rows one export returns. The console says so next to the row count.
MAX_ROWS = 50_000
#: Rows read before Python-side filters (tags on SQLite, outcomes) narrow them.
_SCAN_LIMIT = 200_000
DATASETS = ("calls", "leads", "dnc", "callbacks", "language_callbacks", "followups", "wallet")
#: Wallet history is billing data; everything else is call data.
PERMISSIONS = {"wallet": "app.billing.read"}
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

OUTCOME_LABELS = {"answered": "Answered", "no_answer": "No answer", "busy": "Busy", "declined": "Declined",
                  "unreachable": "Unreachable", "failed": "Failed", "voicemail": "Voicemail",
                  "in_progress": "In progress"}
SOURCE_LABELS = {"inbound_call": "Inbound call", "outbound_call": "Outbound call", "campaign": "Campaign",
                 "ai_call": "AI employee", "manual": "Added by hand"}


def safe_cell(value: Any) -> Any:
    """Prefix text a spreadsheet would run as a formula with a quote; numbers pass through."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def humanize(token: Any) -> str:
    text = str(token or "").strip().replace("_", " ").replace("-", " ")
    return text[:1].upper() + text[1:] if text else ""


def tag_label(tag: str) -> str:
    raw = str(tag or "").strip()
    _, _, value = raw.partition(":")
    return humanize(value or raw)


def ist_text(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST).strftime("%Y-%m-%d %H:%M")


def phone_text(value: Any) -> str:
    return format_phone(value) or ""


def _csv_list(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


class Filters:
    """Query filters shared by every dataset; each dataset reads the ones it supports."""

    def __init__(self, *, range: str | None = None, since: str | None = None, until: str | None = None,
                 agentId: str | None = None, status: str | None = None, outcome: str | None = None,
                 direction: str | None = None, tags: str | None = None, tagMatch: str = "any",
                 stage: str | None = None, source: str | None = None, language: str | None = None,
                 kind: str | None = None) -> None:
        self.has_dates = bool(range or since or until)
        self.start, self.end, _ = resolve_range(range or "30d", since, until) if self.has_dates else (None, None, [])
        self.agent = agent_uuid(agentId)
        self.statuses = _csv_list(status)
        self.outcomes = [o for o in _csv_list(outcome) if o in OUTCOMES]
        self.direction = direction if direction in ("inbound", "outbound") else None
        self.tags = _csv_list(tags)
        self.tag_match = "all" if tagMatch == "all" else "any"
        self.stages = _csv_list(stage)
        self.sources = _csv_list(source)
        self.languages = _csv_list(language)
        self.kinds = _csv_list(kind)

    def window(self, stmt, column):
        if self.start is not None:
            stmt = stmt.where(column >= self.start, column < self.end)
        return stmt

    def tag_ok(self, tags: list[str] | None) -> bool:
        if not self.tags:
            return True
        have = {str(t) for t in tags or []}
        return set(self.tags) <= have if self.tag_match == "all" else bool(set(self.tags) & have)


def _postgres(session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


# --- datasets ---------------------------------------------------------------------------
# Each returns (columns, rows): columns are (header, kind) and rows are lists of values.

async def _calls(session, tid, f: Filters, names) -> tuple[list, list]:
    wanted = set(normalize_call_statuses(f.statuses))
    stmt = select(Call.call_id, Call.agent_id, Call.direction, Call.started_at, Call.ended_at, Call.duration_sec,
                  Call.status, Call.end_reason, Call.disposition, Call.status_tags).where(
        Call.tenant_id == tid, Call.is_test.is_(False))
    stmt = f.window(stmt, Call.started_at)
    if f.agent:
        stmt = stmt.where(Call.agent_id == f.agent)
    if f.direction:
        stmt = stmt.where(Call.direction == f.direction)
    if wanted:
        # Pre-status rows (NULL) are classified below with the same rules.
        stmt = stmt.where(or_(Call.status.in_(wanted), Call.status.is_(None)))
    if f.tags and _postgres(session):
        stmt = stmt.where(Call.status_tags.contains(f.tags) if f.tag_match == "all" else Call.status_tags.overlap(f.tags))
    items = []
    for row in (await session.execute(stmt.order_by(Call.started_at.desc()).limit(_SCAN_LIMIT))).all():
        record = dict(row._mapping)
        status = status_for_record(record)
        bucket = outcome_bucket(status, row.direction, row.end_reason)
        if (wanted and status not in wanted) or (f.outcomes and bucket not in f.outcomes) or not f.tag_ok(row.status_tags):
            continue
        items.append({**record, "status": status, "outcome": bucket, "attempt": False})
    if not f.tags:
        # Never-connected attempts have no transcript, so a tag filter never matches them.
        attempts = select(CallAttempt.attempt_id, CallAttempt.agent_id, CallAttempt.direction, CallAttempt.started_at,
                          CallAttempt.ended_at, CallAttempt.status, CallAttempt.end_reason, CallAttempt.policy_reason,
                          CallAttempt.from_number, CallAttempt.to_number).where(
            CallAttempt.tenant_id == tid, CallAttempt.linked_call_id.is_(None))
        attempts = f.window(attempts, CallAttempt.started_at)
        if f.agent:
            attempts = attempts.where(CallAttempt.agent_id == f.agent)
        if f.direction:
            attempts = attempts.where(CallAttempt.direction == f.direction)
        if wanted:
            attempts = attempts.where(CallAttempt.status.in_(wanted))
        for row in (await session.execute(attempts.order_by(CallAttempt.started_at.desc()).limit(_SCAN_LIMIT))).all():
            bucket = outcome_bucket(row.status, row.direction, row.end_reason, row.policy_reason)
            if f.outcomes and bucket not in f.outcomes:
                continue
            outbound = row.direction == "outbound"
            items.append({"call_id": row.attempt_id, "agent_id": row.agent_id, "direction": row.direction,
                          "started_at": row.started_at, "ended_at": row.ended_at, "duration_sec": 0,
                          "status": row.status, "outcome": bucket, "disposition": None, "status_tags": [],
                          "attempt": True, "contact": row.to_number if outbound else row.from_number,
                          "line": row.from_number if outbound else row.to_number})
    items.sort(key=lambda i: i["started_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    columns = [("Started (IST)", "date"), ("Direction", "text"), ("Agent", "text"), ("Contact number", "phone"),
               ("Our number", "phone"), ("Outcome", "text"), ("Status", "text"), ("Duration (seconds)", "number"),
               ("Disposition", "text"), ("Tags", "text"), ("Call reference", "text")]
    return columns, items


def _call_rows(items: list[dict], tid: uuid.UUID, names: dict) -> list[list]:
    from server.routes.calls import _ledger_contact

    rows = []
    for i in items:
        contact, line = i.get("contact"), i.get("line")
        if not i["attempt"]:
            ledger_tenant, caller, callee = _ledger_contact(str(i["call_id"]))
            if ledger_tenant == str(tid):
                outbound = i.get("direction") == "outbound"
                contact, line = (callee, caller) if outbound else (caller, callee)
        rows.append([ist_text(i["started_at"]), humanize(i.get("direction") or "inbound"),
                     names.get(str(i.get("agent_id")), ""), phone_text(contact), phone_text(line),
                     OUTCOME_LABELS.get(i["outcome"], humanize(i["outcome"])), humanize(i["status"]),
                     int(i.get("duration_sec") or 0), humanize(i.get("disposition")),
                     ", ".join(tag_label(t) for t in i.get("status_tags") or []), str(i["call_id"])])
    return rows


async def _leads(session, tid, f: Filters, names):
    stmt = select(Lead).where(Lead.tenant_id == tid)
    stmt = f.window(stmt, Lead.created_at)
    if f.agent:
        stmt = stmt.where(Lead.agent_id == str(f.agent))
    if f.stages:
        stmt = stmt.where(Lead.stage.in_(f.stages))
    leads = list((await session.execute(stmt.order_by(Lead.created_at.desc()).limit(_SCAN_LIMIT))).scalars())
    sources = await lead_sources(session, tid, [lead.lead_id for lead in leads])
    tags_by_lead = await _lead_tags(session, tid, [lead.lead_id for lead in leads])
    rows = []
    for lead in leads:
        source = sources.get(str(lead.lead_id)) or ("ai_call" if lead.agent_id else "manual")
        tags = tags_by_lead.get(str(lead.lead_id), [])
        if (f.sources and source not in f.sources) or not f.tag_ok(tags):
            continue
        rows.append([ist_text(lead.created_at), lead.name, phone_text(lead.phone), lead.email or "",
                     humanize(lead.stage), SOURCE_LABELS.get(source, humanize(source)),
                     names.get(str(lead.agent_id or ""), ""), ", ".join(tag_label(t) for t in tags),
                     ist_text(lead.updated_at), lead.notes or ""])
    columns = [("Created (IST)", "date"), ("Name", "text"), ("Phone", "phone"), ("Email", "text"), ("Stage", "text"),
               ("Source", "text"), ("Agent", "text"), ("Tags", "text"), ("Updated (IST)", "date"), ("Notes", "text")]
    return columns, rows


async def _lead_tags(session, tid, lead_ids: list) -> dict[str, list[str]]:
    """A lead's tags are the tags on the call that produced it."""
    pairs: dict[str, uuid.UUID] = {}
    for i in range(0, len(lead_ids), 500):
        for lid, cid in (await session.execute(select(LeadAssessment.lead_id, LeadAssessment.source_call_id).where(
                LeadAssessment.tenant_id == tid, LeadAssessment.lead_id.in_(lead_ids[i:i + 500])))).all():
            try:
                pairs[str(lid)] = uuid.UUID(str(cid))
            except ValueError:
                continue
    tags: dict[str, list[str]] = {}
    ids = list(set(pairs.values()))
    for i in range(0, len(ids), 500):
        for cid, call_tags in (await session.execute(select(Call.call_id, Call.status_tags).where(
                Call.tenant_id == tid, Call.call_id.in_(ids[i:i + 500])))).all():
            tags[str(cid)] = list(call_tags or [])
    return {lid: tags.get(str(cid), []) for lid, cid in pairs.items()}


async def _dnc(session, tid, f: Filters, names):
    stmt = select(DncEntry).where(DncEntry.tenant_id == tid)
    stmt = f.window(stmt, DncEntry.added_at)
    if f.sources:
        stmt = stmt.where(DncEntry.source.in_(f.sources))
    status = (f.statuses or ["active"])[0]
    if status == "active":
        stmt = stmt.where(DncEntry.active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(DncEntry.active.is_(False))
    rows = [[ist_text(r.added_at), phone_text(r.phone_e164), humanize(r.source or "manual"), r.reason or "",
             "Active" if r.active else "Removed", ist_text(r.removed_at), r.removal_reason or ""]
            for r in (await session.execute(stmt.order_by(DncEntry.added_at.desc()).limit(_SCAN_LIMIT))).scalars()]
    columns = [("Added (IST)", "date"), ("Phone", "phone"), ("Source", "text"), ("Reason", "text"),
               ("Status", "text"), ("Removed (IST)", "date"), ("Removal reason", "text")]
    return columns, rows


async def _callbacks(session, tid, f: Filters, names):
    from server.call.call_ledger import call_ledger

    stmt = select(CallCallback).where(CallCallback.tenant_id == tid, CallCallback.mode == "requested")
    stmt = f.window(stmt, CallCallback.created_at)
    if f.agent:
        stmt = stmt.where(CallCallback.agent_id == str(f.agent))
    if f.statuses:
        stmt = stmt.where(CallCallback.status.in_(f.statuses))
    rows = []
    for r in (await session.execute(stmt.order_by(CallCallback.created_at.desc()).limit(_SCAN_LIMIT))).scalars():
        meta = (call_ledger.read_meta(str(r.original_call_id)) or {}) if r.original_call_id else {}
        details = meta.get("callback_request") if isinstance(meta.get("callback_request"), dict) else {}
        rows.append([ist_text(r.created_at), phone_text(r.to_e164), names.get(str(r.agent_id), ""),
                     "Pending" if r.status == "requested" else humanize(r.status),
                     str(details.get("requestedWhen") or ""), str(details.get("requestText") or ""),
                     str(r.original_call_id or "")])
    columns = [("Requested (IST)", "date"), ("Phone", "phone"), ("Agent", "text"), ("Status", "text"),
               ("Asked for", "text"), ("Caller's words", "text"), ("Call reference", "text")]
    return columns, rows


async def _language_callbacks(session, tid, f: Filters, names):
    from server.call.language_switch import language_name

    stmt = select(LanguageSwitchRequest).where(LanguageSwitchRequest.tenant_id == tid)
    stmt = f.window(stmt, LanguageSwitchRequest.created_at)
    if f.agent:
        stmt = stmt.where(LanguageSwitchRequest.agent_id == str(f.agent))
    if f.statuses:
        stmt = stmt.where(LanguageSwitchRequest.status.in_(f.statuses))
    if f.languages:
        stmt = stmt.where(LanguageSwitchRequest.requested_language.in_(f.languages))
    rows = [[ist_text(r.created_at), r.contact_name or "", phone_text(r.phone_e164), names.get(str(r.agent_id), ""),
             language_name(r.requested_language), language_name(r.original_language), humanize(r.status),
             ist_text(r.completed_at), r.request_text or ""]
            for r in (await session.execute(stmt.order_by(LanguageSwitchRequest.created_at.desc()).limit(_SCAN_LIMIT))).scalars()]
    columns = [("Requested (IST)", "date"), ("Name", "text"), ("Phone", "phone"), ("Agent", "text"),
               ("Requested language", "text"), ("Call language", "text"), ("Status", "text"),
               ("Completed (IST)", "date"), ("Caller's words", "text")]
    return columns, rows


async def _followups(session, tid, f: Filters, names):
    stmt = select(FollowUpJob).where(FollowUpJob.tenant_id == tid)
    stmt = f.window(stmt, FollowUpJob.created_at)
    if f.agent:
        stmt = stmt.where(FollowUpJob.agent_id == f.agent)
    if f.kinds:
        stmt = stmt.where(FollowUpJob.kind.in_(f.kinds))
    groups = [s for s in f.statuses if s in FOLLOWUP_GROUPS]
    exact = [s for s in f.statuses if s not in FOLLOWUP_GROUPS]
    rows = []
    for r in (await session.execute(stmt.order_by(FollowUpJob.created_at.desc()).limit(_SCAN_LIMIT))).scalars():
        group = followup_group(r.status, r.reason)
        if f.statuses and group not in groups and r.status not in exact:
            continue
        rows.append([ist_text(r.created_at), humanize(r.kind), phone_text(r.phone), names.get(str(r.agent_id), ""),
                     humanize(group), humanize(r.status), humanize(r.reason), ist_text(r.due_at), int(r.attempts or 0)])
    columns = [("Created (IST)", "date"), ("Kind", "text"), ("Phone", "phone"), ("Agent", "text"), ("Result", "text"),
               ("Status", "text"), ("Reason", "text"), ("Due (IST)", "date"), ("Attempts", "number")]
    return columns, rows


async def _wallet(session, tid, f: Filters, names):
    wallet = await session.get(BillingWallet, tid)
    currency = (wallet.currency if wallet else "usd").upper()
    fx = _fx()
    stmt = select(BillingWalletTransaction).where(BillingWalletTransaction.tenant_id == tid)
    stmt = f.window(stmt, BillingWalletTransaction.created_at)
    if f.kinds:
        stmt = stmt.where(BillingWalletTransaction.kind.in_(f.kinds))
    txs = list((await session.execute(stmt.order_by(BillingWalletTransaction.created_at.desc()).limit(_SCAN_LIMIT))).scalars())
    owners = await _call_agents(session, tid, {c for c in (_call_charge_id(t.reference_id) for t in txs) if c})
    rows = []
    for t in txs:
        cid = _call_charge_id(t.reference_id)
        owner = owners.get(cid) if cid else None
        if f.agent and owner != str(f.agent):
            continue
        rows.append([ist_text(t.created_at), humanize(t.kind), wallet_amount(t.amount_cents, t.amount_inr_paise, currency, fx),
                     currency, names.get(owner or "", ""), cid or ""])
    columns = [("Date (IST)", "date"), ("Type", "text"), ("Amount", "number"), ("Currency", "text"),
               ("Agent", "text"), ("Call reference", "text")]
    return columns, rows


_LOADERS = {"calls": _calls, "leads": _leads, "dnc": _dnc, "callbacks": _callbacks,
            "language_callbacks": _language_callbacks, "followups": _followups, "wallet": _wallet}


async def collect(dataset: str, tenant_id: Any, filters: Filters, *, details: bool = True) -> dict[str, Any]:
    """Rows for one dataset, capped at ``MAX_ROWS``. ``details=False`` skips per-call ledger reads (row counts)."""
    if dataset not in _LOADERS:
        raise HTTPException(404, "Unknown export")
    tid = tenant_uuid(tenant_id)
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(503, "Exports need the database")
    async with factory() as session:
        names = await agent_names(session, tid)
        if filters.agent and str(filters.agent) not in names:
            raise HTTPException(404, "Agent not found")
        columns, rows = await _LOADERS[dataset](session, tid, filters, names)
    total = len(rows)
    rows = rows[:MAX_ROWS]
    if dataset == "calls" and details:
        import asyncio
        rows = await asyncio.to_thread(_call_rows, rows, tid, names)
    return {"columns": columns, "rows": rows, "total": total, "capped": total > MAX_ROWS}


def csv_chunks(columns: list, rows: list) -> Iterator[str]:
    """CSV text in chunks, with a BOM so Excel reads Indian-language names as UTF-8."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    buffer.write("﻿")
    writer.writerow([safe_cell(h) for h, _ in columns])
    for index, row in enumerate(rows, 1):
        writer.writerow([safe_cell(v) for v in row])
        if index % 1000 == 0:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
    yield buffer.getvalue()


def xlsx_bytes(columns: list, rows: list, sheet: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font

    book = Workbook(write_only=True)
    ws = book.create_sheet(sheet[:31] or "Export")
    bold = Font(bold=True)
    header = []
    for title, _ in columns:
        cell = WriteOnlyCell(ws, value=safe_cell(title))
        cell.font = bold
        header.append(cell)
    ws.append(header)
    for row in rows:
        out = []
        for value in row:
            # Typed as a string, "+91 93982 47132" or "=x" is stored as text and never
            # evaluated, so Excel shows the value as-is; only CSV needs the quote prefix.
            cell = WriteOnlyCell(ws, value=value)
            if isinstance(value, str):
                cell.data_type = "s"
            out.append(cell)
        ws.append(out)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def filename(dataset: str, fmt: str) -> str:
    stamp = datetime.now(timezone.utc).astimezone(IST).strftime("%Y%m%d-%H%M")
    return f"dialtact-{dataset.replace('_', '-')}-{stamp}.{fmt}"
