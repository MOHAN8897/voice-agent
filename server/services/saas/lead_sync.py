"""Turn a finished call's LLM outcome into an owned, staged lead.

The post-call pipeline already produces a rich judgement — disposition,
confidence, summaries, next action, extracted fields, objections. None of it
reached the CRM: `leads` was written only by manual creation, so after every call
the pipeline decided a stage and then discarded it.

Two rules make this safe to run on every call:

* **Never regress.** A stage only ever moves forward. A callback on an already
  qualified lead must not knock it back to "Contacted", or the pipeline would
  silently devalue good leads every time someone rings again.
* **Never fabricate.** A call with no transcript and no outcome produces no lead.
  An empty board should mean "no calls", not "the model invented something".
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Conversion is tenant-confirmed. An LLM disposition alone is not proof of a sale.
STAGE_ORDER: tuple[str, ...] = ("new", "contacted", "qualified", "meeting_booked", "converted", "unqualified")

#: The LLM's nine dispositions collapsed onto those five. `unqualified` is last in
#: STAGE_ORDER but must never be *advanced into* from a qualified lead, so
#: TERMINAL_DISPOSITIONS is handled separately below.
DISPOSITION_TO_STAGE: dict[str, str] = {
    "new_lead": "new",
    "interested": "contacted",
    "callback_required": "contacted",
    "qualified": "qualified",
    "converted": "qualified",
    # An expressed visit plan is interest, not evidence of a calendar booking.
    # Tenants can confirm a booked meeting through the existing lead editor.
    "site_visit_planned": "qualified",
    "not_interested": "unqualified",
    "wrong_number": "unqualified",
    "no_outcome": "new",
}

#: Dispositions that mean "this is not a lead". They must never create a row, and
#: must never overwrite an existing one — a wrong number is not a sales outcome.
REJECTION_DISPOSITIONS = frozenset({"not_interested", "wrong_number", "no_outcome"})

#: Keys `merge_outcome_facts` may use for the caller's name, best first.
_NAME_KEYS = ("name", "caller_name", "customer_name", "full_name", "contact_name")
#: …and for a callback number.
_PHONE_KEYS = ("phone", "callback_phone", "contact", "phone_number", "mobile")


#: Tags the summary step produces that mean the caller wants to buy.
PURCHASE_INTENT_TAGS = frozenset({"intent:purchase", "intent:quote", "intent:booking", "intent:renewal", "signal:ready_to_buy"})
#: Fact keys that carry how much the caller wants.
_QUANTITY_KEYS = ("quantity", "qty", "units", "order_quantity", "count")


def stage_for_disposition(disposition: str | None) -> str:
    return DISPOSITION_TO_STAGE.get(str(disposition or "").strip().lower(), "new")


def engagement_stage(outcome: dict[str, Any], meta: dict[str, Any] | None = None) -> str | None:
    """A stage earned by what the caller asked for, whatever the disposition says.

    A purchase intent with a stated quantity, or the caller's own request for a
    callback or a manager/owner handoff, is an engaged lead: "qualified" on this
    board. Read from the structured tags and facts the summary step writes, never
    from phrases, so it holds in every language.
    """
    meta = meta or {}
    facts = outcome.get("facts") if isinstance(outcome.get("facts"), dict) else {}
    lowered = {str(k).strip().lower(): str(v).strip() for k, v in facts.items() if str(v or "").strip()}
    tags = {str(t) for t in [*(outcome.get("status_tags") or []), *(outcome.get("tags") or [])]}
    quantity = any(re.search(r"\d", lowered.get(key, "")) for key in _QUANTITY_KEYS)
    if tags & PURCHASE_INTENT_TAGS and quantity:
        return "qualified"
    saved = meta.get("callback_request") if isinstance(meta.get("callback_request"), dict) else {}
    callback = (
        lowered.get("callback_requested") == "true"
        or outcome.get("contact_preference") == "callback"
        or (bool(saved) and not meta.get("callback_cancelled")
            and str(saved.get("status") or "requested") in {"requested", "saved", "scheduled"})
    )
    handoff = (lowered.get("handoff_requested") == "true" or "followup:handoff" in tags
               or isinstance(meta.get("human_handoff"), dict) and bool(meta["human_handoff"]))
    return "qualified" if callback or handoff else None


def outcome_stage(outcome: dict[str, Any], meta: dict[str, Any] | None = None) -> str:
    """The furthest stage this call supports: its disposition or the caller's engagement."""
    stage = stage_for_disposition(outcome.get("disposition"))
    engaged = engagement_stage(outcome, meta)
    return engaged if engaged and stage_rank(engaged) > stage_rank(stage) else stage


