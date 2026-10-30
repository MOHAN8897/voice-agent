"""Tenant activity feed: one stream of what the workspace's AI employees are doing.

The console home renders this as a live feed ("Meera is on a call with Ravi",
"Hima booked a site visit", "Call to +91 98765 43123 needs a callback in Hindi"). Nothing
here is new data: every item is derived from rows the platform already writes
(calls, ringing attempts, callback requests, follow-up jobs, language-switch
requests, leads, campaigns, tool executions, wallet transactions, phone numbers,
channel events, integration status).

Rules this module keeps:

* **Tenant isolation.** Every query filters on the workspace tenant id first.
* **Bounded work.** Each source is read with ``LIMIT limit + 1`` below the cursor,
  merged in memory, and only the returned page is enriched from the call ledger
  (summary, recording flag, contact name), so a page costs a fixed number of
  queries regardless of history size — no per-item queries.
* **No internal vocabulary.** Items carry a plain-language sentence. Raw tags,
  dispositions and end reasons never reach the client as text.
* **Readable numbers.** Contact numbers are the tenant's own customers, so they are
  shown in full but formatted (``+91 98765 43123``), never as raw digit strings.
  Dial actions reference the call or request id, never the number.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import func, or_, select

from server.db.connection import get_session_factory

logger = logging.getLogger(__name__)

FILTERS = ("all", "needs_action", "calls", "leads", "campaigns", "system")
DEFAULT_LIMIT = 30
MAX_LIMIT = 60
#: A call open longer than this is a stale row, not a live call.
LIVE_MAX_AGE = timedelta(hours=2)
#: A ringing attempt older than this without an answer is not "ringing now".
RINGING_MAX_AGE = timedelta(minutes=3)
#: Wallet at or below this (paise) is "low"; at or below zero is "empty".
LOW_WALLET_INR_PAISE = 20_000
LOW_WALLET_USD_CENTS = 200
PINNED_CAP = 25

#: Which item categories each filter shows. Sources outside these are not queried.
_FILTER_SOURCES: dict[str, frozenset[str]] = {
    "all": frozenset({"calls", "attempts", "callbacks", "followups", "language", "leads", "campaigns",
                      "tools", "wallet", "channels", "numbers"}),
    "calls": frozenset({"calls", "attempts", "callbacks", "followups", "language"}),
    "leads": frozenset({"calls_booked", "leads"}),
    "campaigns": frozenset({"campaigns"}),
    "system": frozenset({"tools", "wallet", "channels", "numbers"}),
    "needs_action": frozenset(),
}

_TOPUP_KINDS = ("topup", "razorpay_topup_inr", "razorpay_topup", "admin_grant")
_RENT_KINDS = ("did_rental",)
_REFUND_KINDS = ("did_refund",)
_TECHNICAL_REASONS = frozenset({"technical_fallback", "technical_failure"})
_POSITIVE_DISPOSITIONS = frozenset({"qualified", "interested", "converted", "new_lead", "site_visit_planned"})
_QUALIFIED_STAGES = frozenset({"qualified", "converted", "meeting_booked"})

_DISPOSITION_LABEL = {
    "new_lead": "New lead",
    "interested": "Interested",
    "qualified": "Qualified",
    "site_visit_planned": "Site visit planned",
    "callback_required": "Wants a callback",
    "not_interested": "Not interested",
    "wrong_number": "Wrong number",
    "converted": "Converted",
    "no_outcome": "No clear outcome",
}

_APP_LABEL = {
    "google-calendar": "Google Calendar", "google_calendar": "Google Calendar", "googlecalendar": "Google Calendar",
    "calendly": "Calendly", "todoist": "Todoist", "hubspot": "HubSpot", "zoho-crm": "Zoho CRM", "zoho": "Zoho",
    "salesforce": "Salesforce", "slack": "Slack", "gmail": "Gmail", "google-sheet": "Google Sheets",
    "google-sheets": "Google Sheets", "notion": "Notion", "pipedrive": "Pipedrive", "airtable": "Airtable",
    "whatsapp": "WhatsApp", "zendesk": "Zendesk", "freshdesk": "Freshdesk", "trello": "Trello", "asana": "Asana",
}


# -- Small helpers ---------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    value = _utc(value)
    return value.isoformat() if value else None


def format_phone(value: Any) -> str | None:
    """Format a contact number for display: ``+919398247132`` → ``+91 93982 47132``.

    These are the tenant's own customers, so console users get the full number;
    raw digit strings are always grouped. Mirrors ``dialtact-app/src/lib/phoneMask.js``.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return raw
    if len(digits) < 7:
        return digits
    plus = raw.startswith("+")
    # Indian numbers arrive as +91XXXXXXXXXX, 91XXXXXXXXXX or a bare 10-digit mobile.
    if digits.startswith("91") and len(digits) == 12 and (plus or digits[2] in "6789"):
        local = digits[2:]
        return f"+91 {local[:5]} {local[5:]}"
    if not plus and len(digits) == 10 and digits[0] in "6789":
        return f"+91 {digits[:5]} {digits[5:]}"
    # Indian landline with trunk zero, e.g. 04023456789.
    if not plus and len(digits) == 11 and digits[0] == "0":
        return f"+91 {digits[1:3]} {digits[3:7]} {digits[7:]}"
    if plus and digits.startswith("1") and len(digits) == 11:
        return f"+1 {digits[1:4]} {digits[4:7]} {digits[7:]}"
    groups: list[str] = []
    rest = digits
    while len(rest) > 4:
        groups.append(rest[:3])
        rest = rest[3:]
    if rest:
        groups.append(rest)
    return ("+" if plus else "") + " ".join(groups)


# Kept for old imports; numbers are no longer masked for tenant users.
mask_phone = format_phone


def _as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def money_inr(paise: int | None) -> str:
    rupees = (int(paise or 0)) / 100
    whole = abs(rupees) == int(abs(rupees))
    text = f"{abs(rupees):,.0f}" if whole else f"{abs(rupees):,.2f}"
    return f"₹{_indian_grouping(text)}"


