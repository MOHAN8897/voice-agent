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

#: The five CRM stages the console renders, ordered so progress is comparable.
STAGE_ORDER: tuple[str, ...] = ("new", "contacted", "qualified", "meeting_booked", "unqualified")

#: The LLM's nine dispositions collapsed onto those five. `unqualified` is last in
#: STAGE_ORDER but must never be *advanced into* from a qualified lead, so
#: TERMINAL_DISPOSITIONS is handled separately below.
DISPOSITION_TO_STAGE: dict[str, str] = {
    "new_lead": "new",
    "interested": "contacted",
    "callback_required": "contacted",
    "qualified": "qualified",
    "converted": "qualified",
    "site_visit_planned": "meeting_booked",
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


def stage_for_disposition(disposition: str | None) -> str:
    return DISPOSITION_TO_STAGE.get(str(disposition or "").strip().lower(), "new")


def stage_rank(stage: str | None) -> int:
    try:
        return STAGE_ORDER.index(str(stage or "").strip().lower())
    except ValueError:
        return 0


def should_advance(new_stage: str, current_stage: str | None) -> bool:
    """Only move a lead forward, so re-calls cannot devalue it."""
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
    if from_facts:
        return from_facts
    direction = str(meta.get("direction") or "").lower()
    outbound = direction in ("outbound", "outgoing", "outbound-api")
    candidate = meta.get("callee_e164") if outbound else meta.get("caller_id")
    return _clean(candidate, 32)


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
    stage = stage_for_disposition(disposition)
    notes = _notes_from_outcome(outcome)

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

            from server.db.models.saas_models import Lead

            stmt = select(Lead).where(Lead.tenant_id == tenant_uuid)
            if agent_str:
                stmt = stmt.where(Lead.agent_id == agent_str)
            if phone:
                # Match on digits so formatting differences do not fork a lead.
                digits = _phone_key(phone)
                rows = (await session.execute(stmt)).scalars().all()
                row = next((r for r in rows if _phone_key(r.phone) == digits), None)
            else:
                # Without a number there is nothing stable to match on; only the
                # most recent lead for this agent can be safely reused.
                recent = (
                    await session.execute(
                        stmt.order_by(Lead.updated_at.desc()).limit(1)
                    )
                ).scalars().first()
                row = recent

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
                # A later call knows the caller's name better than the first one.
                if name != "New lead":
                    row.name = name
                if email and not row.email:
                    row.email = email
                if phone and not row.phone:
                    row.phone = phone
                if notes:
                    previous = (row.notes or "").strip()
                    if call_id and call_id not in previous:
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