def better_name(stored: str | None, captured: str) -> bool:
    """Whether a name heard on this call should replace the stored one.

    Only a missing placeholder or a shorter form of the same name ("Sai" ->
    "Saikiran", "Sai" -> "Sai Kiran") is replaced. A different name is kept: it
    may have been typed by a person, and the lead row does not record who did.
    """
    old = re.sub(r"\s+", " ", str(stored or "")).strip()
    new = re.sub(r"\s+", " ", str(captured or "")).strip()
    if not new or new == "New lead":
        return False
    if not old or old == "New lead":
        return True
    old_key, new_key = old.casefold(), new.casefold()
    return len(new_key) > len(old_key) and (new_key.startswith(old_key) or new_key.replace(" ", "").startswith(old_key.replace(" ", "")))


def stage_rank(stage: str | None) -> int:
    try:
        return STAGE_ORDER.index(str(stage or "").strip().lower())
    except ValueError:
        return 0


def should_advance(new_stage: str, current_stage: str | None) -> bool:
    """Only move a lead forward, so re-calls cannot devalue it."""
    if current_stage in {"converted", "unqualified"} or new_stage in {"converted", "unqualified"}:
        return False
    return stage_rank(new_stage) > stage_rank(current_stage)


def _clean(value: Any, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _first_fact(facts: dict[str, str], keys: tuple[str, ...]) -> str:
    lowered = {str(k).strip().lower(): str(v).strip() for k, v in (facts or {}).items()}
    for key in keys:
        value = lowered.get(key)
        if value:
            return value
    return ""


def _notes_from_outcome(outcome: dict[str, Any]) -> str:
    """The owner-facing record: what happened, and what to do next."""
    lines: list[str] = []
    summary = _clean(outcome.get("summary_en"), 1200)
    if summary:
        lines.append(summary)
    action = _clean(outcome.get("next_action"), 240)
    if action:
        lines.append(f"Next step: {action}")
    objections = outcome.get("objections") or []
    if isinstance(objections, list) and objections:
        joined = ", ".join(_clean(o, 80) for o in objections if str(o).strip())
        if joined:
            lines.append(f"Objections: {joined}")
    disposition = str(outcome.get("disposition") or "").strip()
    if disposition:
        confidence = outcome.get("disposition_confidence")
        try:
            pct = f" ({round(float(confidence) * 100)}% confidence)"
        except (TypeError, ValueError):
            pct = ""
        lines.append(f"Call outcome: {disposition.replace('_', ' ')}{pct}")
    return "\n\n".join(lines)


def _phone_key(raw: str) -> str:
    """Digits-only key so +91 98765 43210 and 919876543210 are one lead."""
    return re.sub(r"\D", "", str(raw or ""))


def _extract_phone(facts: dict[str, str], meta: dict[str, Any]) -> str:
    """The number to key the lead on, falling back to the call's own parties."""
    from_facts = _clean(_first_fact(facts, _PHONE_KEYS), 32)
    if 7 <= len(_phone_key(from_facts)) <= 15:
        return from_facts
    direction = str(meta.get("direction") or "").lower()
    outbound = direction in ("outbound", "outgoing", "outbound-api")
    candidate = meta.get("callee_e164") if outbound else meta.get("caller_id")
    candidate = _clean(candidate, 32)
    return candidate if 7 <= len(_phone_key(candidate)) <= 15 else ""


async def sync_outcome_to_lead(
    *,
    outcome: dict[str, Any],
    tenant_id: str | uuid.UUID,
    agent_id: str | uuid.UUID | None,
    meta: dict[str, Any] | None = None,
    call_id: str | None = None,
) -> dict[str, Any] | None:
    """Create or advance the lead this call produced. Returns the lead, or None.

    Never raises: a CRM write failing must not take down the call pipeline.
    """
    meta = meta or {}
    disposition = str(outcome.get("disposition") or "").strip().lower()
    if disposition in REJECTION_DISPOSITIONS:
        return None

    facts = outcome.get("facts") if isinstance(outcome.get("facts"), dict) else {}
    phone = _extract_phone(facts, meta)
    name = _clean(_first_fact(facts, _NAME_KEYS), 255) or "New lead"
    email = _clean(facts.get("email"), 320) or None
    stage = outcome_stage(outcome, meta)
    notes = _notes_from_outcome(outcome)
    call_marker = f"[Call reference: {call_id}]" if call_id else ""
    if call_marker:
        notes = f"{call_marker}\n{notes}".strip()

    factory = _session_factory()
    if factory is None:
        return None

    try:
        tenant_uuid = uuid.UUID(str(tenant_id))
    except (TypeError, ValueError):
        logger.warning("lead_sync: unusable tenant_id %r", tenant_id)
        return None
    agent_str = str(agent_id) if agent_id else None

    try:
        async with factory() as session:
            from sqlalchemy import select

            from server.db.models.entities import Tenant
            from server.db.models.saas_models import Lead

            # Serialise automatic upserts within this tenant. Two simultaneous
            # post-call jobs must not both decide that the same contact is new.
            await session.execute(select(Tenant.tenant_id).where(Tenant.tenant_id == tenant_uuid).with_for_update())

            stmt = select(Lead).where(Lead.tenant_id == tenant_uuid)
            stmt = stmt.where(Lead.agent_id == agent_str if agent_str else Lead.agent_id.is_(None))
            if phone:
                # Match on digits so formatting differences do not fork a lead.
                digits = _phone_key(phone)
                if getattr(getattr(session.bind, "dialect", None), "name", "") == "postgresql":
                    from sqlalchemy import func

                    row = (await session.execute(stmt.where(func.regexp_replace(Lead.phone, r"\D", "", "g") == digits)
                        .order_by(Lead.created_at, Lead.lead_id).limit(1).with_for_update())).scalars().first()
                else:
                    rows = (await session.execute(stmt.with_for_update())).scalars().all()
                    row = next((r for r in rows if _phone_key(r.phone) == digits), None)
            elif email:
                from sqlalchemy import func

                row = (await session.execute(stmt.where(func.lower(Lead.email) == email.lower())
                    .order_by(Lead.created_at, Lead.lead_id).limit(1).with_for_update())).scalars().first()
            else:
                # Never merge unrelated unidentified callers. Only a replay of
                # this exact call may reuse an identity-less lead.
                row = (await session.execute(stmt.where(Lead.notes.contains(call_marker, autoescape=True))
                    .limit(1).with_for_update())).scalars().first() if call_marker else None

            now = datetime.now(timezone.utc)
            if row is None:
                row = Lead(
                    tenant_id=tenant_uuid,
                    agent_id=agent_str,
                    name=name,
                    phone=phone or None,
                    email=email,
                    stage=stage,
                    notes=notes or None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                action = "created"
            else:
                action = "advanced" if should_advance(stage, row.stage) else "unchanged"
                if action == "advanced":
                    row.stage = stage
                # Enrich blanks; an unverified later call must not overwrite a
                # contact identity already maintained in the tenant's CRM.
                if better_name(row.name, name):
                    row.name = name
                if email and not row.email:
                    row.email = email
                if phone and not row.phone:
                    row.phone = phone
                if notes:
                    previous = (row.notes or "").strip()
                    if call_marker and call_marker not in previous:
                        row.notes = f"{previous}\n\n---\n{notes}".strip() if previous else notes
                    elif not previous:
                        row.notes = notes
                if agent_str and not row.agent_id:
                    row.agent_id = agent_str
                row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return {
                "leadId": str(row.lead_id),
                "agentId": row.agent_id,
                "stage": row.stage,
                "action": action,
            }
    except Exception:
        logger.exception("lead_sync failed call=%s disposition=%s", call_id, disposition)
        return None


def _session_factory():
    from server.db.connection import get_session_factory

    return get_session_factory()