def _indian_grouping(text: str) -> str:
    """1,234,567.50 → 12,34,567.50 (lakh grouping)."""
    number, _, frac = text.replace(",", "").partition(".")
    if len(number) > 3:
        head, tail = number[:-3], number[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        number = ",".join(groups + [tail])
    return f"{number}.{frac}" if frac else number


def _duration_label(seconds: Any) -> str | None:
    try:
        total = int(seconds or 0)
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return None
    minutes, secs = divmod(total, 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _app_label(app: Any) -> str:
    key = str(app or "").strip().lower()
    if key in _APP_LABEL:
        return _APP_LABEL[key]
    return key.replace("-", " ").replace("_", " ").strip().title() or "An integration"


def _tool_phrase(action: str, succeeded: bool) -> str:
    """Plain words for a tool action name such as ``google_calendar.create_event``."""
    name = str(action or "").lower()
    if "calendar" in name or "event" in name or "booking" in name or "calendly" in name:
        noun, verb = "a calendar event", "added"
    elif "todoist" in name or "task" in name:
        noun, verb = "a task", "created"
    elif "hubspot" in name or "contact" in name or "crm" in name or "lead" in name:
        noun, verb = "a CRM contact", "saved"
    elif "sheet" in name or "row" in name:
        noun, verb = "a spreadsheet row", "added"
    elif "email" in name or "gmail" in name or "mail" in name:
        noun, verb = "an email", "sent"
    elif "slack" in name or "message" in name or "whatsapp" in name:
        noun, verb = "a message", "sent"
    else:
        noun, verb = "an integration action", "completed"
    if succeeded:
        return f"{verb} {noun}"
    return {"added": "couldn't add", "created": "couldn't create", "saved": "couldn't save",
            "sent": "couldn't send", "completed": "couldn't complete"}[verb] + f" {noun}"


def _tool_app(action: str) -> str | None:
    name = str(action or "")
    for sep in (".", "__", ":"):
        if sep in name:
            head = name.split(sep, 1)[0]
            return _app_label(head) if head else None
    return None


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def encode_cursor(at: datetime, key: str) -> str:
    stamp = (_utc(at) - _EPOCH) // timedelta(microseconds=1)
    return f"{stamp}_{key}"


def decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    stamp, _, key = str(cursor).partition("_")
    try:
        return _EPOCH + timedelta(microseconds=int(stamp)), key
    except (TypeError, ValueError, OverflowError):
        return None


def _item(*, key: str, type_: str, category: str, at: datetime | None, tone: str, actor: str | None,
          text: str, agent_id: Any = None, detail: str | None = None, contact: dict | None = None,
          needs_action: bool = False, actions: list[dict] | None = None, refs: dict | None = None,
          meta: dict | None = None) -> dict[str, Any]:
    return {
        "id": key,
        "type": type_,
        "category": category,
        "at": _iso(at),
        "_at": _utc(at) or _now(),
        "tone": tone,
        "actor": actor,
        "text": text,
        "detail": detail,
        "agentId": str(agent_id) if agent_id else None,
        "contact": contact or None,
        "needsAction": needs_action,
        "actions": actions or [],
        "refs": refs or {},
        "meta": meta or {},
    }


def _contact(name: Any = None, phone: Any = None) -> dict[str, Any]:
    clean = str(name or "").strip() or None
    # Some records store the number itself as the name; show it formatted, not as raw digits.
    if clean and sum(ch.isdigit() for ch in clean) >= 7 and not any(ch.isalpha() for ch in clean):
        formatted = format_phone(phone) or format_phone(clean)
        return {"name": None, "phone": formatted}
    formatted = format_phone(phone)
    return {"name": clean, "phone": formatted}


def _who(contact: dict | None, fallback: str = "a caller") -> str:
    if not contact:
        return fallback
    return contact.get("name") or contact.get("phone") or fallback


# -- Models (imported lazily so the module imports without a database) -------------------

def _models():
    from server.db.models.concurrency_models import TenantChannelEvent, TenantChannelSubscription
    from server.db.models.entities import Agent, Call, CallAttempt, CallCallback
    from server.db.models.followup_models import FollowUpJob
    from server.db.models.integration_models import TenantIntegration, ToolExecution
    from server.db.models.language_switch_models import LanguageSwitchRequest
    from server.db.models.phase5_models import Campaign, CampaignContact, CampaignRun, PhoneNumber
    from server.db.models.saas_models import BillingWallet, BillingWalletTransaction, Lead

    return {
        "Agent": Agent, "Call": Call, "CallAttempt": CallAttempt, "CallCallback": CallCallback,
        "FollowUpJob": FollowUpJob, "TenantIntegration": TenantIntegration, "ToolExecution": ToolExecution,
        "LanguageSwitchRequest": LanguageSwitchRequest, "Campaign": Campaign, "CampaignContact": CampaignContact,
        "CampaignRun": CampaignRun, "PhoneNumber": PhoneNumber, "BillingWallet": BillingWallet,
        "BillingWalletTransaction": BillingWalletTransaction, "Lead": Lead,
        "TenantChannelEvent": TenantChannelEvent, "TenantChannelSubscription": TenantChannelSubscription,
    }


def _language_name(code: Any) -> str:
    try:
        from server.call.language_switch import language_name

        return language_name(str(code or "")) or str(code or "another language")
    except Exception:  # noqa: BLE001 -- a label must never break the feed.
        return str(code or "another language")


def _call_status(row: Any) -> str:
    try:
        from server.call.call_status import status_for_record

        return status_for_record({
            "status": row.status, "direction": row.direction, "duration_sec": getattr(row, "duration_sec", None),
            "end_reason": row.end_reason, "disposition": getattr(row, "disposition", None),
            "ended_at": row.ended_at,
        })
    except Exception:  # noqa: BLE001
        return str(row.status or "answered")


# -- Ledger enrichment (page only, off the event loop) -------------------------------------

def _ledger_details(call_id: str, tenant_id: str) -> dict[str, Any]:
    """Contact, summary, recording flag and booking time for one call on the returned page."""
    out: dict[str, Any] = {}
    try:
        from server.call.call_ledger import call_ledger

        meta = call_ledger.read_meta(call_id) or {}
    except Exception:  # noqa: BLE001
        meta = {}
    if meta and str(meta.get("tenant_id") or "") == tenant_id:
        outbound = str(meta.get("direction") or "") == "outbound"
        out["phone"] = (meta.get("callee_e164") or meta.get("to_number")) if outbound else (
            meta.get("caller_id") or meta.get("from_number"))
        contact = meta.get("contact") if isinstance(meta.get("contact"), dict) else {}
        name = contact.get("full_name") or contact.get("name") or " ".join(
            str(contact.get(k) or "") for k in ("first_name", "last_name")).strip()
        if name:
            out["name"] = str(name)[:120]
        request = meta.get("callback_request") if isinstance(meta.get("callback_request"), dict) else {}
        if request.get("requestedWhen"):
            out["requested_when"] = str(request["requestedWhen"])[:160]
        if isinstance(request.get("resolvedWindow"), dict):
            out["resolved_window"] = request["resolvedWindow"]
    try:
        from server.call.post_call_pipeline import read_outcome
        from server.call.outcome_schema import normalize_extracted_fields

        outcome = read_outcome(call_id) or {}
        summary = str(outcome.get("summary_en") or "").strip()
        if summary:
            # The whole summary; the feed row clamps it visually with a More toggle.
            out["summary"] = summary
        fields = normalize_extracted_fields(outcome.get("extracted_fields"))
        if not out.get("name") and (fields.get("name") or "").strip():
            out["name"] = fields["name"].strip()[:120]
        for key, value in fields.items():
            k = key.lower()
            if value and any(word in k for word in ("visit", "appointment", "booking", "meeting")) and any(
                    word in k for word in ("time", "date", "when", "slot", "at")):
                out["booked_for"] = str(value).strip()[:80]
                break
    except Exception:  # noqa: BLE001
        pass
    try:
        from server.call.audio_archive import audio_archive

        out["has_recording"] = audio_archive.recording_source(call_id) != "none"
    except Exception:  # noqa: BLE001
        out["has_recording"] = False
    return out


async def _enrich_calls(items: list[dict[str, Any]], tenant_id: str) -> None:
    targets = [i for i in items if i.get("refs", {}).get("callId") and i.get("_enrich")]
    if not targets:
        return

    def work() -> dict[str, dict[str, Any]]:
        return {i["refs"]["callId"]: _ledger_details(i["refs"]["callId"], tenant_id) for i in targets}

    try:
        details = await asyncio.to_thread(work)
    except Exception:  # noqa: BLE001
        return
    for item in targets:
        info = details.get(item["refs"]["callId"]) or {}
        renderer = item.get("_enrich")
        try:
            renderer(item, info)
        except Exception:  # noqa: BLE001
            logger.debug("activity_feed.enrich_failed type=%s", item.get("type"))


# -- Call items --------------------------------------------------------------------------

def _call_item(row: Any, agent_names: dict[str, str]) -> dict[str, Any]:
    tags = set(row.status_tags or [])
    status = _call_status(row)
    actor = agent_names.get(str(row.agent_id))
    end_reason = str(row.end_reason or "").lower()
    disposition = str(row.disposition or "").lower()
    duration = _duration_label(row.duration_sec)
    call_id = str(row.call_id)
    base_actions = [{"kind": "open_call", "label": "Open call", "callId": call_id}]
    refs = {"callId": call_id, "campaignId": str(row.campaign_id) if row.campaign_id else None}
    meta = {"duration": duration, "direction": row.direction, "outcome": _DISPOSITION_LABEL.get(disposition)}

    if end_reason in _TECHNICAL_REASONS:
        type_, tone, category = "call.technical", "danger", "calls"
    elif "signal:do_not_call" in tags or end_reason == "opt_out":
        type_, tone, category = "call.dnd", "neutral", "calls"
    elif disposition == "site_visit_planned" or "followup:site_visit" in tags or (
            "intent:booking" in tags and disposition in ("qualified", "converted")):
        type_, tone, category = "call.booked", "success", "leads"
    elif status in ("missed", "declined", "voicemail", "failed"):
        type_, tone, category = "call.missed", "warning", "calls"
    else:
        type_, tone, category = "call.completed", ("success" if disposition in _POSITIVE_DISPOSITIONS else "neutral"), "calls"

    item = _item(key=f"call:{call_id}", type_=type_, category=category, at=row.started_at, tone=tone, actor=actor,
                 text="", agent_id=row.agent_id, refs=refs, meta=meta, actions=list(base_actions))

    def render(it: dict[str, Any], info: dict[str, Any]) -> None:
        contact = _contact(info.get("name"), info.get("phone"))
        it["contact"] = contact
        who = _who(contact)
        it["detail"] = info.get("summary")
        if info.get("has_recording"):
            it["actions"].append({"kind": "play_recording", "label": "Play recording", "callId": call_id})
        t = it["type"]
        if t == "call.technical":
            it["actor"] = None
            it["text"] = f"Call with {who} ended because of a technical issue"
            it["actions"].insert(0, {"kind": "call_back", "label": "Call back", "callId": call_id})
        elif t == "call.dnd":
            it["text"] = f"recorded a do-not-call request from {who}"
        elif t == "call.booked":
            when = info.get("booked_for")
            site_visit = disposition == "site_visit_planned" or "followup:site_visit" in tags
            visit = "a site visit" if site_visit else "an appointment"
            if site_visit or when:
                it["text"] = f"booked {visit} with {who}" + (f" for {when}" if when else "")
            else:
                # A booking intent alone is not proof that anything was booked.
                it["text"] = f"talked with {who} about booking {visit}"
        elif t == "call.missed":
            it["actor"] = None
            outbound = row.direction == "outbound"
            if status == "voicemail":
                it["text"] = f"Call {'to' if outbound else 'from'} {who} went to voicemail"
            else:
                it["text"] = f"Couldn't reach {who}" if outbound else f"Missed call from {who}"
            it["actions"].insert(0, {"kind": "call_back", "label": "Call back", "callId": call_id})
        else:
            verb = "called" if row.direction == "outbound" else "talked with"
            it["text"] = f"{verb} {who}"

    item["_enrich"] = render
    return item


def _attempt_item(row: Any, agent_names: dict[str, str]) -> dict[str, Any]:
    status = _call_status(row)
    outbound = row.direction == "outbound"
    phone = row.to_number if outbound else row.from_number
    contact = _contact(None, phone)
    who = _who(contact)
    attempt_id = str(row.attempt_id)
    from server.call.hangup_causes import outcome_for_item
    outcome = outcome_for_item({"status": status, "direction": row.direction, "end_reason": row.end_reason,
                                "policy_reason": row.policy_reason})
    if status == "voicemail":
        text = f"Call {'to' if outbound else 'from'} {who} went to voicemail"
    elif outbound:
        label = str(outcome.get("outcome_label") or "").lower()
        text = f"Couldn't reach {who}" + (f": {label}" if label and label != "failed" else "")
    else:
        text = f"Missed call from {who}"
    return _item(
        key=f"attempt:{attempt_id}", type_="call.missed", category="calls", at=row.started_at, tone="warning",
        actor=None, text=text, detail=outcome.get("outcome_reason"), agent_id=row.agent_id, contact=contact,
        actions=[{"kind": "call_back", "label": "Call back", "callId": attempt_id},
                 {"kind": "open_calls", "label": "Open calls", "status": "missed"}],
        refs={"callId": attempt_id, "attemptId": attempt_id}, meta={"direction": row.direction},
    )


def _live_item(row: Any, agent_names: dict[str, str], now: datetime) -> dict[str, Any]:
    call_id = str(row.call_id)
    item = _item(
        key=f"live:{call_id}", type_="call.live", category="calls", at=row.started_at, tone="live",
        actor=agent_names.get(str(row.agent_id)), text="is on a call", agent_id=row.agent_id,
        actions=[{"kind": "open_call", "label": "Open live transcript", "callId": call_id}],
        refs={"callId": call_id}, meta={"direction": row.direction, "startedAt": _iso(row.started_at)},
    )

    def render(it: dict[str, Any], info: dict[str, Any]) -> None:
        contact = _contact(info.get("name"), info.get("phone"))
        it["contact"] = contact
        it["text"] = f"is on a call with {_who(contact)}"

    item["_enrich"] = render
    return item


# -- Feed assembly -------------------------------------------------------------------------

async def _agent_names(session, M, tenant_id: uuid.UUID) -> dict[str, str]:
    rows = (await session.execute(select(M["Agent"].agent_id, M["Agent"].name)
                                  .where(M["Agent"].tenant_id == tenant_id))).all()
    return {str(aid): name for aid, name in rows}


def _below(column, before: datetime | None):
    return column <= before if before is not None else None


def _where(*clauses):
    return [c for c in clauses if c is not None]


async def _collect(session, M, *, tenant_id: uuid.UUID, agent: uuid.UUID | None, sources: Iterable[str],
                   before: datetime | None, fetch: int, names: dict[str, str]) -> list[dict[str, Any]]:
    sources = set(sources)
    items: list[dict[str, Any]] = []
    agent_str = str(agent) if agent else None
    Call = M["Call"]

    if sources & {"calls", "calls_booked"}:
        q = select(Call).where(*_where(Call.tenant_id == tenant_id, Call.is_test.is_(False), Call.ended_at.is_not(None),
                                       Call.agent_id == agent if agent else None, _below(Call.started_at, before)))
        if "calls" not in sources:
            q = q.where(or_(Call.disposition == "site_visit_planned", Call.disposition.in_(("qualified", "converted"))))
        rows = (await session.execute(q.order_by(Call.started_at.desc()).limit(fetch))).scalars().all()
        for row in rows:
            item = _call_item(row, names)
            if "calls" in sources or item["type"] == "call.booked":
                items.append(item)

    if "attempts" in sources:
        A = M["CallAttempt"]
        rows = (await session.execute(select(A).where(*_where(
            A.tenant_id == tenant_id, A.linked_call_id.is_(None),
            A.status.in_(("missed", "declined", "voicemail", "failed")),
            A.agent_id == agent if agent else None, _below(A.started_at, before),
        )).order_by(A.started_at.desc()).limit(fetch))).scalars().all()
        items.extend(_attempt_item(r, names) for r in rows)

    if "callbacks" in sources:
        C = M["CallCallback"]
        rows = (await session.execute(select(C).where(*_where(
            C.tenant_id == tenant_id, C.mode == "requested",
            C.agent_id == agent_str if agent_str else None, _below(C.created_at, before),
        )).order_by(C.created_at.desc()).limit(fetch))).scalars().all()
        items.extend(_callback_item(r, names) for r in rows)

    if "followups" in sources:
        F = M["FollowUpJob"]
        rows = (await session.execute(select(F).where(*_where(
            F.tenant_id == tenant_id, F.status.in_(("needs_review", "scheduled", "dialed", "completed")),
            F.agent_id == agent if agent else None, _below(F.updated_at, before),
        )).order_by(F.updated_at.desc()).limit(fetch))).scalars().all()
        items.extend(_followup_item(r, names) for r in rows)

    if "language" in sources:
        L = M["LanguageSwitchRequest"]
        rows = (await session.execute(select(L).where(*_where(
            L.tenant_id == tenant_id, L.status != "dismissed",
            L.agent_id == agent_str if agent_str else None, _below(L.updated_at, before),
        )).order_by(L.updated_at.desc()).limit(fetch))).scalars().all()
        items.extend(_language_item(r, names) for r in rows)

    if "leads" in sources:
        Lead = M["Lead"]
        rows = (await session.execute(select(Lead).where(*_where(
            Lead.tenant_id == tenant_id, Lead.agent_id == agent_str if agent_str else None,
            _below(Lead.updated_at, before),
        )).order_by(Lead.updated_at.desc()).limit(fetch))).scalars().all()
        items.extend(_lead_item(r, names) for r in rows)

    if "campaigns" in sources:
        items.extend(await _campaign_items(session, M, tenant_id=tenant_id, agent=agent, before=before,
                                           fetch=fetch, names=names))

    if "tools" in sources:
        T = M["ToolExecution"]
        rows = (await session.execute(select(T).where(*_where(
            T.tenant_id == tenant_id, T.action_type == "write",
            T.status.in_(("succeeded", "failed", "timed_out_pending")),
            T.agent_id == agent if agent else None, _below(T.started_at, before),
        )).order_by(T.started_at.desc()).limit(fetch))).scalars().all()
        items.extend(_tool_item(r, names) for r in rows)

    if "numbers" in sources:
        P = M["PhoneNumber"]
        rows = (await session.execute(select(P).where(*_where(
            P.tenant_id == tenant_id, P.released_at.is_(None),
            P.agent_id == agent if agent else None, _below(P.created_at, before),
        )).order_by(P.created_at.desc()).limit(fetch))).scalars().all()
        items.extend(_number_item(r, names) for r in rows)

    if agent is None and "wallet" in sources:
        W = M["BillingWalletTransaction"]
        rows = (await session.execute(select(W).where(*_where(
            W.tenant_id == tenant_id, W.kind.in_((*_TOPUP_KINDS, *_RENT_KINDS, *_REFUND_KINDS)),
            _below(W.created_at, before),
        )).order_by(W.created_at.desc()).limit(fetch))).scalars().all()
        items.extend(i for i in (_wallet_item(r) for r in rows) if i)

    if agent is None and "channels" in sources:
        E = M["TenantChannelEvent"]
        rows = (await session.execute(select(E).where(*_where(
            E.tenant_id == tenant_id, E.kind.in_(("purchase", "renewal", "renewal_failed", "lapsed", "downgrade_applied")),
            _below(E.created_at, before),
        )).order_by(E.created_at.desc()).limit(fetch))).scalars().all()
        items.extend(_channel_item(r) for r in rows)

    return items


def _callback_item(row: Any, names: dict[str, str]) -> dict[str, Any]:
    open_ = row.status == "requested"
    call_id = str(row.original_call_id) if row.original_call_id else None
    contact = _contact(None, row.to_e164)
    actions = []
    if call_id and open_:
        actions.append({"kind": "call_back", "label": "Call back now", "callId": call_id})
    actions.append({"kind": "open_callbacks", "label": "Open callbacks"})
    if call_id:
        actions.append({"kind": "open_call", "label": "Open call", "callId": call_id})
    status_text = {"converted": "was handled", "dismissed": "was dismissed", "completed": "was completed"}
    text = f"{_who(contact)} asked for a callback" if open_ or row.status not in status_text else \
        f"Callback request from {_who(contact)} {status_text[row.status]}"
    item = _item(key=f"callback:{row.callback_id}", type_="callback.requested", category="calls",
                 at=row.created_at, tone="warning" if open_ else "neutral", actor=None, text=text,
                 agent_id=row.agent_id, contact=contact, needs_action=open_, actions=actions,
                 refs={"callId": call_id, "callbackId": str(row.callback_id)})
    if call_id:
        def render(it: dict[str, Any], info: dict[str, Any]) -> None:
            if info.get("name"):
                it["contact"] = {**(it["contact"] or {}), "name": info["name"]}
                it["text"] = it["text"].replace(contact.get("phone") or "\0", info["name"], 1)
            if info.get("requested_when"):
                it["detail"] = _asked_for(info["requested_when"], info.get("resolved_window"))
                it["meta"]["requestedWhen"] = info["requested_when"]
                if info.get("resolved_window"):
                    it["meta"]["resolvedWindow"] = info["resolved_window"]
        item["_enrich"] = render
    return item


def _asked_for(requested: str, resolved: dict | None) -> str:
    """'Asked for: రేపు ఈవెనింగ్ → Sat 31 Oct, 5:00–7:30 pm'."""
    text = f"Asked for: {requested}"
    if isinstance(resolved, dict) and resolved.get("display"):
        text += f" → {resolved['display']}"
    return text


def _followup_item(row: Any, names: dict[str, str]) -> dict[str, Any]:
    contact = _contact(None, row.phone)
    who = _who(contact, "a contact")
    payload = row.payload or {}
    requested = payload.get("requestedWhen") or payload.get("requestText") or None
    common = {"followUpId": str(row.id), "updatedAt": _iso(row.updated_at), "expiresAt": _iso(row.expires_at),
              "dueAt": _iso(row.due_at), "timezone": payload.get("timezone")}
    refs = {"followUpId": str(row.id), "callId": row.source_id}
    kind_word = {"missed": "missed-call follow-up", "recall": "recall"}.get(row.kind, "callback")
    resolved = payload.get("resolvedWindow") if isinstance(payload.get("resolvedWindow"), dict) else None
    if row.kind == "recall":
        outcome_word = {"no_answer": "didn't answer", "busy": "was busy", "declined": "declined",
                        "failed": "couldn't be reached"}.get(str(payload.get("outcome") or ""), "wasn't reached")
        review_detail = f"Last call: {who} {outcome_word}"
    else:
        review_detail = f"Caller asked: {requested}" + (f" → {resolved['display']}" if resolved else "") if requested else None
    if row.status == "needs_review":
        return _item(key=f"followup:{row.id}:review", type_="followup.review", category="calls", at=row.updated_at,
                     tone="warning", actor=None, text=f"A {kind_word} to {who} needs your approval",
                     detail=review_detail, agent_id=row.agent_id,
                     contact=contact, needs_action=True, refs=refs,
                     meta={"requestedWhen": requested, "resolvedWindow": resolved},
                     actions=[{"kind": "approve_followup", "label": "Approve", **common},
                              {"kind": "reject_followup", "label": "Don't call", **common},
                              {"kind": "open_followups", "label": "Open follow-ups"}])
    if row.status == "scheduled":
        return _item(key=f"followup:{row.id}:scheduled", type_="callback.due", category="calls", at=row.updated_at,
                     tone="info", actor=names.get(str(row.agent_id)), text=f"will call {who} back",
                     detail=_asked_for(requested, resolved) if requested and resolved else None,
                     agent_id=row.agent_id, contact=contact, refs=refs,
                     meta={"dueAt": _iso(row.due_at), "resolvedWindow": resolved},
                     actions=[{"kind": "reject_followup", "label": "Cancel", **common},
                              {"kind": "open_followups", "label": "Open follow-ups"}])
    if row.status == "dialed":
        return _item(key=f"followup:{row.id}:dialed", type_="followup.sent", category="calls", at=row.updated_at,
                     tone="info", actor=names.get(str(row.agent_id)), text=f"is calling {who} back",
                     agent_id=row.agent_id, contact=contact, refs=refs,
                     actions=[{"kind": "open_followups", "label": "Open follow-ups"}])
    return _item(key=f"followup:{row.id}:done", type_="followup.done", category="calls", at=row.updated_at,
                 tone="success" if row.reason == "call_connected" else "neutral",
                 actor=names.get(str(row.agent_id)),
                 text=f"called {who} back" if row.reason == "call_connected" else f"finished follow-up attempts to {who}",
                 agent_id=row.agent_id, contact=contact, refs=refs,
                 actions=[{"kind": "open_followups", "label": "Open follow-ups"}])


def _language_item(row: Any, names: dict[str, str]) -> dict[str, Any]:
    language = _language_name(row.requested_language)
    contact = _contact(row.contact_name, row.phone_e164)
    who = _who(contact, "a caller")
    refs = {"languageRequestId": str(row.id), "callId": str(row.original_call_id) if row.original_call_id else None}
    open_call = [{"kind": "open_call", "label": "Open call", "callId": refs["callId"]}] if refs["callId"] else []
    if row.status == "pending":
        return _item(key=f"language:{row.id}", type_="language.callback", category="calls", at=row.updated_at,
                     tone="warning", actor=None, text=f"{who} needs a callback in {language}",
                     detail=(row.request_text or None), agent_id=row.agent_id, contact=contact, needs_action=True,
                     refs=refs, meta={"language": row.requested_language, "languageLabel": language},
                     actions=[{"kind": "call_in_language", "label": f"Call in {language}",
                               "requestId": str(row.id), "agentId": row.agent_id,
                               "language": row.requested_language, "languageLabel": language},
                              {"kind": "dismiss_language", "label": "Dismiss", "requestId": str(row.id)},
                              *open_call])
    if row.status == "calling":
        return _item(key=f"language:{row.id}", type_="language.calling", category="calls", at=row.updated_at,
                     tone="info", actor=names.get(str(row.agent_id)), text=f"is calling {who} back in {language}",
                     agent_id=row.agent_id, contact=contact, refs=refs,
                     actions=[{"kind": "open_language", "label": "Open language callbacks"}, *open_call])
    return _item(key=f"language:{row.id}", type_="language.done", category="calls",
                 at=row.updated_at, tone="success", actor=names.get(str(row.agent_id)),
                 text=f"called {who} back in {language}", agent_id=row.agent_id, contact=contact, refs=refs,
                 actions=open_call)


def _lead_item(row: Any, names: dict[str, str]) -> dict[str, Any]:
    stage = str(row.stage or "new").lower()
    name = str(row.name or "").strip() or "a contact"
    contact = _contact(row.name, row.phone)
    actor = names.get(str(row.agent_id)) if row.agent_id else None
    actions = [{"kind": "open_lead", "label": "Open lead", "leadId": str(row.lead_id), "name": row.name}]
    refs = {"leadId": str(row.lead_id)}
    if stage in _QUALIFIED_STAGES:
        label = {"qualified": "is qualified", "converted": "converted", "meeting_booked": "booked a meeting"}[stage]
        return _item(key=f"lead:{row.lead_id}:{stage}", type_="lead.qualified", category="leads", at=row.updated_at,
                     tone="success", actor=None, text=f"{name} {label}", agent_id=row.agent_id, contact=contact,
                     refs=refs, actions=actions, meta={"stage": stage})
    text = f"added {name} as a new lead" if actor else f"New lead: {name}"
    if stage not in ("new",):
        text = f"updated lead {name}" if actor else f"Lead {name} was updated"
    return _item(key=f"lead:{row.lead_id}:{stage}", type_="lead.created", category="leads", at=row.updated_at,
                 tone="info", actor=actor, text=text, agent_id=row.agent_id, contact=contact, refs=refs,
                 actions=actions, meta={"stage": stage})


async def _campaign_items(session, M, *, tenant_id, agent, before, fetch, names) -> list[dict[str, Any]]:
    Campaign, Run, Contact = M["Campaign"], M["CampaignRun"], M["CampaignContact"]
    scope = _where(Campaign.tenant_id == tenant_id, Campaign.agent_id == agent if agent else None)
    started = (await session.execute(
        select(Run, Campaign).join(Campaign, Campaign.campaign_id == Run.campaign_id)
        .where(*scope, Run.started_at.is_not(None), *_where(_below(Run.started_at, before)))
        .order_by(Run.started_at.desc()).limit(fetch))).all()
    finished = (await session.execute(
        select(Run, Campaign).join(Campaign, Campaign.campaign_id == Run.campaign_id)
        .where(*scope, Run.ended_at.is_not(None), *_where(_below(Run.ended_at, before)))
        .order_by(Run.ended_at.desc()).limit(fetch))).all()
    created = (await session.execute(
        select(Campaign).where(*scope, *_where(_below(Campaign.created_at, before)))
        .order_by(Campaign.created_at.desc()).limit(fetch))).scalars().all()

    ids = {c.campaign_id for _, c in started} | {c.campaign_id for _, c in finished} | {c.campaign_id for c in created}
    progress: dict[str, dict[str, int]] = {}
    if ids:
        rows = (await session.execute(
            select(Contact.campaign_id, Contact.status, func.count())
            .where(Contact.campaign_id.in_(list(ids))).group_by(Contact.campaign_id, Contact.status))).all()
        for cid, status, count in rows:
            bucket = progress.setdefault(str(cid), {"total": 0, "done": 0})
            bucket["total"] += int(count)
            if str(status or "") not in ("pending", "queued", "in_progress", "dialing", "scheduled", "retry"):
                bucket["done"] += int(count)

    out: list[dict[str, Any]] = []
    empty = {"total": 0, "done": 0}
    for run, camp in started:
        out.append(_campaign_item("start", camp, run, progress.get(str(camp.campaign_id), empty), names))
    for run, camp in finished:
        out.append(_campaign_item("end", camp, run, progress.get(str(camp.campaign_id), empty), names))
    for camp in created:
        out.append(_campaign_item("created", camp, None, progress.get(str(camp.campaign_id), empty), names))
    return out


def _campaign_item(kind: str, camp: Any, run: Any, p: dict[str, int], names: dict[str, str]) -> dict[str, Any]:
    """One campaign event: a run started (``start``), a run ended (``end``) or the campaign was created."""
    actions = [{"kind": "open_campaign", "label": "Open campaign", "campaignId": str(camp.campaign_id)}]
    refs = {"campaignId": str(camp.campaign_id)}
    meta = {"progress": p, "status": camp.status}
    if kind == "start":
        running = run.ended_at is None and str(camp.status) == "running"
        return _item(key=f"campaign:{run.run_id}:start", type_="campaign.started", category="campaigns",
                     at=run.started_at, tone="live" if running else "info",
                     actor=names.get(str(camp.agent_id)), text=f"started calling for “{camp.name}”",
                     agent_id=camp.agent_id,
                     detail=(f"{p['done']} of {p['total']} contacts done" if p["total"] else None),
                     refs=refs, actions=actions, meta=meta)
    if kind == "end":
        return _item(key=f"campaign:{run.run_id}:end", type_="campaign.completed", category="campaigns",
                     at=run.ended_at, tone="success", actor=None,
                     text=f"Campaign “{camp.name}” finished", agent_id=camp.agent_id,
                     detail=(f"{p['done']} of {p['total']} contacts called" if p["total"] else None),
                     refs=refs, actions=actions, meta=meta)
    return _item(key=f"campaign:{camp.campaign_id}:created", type_="campaign.created", category="campaigns",
                 at=camp.created_at, tone="neutral", actor=None,
                 text=f"Campaign “{camp.name}” was created", agent_id=camp.agent_id,
                 refs=refs, actions=actions, meta=meta)


def _tool_item(row: Any, names: dict[str, str]) -> dict[str, Any]:
    ok = row.status == "succeeded"
    pending = row.status == "timed_out_pending"
    phrase = _tool_phrase(row.action, ok or pending)
    app = _tool_app(row.action)
    actions = [{"kind": "open_call", "label": "Open call", "callId": row.call_id}] if row.call_id else []
    if not ok:
        actions.append({"kind": "open_integrations", "label": "Check integrations"})
    return _item(key=f"tool:{row.id}", type_="integration.action", category="system", at=row.started_at,
                 tone="success" if ok else ("warning" if pending else "danger"),
                 actor=names.get(str(row.agent_id)),
                 text=phrase + (f" in {app}" if app else "") + (" (not confirmed yet)" if pending else ""),
                 agent_id=row.agent_id, refs={"callId": row.call_id}, actions=actions,
                 meta={"app": app})


def _number_item(row: Any, names: dict[str, str]) -> dict[str, Any]:
    status = str(row.status or "").lower()
    ready = status == "active"
    suspended = status == "suspended_unpaid"
    if suspended:
        text, tone = f"Phone line {row.e164} is paused until its rent is paid", "danger"
    elif ready:
        text, tone = f"Phone line {row.e164} is ready", "success"
    else:
        text, tone = f"Phone line {row.e164} is being set up", "info"
    actions = [{"kind": "open_numbers", "label": "Open phone lines"}]
    if suspended:
        actions.insert(0, {"kind": "top_up", "label": "Add funds"})
    return _item(key=f"number:{row.id}", type_="number.provisioned" if not suspended else "number.suspended",
                 category="system", at=row.created_at, tone=tone, actor=None, text=text, agent_id=row.agent_id,
                 actions=actions, refs={"numberId": str(row.id)})


def _wallet_item(row: Any) -> dict[str, Any] | None:
    amount = abs(int(row.amount_inr_paise or 0))
    usd = abs(int(row.amount_cents or 0))
    money = money_inr(amount) if amount else (f"${usd / 100:,.2f}" if usd else None)
    if row.kind in _TOPUP_KINDS:
        text, tone, type_ = (f"{money} added to your wallet" if money else "Credit added to your wallet"), "success", "billing.topup"
    elif row.kind in _RENT_KINDS:
        text, tone, type_ = (f"Monthly phone line rent paid · {money}" if money else "Monthly phone line rent paid"), "neutral", "billing.rent"
    elif row.kind in _REFUND_KINDS:
        text, tone, type_ = (f"{money} refunded to your wallet" if money else "Refund added to your wallet"), "success", "billing.refund"
    else:
        return None
    return _item(key=f"wallet:{row.id}", type_=type_, category="system", at=row.created_at, tone=tone, actor=None,
                 text=text, actions=[{"kind": "open_billing", "label": "Open billing"}], refs={})


def _channel_item(row: Any) -> dict[str, Any]:
    kind = row.kind
    if kind == "purchase":
        text, tone = f"Call channels increased to {row.channels_after}", "success"
    elif kind == "renewal":
        text, tone = f"{row.channels_after} call channel{'s' if row.channels_after != 1 else ''} renewed", "neutral"
    elif kind == "renewal_failed":
        text, tone = "Call channel renewal failed — add funds to keep them", "danger"
    elif kind == "lapsed":
        text, tone = "Extra call channels lapsed", "danger"
    else:
        text, tone = f"Call channels changed to {row.channels_after}", "neutral"
    actions = [{"kind": "open_billing", "label": "Open billing"}]
    if tone == "danger":
        actions.insert(0, {"kind": "top_up", "label": "Add funds"})
    return _item(key=f"channel:{row.id}", type_=f"channel.{kind}", category="system", at=row.created_at, tone=tone,
                 actor=None, text=text, actions=actions, refs={})


# -- Pinned "needs action" -----------------------------------------------------------------

async def _pinned(session, M, *, tenant_id: uuid.UUID, agent: uuid.UUID | None,
                  names: dict[str, str]) -> tuple[list[dict[str, Any]], int]:
    """Open work, newest first, independent of the cursor. Returns (items, total open)."""
    agent_str = str(agent) if agent else None
    out: list[dict[str, Any]] = []
    total = 0
    L, F, C = M["LanguageSwitchRequest"], M["FollowUpJob"], M["CallCallback"]

    lang_scope = _where(L.tenant_id == tenant_id, L.status == "pending", L.agent_id == agent_str if agent_str else None)
    total += int(await session.scalar(select(func.count()).select_from(L).where(*lang_scope)) or 0)
    rows = (await session.execute(select(L).where(*lang_scope).order_by(L.updated_at.desc()).limit(PINNED_CAP))).scalars().all()
    out.extend(_language_item(r, names) for r in rows)

    fu_scope = _where(F.tenant_id == tenant_id, F.status == "needs_review", F.agent_id == agent if agent else None)
    total += int(await session.scalar(select(func.count()).select_from(F).where(*fu_scope)) or 0)
    rows = (await session.execute(select(F).where(*fu_scope).order_by(F.updated_at.desc()).limit(PINNED_CAP))).scalars().all()
    out.extend(_followup_item(r, names) for r in rows)

    cb_scope = _where(C.tenant_id == tenant_id, C.mode == "requested", C.status == "requested",
                      C.agent_id == agent_str if agent_str else None)
    total += int(await session.scalar(select(func.count()).select_from(C).where(*cb_scope)) or 0)
    rows = (await session.execute(select(C).where(*cb_scope).order_by(C.created_at.desc()).limit(PINNED_CAP))).scalars().all()
    out.extend(_callback_item(r, names) for r in rows)

    if agent is None:
        alerts = await _system_alerts(session, M, tenant_id=tenant_id)
        total += len(alerts)
        out.extend(alerts)
    out.sort(key=lambda i: i["_at"], reverse=True)
    return out, total


async def _system_alerts(session, M, *, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    wallet = await session.get(M["BillingWallet"], tenant_id)
    paise = int(getattr(wallet, "balance_inr_paise", 0) or 0)
    cents = int(getattr(wallet, "balance_cents", 0) or 0)
    # A missing wallet row is an empty wallet.
    if paise <= 0 and cents <= 0:
        alerts.append(_item(key="alert:wallet", type_="billing.low", category="system",
                            at=getattr(wallet, "updated_at", None), tone="danger", actor=None,
                            text="Your wallet is empty, so calls can't be placed", needs_action=True,
                            actions=[{"kind": "top_up", "label": "Add funds"}], refs={},
                            meta={"balanceInrPaise": paise, "empty": True}))
    elif (paise and paise <= LOW_WALLET_INR_PAISE) or (not paise and cents <= LOW_WALLET_USD_CENTS):
        left = money_inr(paise) if paise else f"${cents / 100:,.2f}"
        alerts.append(_item(key="alert:wallet", type_="billing.low", category="system",
                            at=getattr(wallet, "updated_at", None), tone="warning", actor=None,
                            text=f"Wallet is running low · {left} left", needs_action=True,
                            actions=[{"kind": "top_up", "label": "Add funds"}], refs={},
                            meta={"balanceInrPaise": paise, "empty": False}))

    P = M["PhoneNumber"]
    for row in (await session.execute(select(P).where(P.tenant_id == tenant_id, P.released_at.is_(None),
                                                       P.status == "suspended_unpaid").limit(10))).scalars():
        item = _number_item(row, {})
        item.update(needsAction=True, id=f"alert:number:{row.id}")
        alerts.append(item)

    S = M["TenantChannelSubscription"]
    sub = await session.get(S, tenant_id)
    if sub is not None and str(sub.status) in ("grace", "lapsed"):
        grace = _utc(sub.grace_until)
        text = sub.notice or ("Call channel renewal is overdue" + (
            f" — add funds before {grace.strftime('%d %b')}" if grace else ""))
        alerts.append(_item(key="alert:channels", type_="channel.grace", category="system", at=sub.updated_at,
                            tone="warning" if sub.status == "grace" else "danger", actor=None, text=text,
                            needs_action=True, refs={},
                            actions=[{"kind": "top_up", "label": "Add funds"},
                                     {"kind": "open_billing", "label": "Open billing"}]))

    I = M["TenantIntegration"]
    for row in (await session.execute(select(I).where(I.tenant_id == tenant_id, I.status == "ERROR").limit(10))).scalars():
        label = _app_label(row.app_name)
        alerts.append(_item(key=f"alert:integration:{row.id}", type_="integration.reconnect", category="system",
                            at=row.updated_at, tone="danger", actor=None,
                            text=f"{label} is disconnected — reconnect it so agents can use it", needs_action=True,
                            actions=[{"kind": "reconnect_integration", "label": "Reconnect", "app": row.app_name}],
                            refs={}, meta={"app": label}))
    return alerts


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if not k.startswith("_")}


async def build_feed(tenant_id: uuid.UUID, *, cursor: str | None = None, limit: int = DEFAULT_LIMIT,
                     filter_: str = "all", agent_id: str | None = None) -> dict[str, Any]:
    """One page of the activity feed plus, on the first page, the pinned "needs action" list."""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    filter_ = filter_ if filter_ in FILTERS else "all"
    agent = _as_uuid(agent_id) if agent_id else None
    if agent_id and agent is None:
        return {"items": [], "pinned": [], "nextCursor": None, "needsActionCount": 0, "filter": filter_,
                "generatedAt": _iso(_now())}
    position = decode_cursor(cursor)
    factory = get_session_factory()
    if factory is None:
        return {"items": [], "pinned": [], "nextCursor": None, "needsActionCount": 0, "filter": filter_,
                "generatedAt": _iso(_now()), "unavailable": True}
    M = _models()
    now = _now()
    async with factory() as session:
        names = await _agent_names(session, M, tenant_id)
        pinned: list[dict[str, Any]] = []
        needs_total = 0
        if position is None or filter_ == "needs_action":
            pinned, needs_total = await _pinned(session, M, tenant_id=tenant_id, agent=agent, names=names)
        items: list[dict[str, Any]] = []
        if filter_ != "needs_action":
            items = await _collect(session, M, tenant_id=tenant_id, agent=agent, sources=_FILTER_SOURCES[filter_],
                                   before=position[0] if position else None, fetch=limit + 2, names=names)
            if position is None and filter_ in ("all", "calls"):
                items.extend(await _live_items(session, M, tenant_id=tenant_id, agent=agent, names=names, now=now))

    if filter_ == "needs_action":
        page = pinned[:MAX_LIMIT]
        pinned_out: list[dict[str, Any]] = []
        next_cursor = None
    else:
        # Live items sort first; everything else newest first with a stable tie-breaker.
        items.sort(key=lambda i: (i["type"] == "call.live", i["_at"], i["id"]), reverse=True)
        if position is not None:
            items = [i for i in items if (i["_at"], i["id"]) < position]
        pinned_ids = {i["id"] for i in pinned}
        seen: set[str] = set()
        deduped = []
        for item in items:
            if item["id"] in seen or item["id"] in pinned_ids:
                continue
            seen.add(item["id"])
            deduped.append(item)
        page = deduped[:limit]
        # Any source that filled its window means older rows may exist below this page.
        has_more = sum(1 for i in items if i["type"] != "call.live") > limit
        last_regular = next((i for i in reversed(page) if i["type"] != "call.live"), None)
        next_cursor = encode_cursor(last_regular["_at"], last_regular["id"]) if (
            has_more and last_regular) else None
        pinned_out = pinned if filter_ == "all" else [p for p in pinned if _matches_filter(p, filter_)]

    await _enrich_calls(page + pinned_out, str(tenant_id))
    return {
        "items": [_public(i) for i in page],
        "pinned": [_public(i) for i in pinned_out],
        "nextCursor": next_cursor,
        "needsActionCount": needs_total,
        "filter": filter_,
        "generatedAt": _iso(now),
    }


def _matches_filter(item: dict[str, Any], filter_: str) -> bool:
    if filter_ in ("all", "needs_action"):
        return True
    return item.get("category") == filter_


async def _live_items(session, M, *, tenant_id, agent, names, now) -> list[dict[str, Any]]:
    Call = M["Call"]
    rows = (await session.execute(select(Call).where(*_where(
        Call.tenant_id == tenant_id, Call.ended_at.is_(None), Call.is_test.is_(False),
        Call.started_at >= now - LIVE_MAX_AGE, Call.agent_id == agent if agent else None,
    )).order_by(Call.started_at.desc()).limit(20))).scalars().all()
    return [_live_item(r, names, now) for r in rows]


# -- Live rail -----------------------------------------------------------------------------

async def live_snapshot(tenant_id: uuid.UUID, *, since: datetime | None = None) -> dict[str, Any]:
    """Calls in progress plus today's counts. Cheap enough to poll every few seconds."""
    now = _now()
    since = _utc(since) or now.replace(hour=0, minute=0, second=0, microsecond=0)
    if since > now or now - since > timedelta(days=2):
        since = now - timedelta(hours=24)
    factory = get_session_factory()
    empty_today = {"calls": 0, "answered": 0, "missed": 0, "talkSeconds": 0, "leads": 0, "bookings": 0}
    if factory is None:
        return {"calls": [], "ringing": 0, "today": empty_today, "serverTime": _iso(now), "unavailable": True}
    M = _models()
    Call, A, Lead = M["Call"], M["CallAttempt"], M["Lead"]
    async with factory() as session:
        names = await _agent_names(session, M, tenant_id)
        live_rows = (await session.execute(select(Call).where(
            Call.tenant_id == tenant_id, Call.ended_at.is_(None), Call.is_test.is_(False),
            Call.started_at >= now - LIVE_MAX_AGE,
        ).order_by(Call.started_at.desc()).limit(50))).scalars().all()
        ringing = int(await session.scalar(select(func.count()).select_from(A).where(
            A.tenant_id == tenant_id, A.status == "in_progress", A.linked_call_id.is_(None),
            A.started_at >= now - RINGING_MAX_AGE)) or 0)
        agg = (await session.execute(select(
            func.count(), func.coalesce(func.sum(Call.duration_sec), 0),
        ).where(Call.tenant_id == tenant_id, Call.is_test.is_(False), Call.started_at >= since,
                Call.ended_at.is_not(None)))).one()
        answered = int(await session.scalar(select(func.count()).select_from(Call).where(
            Call.tenant_id == tenant_id, Call.is_test.is_(False), Call.started_at >= since,
            Call.ended_at.is_not(None), Call.duration_sec >= 5)) or 0)
        bookings = int(await session.scalar(select(func.count()).select_from(Call).where(
            Call.tenant_id == tenant_id, Call.is_test.is_(False), Call.started_at >= since,
            Call.disposition == "site_visit_planned")) or 0)
        missed_attempts = int(await session.scalar(select(func.count()).select_from(A).where(
            A.tenant_id == tenant_id, A.linked_call_id.is_(None), A.started_at >= since,
            A.status.in_(("missed", "declined", "voicemail")))) or 0)
        leads = int(await session.scalar(select(func.count()).select_from(Lead).where(
            Lead.tenant_id == tenant_id, Lead.created_at >= since)) or 0)

    items = [_live_item(r, names, now) for r in live_rows]
    await _enrich_calls(items, str(tenant_id))
    calls = [{
        "callId": i["refs"]["callId"], "agentId": i["agentId"], "agentName": i["actor"],
        "direction": i["meta"].get("direction"), "startedAt": i["meta"].get("startedAt"),
        "contact": i["contact"],
    } for i in items]
    total_calls = int(agg[0] or 0)
    return {
        "calls": calls,
        "ringing": ringing,
        "today": {"calls": total_calls + missed_attempts, "answered": answered,
                  "missed": missed_attempts + max(0, total_calls - answered),
                  "talkSeconds": int(agg[1] or 0), "leads": leads, "bookings": bookings},
        "since": _iso(since),
        "serverTime": _iso(now),
    }


# -- One item, in full (the console's detail panel) -----------------------------------------

#: Related rows shown per kind in the detail panel.
DETAIL_RELATED_CAP = 10
_CAMPAIGN_OPEN_STATUSES = ("pending", "queued", "in_progress", "dialing", "scheduled", "retry")


def _channel_label(kind: str) -> str:
    return {"purchase": "Channels bought", "renewal": "Renewal", "renewal_failed": "Renewal failed",
            "lapsed": "Channels lapsed", "downgrade_applied": "Channels reduced"}.get(kind, "Channel change")


def _wallet_label(kind: str) -> str:
    if kind in _TOPUP_KINDS:
        return "Top-up"
    if kind in _RENT_KINDS:
        return "Phone line rent"
    if kind in _REFUND_KINDS:
        return "Refund"
    return "Wallet change"


async def _call_record(session, M, tenant_id: uuid.UUID, call_id: str | None) -> dict[str, Any] | None:
    """The same row ``GET /api/calls`` returns for one call (or ringing attempt), tenant-scoped."""
    cid = _as_uuid(call_id)
    if cid is None:
        return None
    from server.call import call_timeline
    from server.call.call_store import _attempt_row_to_dict, _row_to_dict

    row = await session.get(M["Call"], cid)
    if row is not None and row.tenant_id == tenant_id and not row.is_test:
        return call_timeline._call_to_item(_row_to_dict(row))
    attempt = await session.get(M["CallAttempt"], cid)
    if attempt is not None and attempt.tenant_id == tenant_id:
        return call_timeline._attempt_to_item(_attempt_row_to_dict(attempt))
    return None


async def _enrich_call_record(record: dict[str, Any], tenant_id: uuid.UUID) -> dict[str, Any]:
    """Summary, recording, contact numbers and the wallet charge, exactly as the Calls page gets them."""
    try:
        from server.routes import calls as calls_routes

        enriched = await asyncio.to_thread(calls_routes._enrich_timeline_item, record)
        if enriched.get("connected") and enriched.get("call_id"):
            enriched.update(await asyncio.to_thread(calls_routes._integration_fields, str(enriched["call_id"])))
        await calls_routes._attach_tenant_wallet_charges([enriched], str(tenant_id))
        return enriched
    except Exception:  # noqa: BLE001 -- the panel still shows the database fields.
        logger.debug("activity_feed.detail_enrich_failed")
        return record


async def _related_to_call(session, M, tenant_id: uuid.UUID, call_id: str,
                           names: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    """Callbacks, follow-ups, language callbacks and integration actions that came from one call."""
    cid = _as_uuid(call_id)
    C, F, L, T = M["CallCallback"], M["FollowUpJob"], M["LanguageSwitchRequest"], M["ToolExecution"]
    cap = DETAIL_RELATED_CAP
    callbacks: list[dict[str, Any]] = []
    language: list[dict[str, Any]] = []
    if cid is not None:
        callbacks = [_callback_item(r, names) for r in (await session.execute(select(C).where(
            C.tenant_id == tenant_id, C.mode == "requested",
            or_(C.original_call_id == cid, C.original_attempt_id == cid),
        ).order_by(C.created_at.desc()).limit(cap))).scalars().all()]
        language = [_language_item(r, names) for r in (await session.execute(select(L).where(
            L.tenant_id == tenant_id, L.original_call_id == cid,
        ).order_by(L.updated_at.desc()).limit(cap))).scalars().all()]
    followups = [_followup_item(r, names) for r in (await session.execute(select(F).where(
        F.tenant_id == tenant_id, F.source_id == str(call_id),
    ).order_by(F.updated_at.desc()).limit(cap))).scalars().all()]
    tools = [_tool_item(r, names) for r in (await session.execute(select(T).where(
        T.tenant_id == tenant_id, T.call_id == str(call_id),
        T.status.in_(("succeeded", "failed", "timed_out_pending")),
    ).order_by(T.started_at.asc()).limit(cap))).scalars().all()]
    return {"callbacks": callbacks, "followUps": followups, "languageRequests": language,
            "integrationActions": tools}


async def _lead_calls(session, M, tenant_id: uuid.UUID, lead: Any, names: dict[str, str]) -> list[dict[str, Any]]:
    """The lead's latest calls: the assessed call plus calls its callbacks, follow-ups and attempts point at."""
    phone = str(lead.phone or "").strip()
    call_ids: set[uuid.UUID] = set()
    try:
        from server.db.models.followup_models import LeadAssessment

        source = await session.scalar(select(LeadAssessment.source_call_id).where(
            LeadAssessment.tenant_id == tenant_id, LeadAssessment.lead_id == lead.lead_id))
        if _as_uuid(source):
            call_ids.add(_as_uuid(source))
    except Exception:  # noqa: BLE001 -- the scoring table may not exist yet.
        await session.rollback()
    items: list[dict[str, Any]] = []
    if phone:
        C, F, L, A = M["CallCallback"], M["FollowUpJob"], M["LanguageSwitchRequest"], M["CallAttempt"]
        call_ids |= set((await session.execute(select(C.original_call_id).where(
            C.tenant_id == tenant_id, C.to_e164 == phone, C.original_call_id.is_not(None)).limit(20))).scalars())
        call_ids |= set((await session.execute(select(L.original_call_id).where(
            L.tenant_id == tenant_id, L.phone_e164 == phone, L.original_call_id.is_not(None)).limit(20))).scalars())
        call_ids |= {u for r in (await session.execute(select(F.source_id).where(
            F.tenant_id == tenant_id, F.phone == phone).limit(20))).scalars() if (u := _as_uuid(r))}
        attempts = (await session.execute(select(A).where(
            A.tenant_id == tenant_id, A.linked_call_id.is_(None), or_(A.from_number == phone, A.to_number == phone),
            A.status.in_(("missed", "declined", "voicemail", "failed")),
        ).order_by(A.started_at.desc()).limit(5))).scalars().all()
        items.extend(_attempt_item(r, names) for r in attempts)
    if call_ids:
        Call = M["Call"]
        rows = (await session.execute(select(Call).where(
            Call.tenant_id == tenant_id, Call.call_id.in_(list(call_ids)), Call.is_test.is_(False),
        ).order_by(Call.started_at.desc()).limit(5))).scalars().all()
        items.extend(_call_item(r, names) if r.ended_at is not None else _live_item(r, names, _now()) for r in rows)
    items.sort(key=lambda i: i["_at"], reverse=True)
    return items[:5]


def _row_by_id(value: str) -> uuid.UUID | None:
    return _as_uuid(str(value or "").split(":")[0])


async def item_detail(tenant_id: uuid.UUID, item_id: str) -> dict[str, Any] | None:
    """Everything the console's detail panel shows for one feed item, or ``None`` if it is not this tenant's.

    The item is rebuilt from its source row, so a deep link works even when the item
    is no longer on the first feed page. Read-only: nothing here dials, charges or writes.
    """
    item_id = str(item_id or "").strip()[:160]
    kind, _, rest = item_id.partition(":")
    factory = get_session_factory()
    if factory is None or not rest:
        return None
    M = _models()
    now = _now()
    item: dict[str, Any] | None = None
    record: dict[str, Any] | None = None
    related: dict[str, list[dict[str, Any]]] = {}
    lead_out: dict[str, Any] | None = None
    campaign_out: dict[str, Any] | None = None
    facts: dict[str, Any] = {}
    source_call: str | None = None
    rid = _row_by_id(rest)

    async with factory() as session:
        names = await _agent_names(session, M, tenant_id)

        async def owned(model):
            row = await session.get(model, rid) if rid is not None else None
            return row if row is not None and row.tenant_id == tenant_id else None

        if kind in ("call", "live"):
            row = await owned(M["Call"])
            if row is None or row.is_test:
                return None
            item = _live_item(row, names, now) if row.ended_at is None else _call_item(row, names)
            source_call = str(row.call_id)
        elif kind == "attempt":
            row = await owned(M["CallAttempt"])
            if row is None:
                return None
            item = _attempt_item(row, names)
            source_call = str(row.attempt_id)
        elif kind == "callback":
            row = await owned(M["CallCallback"])
            if row is None:
                return None
            item = _callback_item(row, names)
            source_call = item["refs"].get("callId") or (str(row.original_attempt_id) if row.original_attempt_id else None)
            facts = {"status": row.status, "requestedAt": _iso(row.created_at), "updatedAt": _iso(row.updated_at)}
        elif kind == "followup":
            row = await owned(M["FollowUpJob"])
            if row is None:
                return None
            item = _followup_item(row, names)
            source_call = row.source_id
            payload = row.payload or {}
            facts = {"status": row.status, "kind": row.kind, "dueAt": _iso(row.due_at),
                     "expiresAt": _iso(row.expires_at), "requestedAt": _iso(row.created_at),
                     "requestedWhen": payload.get("requestedWhen") or payload.get("requestText"),
                     "resolvedWindow": (payload.get("resolvedWindow") or {}).get("summary"),
                     "timezone": payload.get("timezone")}
        elif kind == "language":
            row = await owned(M["LanguageSwitchRequest"])
            if row is None:
                return None
            item = _language_item(row, names)
            source_call = item["refs"].get("callId")
            facts = {"status": row.status, "language": _language_name(row.requested_language),
                     "originalLanguage": _language_name(row.original_language),
                     "requestedAt": _iso(row.created_at), "updatedAt": _iso(row.updated_at),
                     "requestText": row.request_text}
        elif kind == "lead":
            row = await owned(M["Lead"])
            if row is None:
                return None
            item = _lead_item(row, names)
            lead_out = {"leadId": str(row.lead_id), "name": row.name, "phone": row.phone, "email": row.email,
                        "stage": row.stage, "notes": row.notes, "agentId": row.agent_id,
                        "createdAt": _iso(row.created_at), "updatedAt": _iso(row.updated_at)}
            related["calls"] = await _lead_calls(session, M, tenant_id, row, names)
        elif kind == "campaign":
            _, _, which = rest.partition(":")
            Campaign, Run, Contact = M["Campaign"], M["CampaignRun"], M["CampaignContact"]
            run = None
            if which in ("start", "end"):
                run = await session.get(Run, rid) if rid is not None else None
                camp = await session.get(Campaign, run.campaign_id) if run is not None else None
            else:
                camp = await session.get(Campaign, rid) if rid is not None else None
            if camp is None or camp.tenant_id != tenant_id:
                return None
            counts = dict((await session.execute(select(Contact.status, func.count()).where(
                Contact.campaign_id == camp.campaign_id).group_by(Contact.status))).all())
            total = sum(int(v) for v in counts.values())
            done = sum(int(v) for k, v in counts.items() if str(k or "") not in _CAMPAIGN_OPEN_STATUSES)
            p = {"total": total, "done": done}
            item = _campaign_item(which if which in ("start", "end") else "created", camp, run, p, names)
            campaign_out = {"campaignId": str(camp.campaign_id), "name": camp.name, "status": camp.status,
                            "description": camp.description, "agentId": str(camp.agent_id),
                            "createdAt": _iso(camp.created_at), "concurrency": camp.concurrency,
                            "progress": p, "statusCounts": {str(k or "unknown"): int(v) for k, v in counts.items()},
                            "run": ({"startedAt": _iso(run.started_at), "endedAt": _iso(run.ended_at),
                                     "status": run.status} if run is not None else None)}
        elif kind == "tool":
            row = await owned(M["ToolExecution"])
            if row is None:
                return None
            item = _tool_item(row, names)
            source_call = row.call_id
            facts = {"status": row.status, "app": _tool_app(row.action), "startedAt": _iso(row.started_at),
                     "completedAt": _iso(row.completed_at)}
        elif kind == "number":
            row = await owned(M["PhoneNumber"])
            if row is None:
                return None
            item = _number_item(row, names)
            facts = {"number": row.e164, "status": row.status, "addedAt": _iso(row.created_at),
                     "agentName": names.get(str(row.agent_id)) if row.agent_id else None,
                     "inbound": bool(row.inbound_enabled), "outbound": bool(row.outbound_enabled)}
        elif kind == "wallet":
            row = await owned(M["BillingWalletTransaction"])
            item = _wallet_item(row) if row is not None else None
            if item is None:
                return None
            paise = abs(int(row.amount_inr_paise or 0))
            cents = abs(int(row.amount_cents or 0))
            facts = {"amount": money_inr(paise) if paise else (f"${cents / 100:,.2f}" if cents else None),
                     "kindLabel": _wallet_label(row.kind), "at": _iso(row.created_at)}
        elif kind == "channel":
            row = await owned(M["TenantChannelEvent"])
            if row is None:
                return None
            item = _channel_item(row)
            paise = abs(int(row.amount_inr_paise or 0))
            facts = {"kindLabel": _channel_label(row.kind), "channelsBefore": row.channels_before,
                     "channelsAfter": row.channels_after, "amount": money_inr(paise) if paise else None,
                     "at": _iso(row.created_at)}
        elif kind == "alert":
            alerts = await _system_alerts(session, M, tenant_id=tenant_id)
            item = next((a for a in alerts if a["id"] == item_id), None)
            if item is None:
                return None
            if item["type"] == "billing.low":
                facts = {"balance": money_inr(int(item["meta"].get("balanceInrPaise") or 0))}
        else:
            return None

        if source_call:
            record = await _call_record(session, M, tenant_id, source_call)
            if record is not None:
                related.update(await _related_to_call(session, M, tenant_id, source_call, names))
                # The item itself is not "related" to itself.
                for key in ("callbacks", "followUps", "languageRequests", "integrationActions"):
                    related[key] = [r for r in related.get(key, []) if r["id"] != item["id"]]

    if lead_out is not None:
        try:
            from server.services.saas.lead_scoring import enrich_leads

            enriched = (await enrich_leads([dict(lead_out)], tenant_id))[0] or {}
            lead_out["assessment"] = enriched.get("assessment")
            lead_out["doNotCall"] = bool(enriched.get("doNotCall"))
        except Exception:  # noqa: BLE001 -- the score is optional.
            lead_out["assessment"] = None

    await _enrich_calls([item, *(r for rows in related.values() for r in rows)], str(tenant_id))
    if record is not None:
        record = await _enrich_call_record(record, tenant_id)
        record.pop("tenant_id", None)
        record["agent_name"] = names.get(str(record.get("agent_id") or ""))
        record["outcome_label"] = _DISPOSITION_LABEL.get(str(record.get("disposition") or "").lower())
    return {
        "item": _public(item),
        "call": record,
        "related": {k: [_public(r) for r in v] for k, v in related.items()},
        "lead": lead_out,
        "campaign": campaign_out,
        "facts": {k: v for k, v in facts.items() if v is not None},
        "generatedAt": _iso(now),
    }
