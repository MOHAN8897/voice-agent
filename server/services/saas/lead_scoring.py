"""Explainable priority, not a conversion probability or permission to contact."""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.followup_models import AgentFollowUpPolicy, LeadAssessment
from server.db.models.phase5_models import DncEntry
from server.services.saas.followup_policy import FollowUpConfig, utc

logger = logging.getLogger(__name__)


def score_outcome(outcome: dict, config: FollowUpConfig | None = None) -> dict:
    cfg = config or FollowUpConfig()
    disposition = str(outcome.get("disposition") or "no_outcome")
    confidence = outcome.get("disposition_confidence")
    try:
        confidence = float(confidence)
        reliable = math.isfinite(confidence) and 0.6 <= confidence <= 1
        if not math.isfinite(confidence):
            confidence = None
    except (TypeError, ValueError):
        reliable = False
    base = {"score": None, "band": "unscored", "disposition": disposition,
            "confidence": confidence, "components": [], "version": 1,
            "note": "Priority score uses recorded business signals; it is not a conversion probability or contact consent."}
    if not cfg.scoringEnabled:
        return {**base, "reason": "disabled"}
    if outcome.get("contact_preference") == "do_not_call":
        return {**base, "score": 0, "band": "disqualified", "reason": "caller_opt_out"}
    if not reliable or disposition == "no_outcome":
        return {**base, "reason": "insufficient_evidence"}
    if disposition in ("wrong_number", "not_interested", "do_not_call", "opt_out"):
        return {**base, "score": 0, "band": "disqualified", "reason": disposition}
    facts = outcome.get("facts") or {}
    if not isinstance(facts, dict):
        facts = {}
    normalized = {str(k).lower(): str(v).strip() for k, v in facts.items() if v is not None and str(v).strip()}
    selected_offer = any(normalized.get(key) for key in ("product", "service", "selected_product", "course"))
    contextual_requirement = any(normalized.get(key.strip().lower()) for key in cfg.scoreFactKeys["requirements"]
                                 if key.strip().lower() not in {"product", "service", "product_interest", "selected_product", "course"})
    components = []
    for key, weight in cfg.scoreWeights.items():
        evidence = (
            disposition
            if key == "interest"
            and (
                disposition in ("interested", "qualified", "site_visit_planned", "converted", "order_requested")
                or (selected_offer and contextual_requirement)
            )
            else ""
        )
        if key != "interest":
            evidence = next((name for name in cfg.scoreFactKeys[key] if normalized.get(name.strip().lower())), "")
        components.append({"signal": key, "points": weight if evidence else 0, "max": weight, "evidence": evidence or "not recorded"})
    score = sum(c["points"] for c in components)
    return {**base, "score": score, "band": "hot" if score >= cfg.hotThreshold else "warm" if score >= cfg.warmThreshold else "cold", "components": components, "reason": "recorded_signals"}


def assessment_time(meta: dict) -> datetime | None:
    try:
        return utc(datetime.fromisoformat(str(meta.get("ended_at")).replace("Z", "+00:00")))
    except ValueError:
        return None


async def persist_assessment(tenant_id: str, agent_id: str, lead_id: str, call_id: str, outcome: dict, at: datetime | None = None) -> dict | None:
    factory = get_session_factory()
    if factory is None:
        return None
    try:
        tid, aid, lid = uuid.UUID(str(tenant_id)), uuid.UUID(str(agent_id)), uuid.UUID(str(lead_id))
        async with factory() as session:
            # Lock the lead to serialize concurrent outcomes, and verify tenant ownership.
            from server.db.models.saas_models import Lead
            lead = await session.scalar(select(Lead).where(Lead.tenant_id == tid, Lead.lead_id == lid).with_for_update())
            if lead is None or lead.agent_id != str(aid):
                return None
            policy = await session.scalar(select(AgentFollowUpPolicy).where(AgentFollowUpPolicy.tenant_id == tid, AgentFollowUpPolicy.agent_id == aid))
            assessment = score_outcome(outcome, FollowUpConfig.model_validate(policy.config if policy else {}))
            row = await session.scalar(select(LeadAssessment).where(LeadAssessment.tenant_id == tid, LeadAssessment.lead_id == lid))
            timestamp = at or datetime.now(timezone.utc)
            if row and utc(row.updated_at) > utc(timestamp):
                return row.assessment  # An older analysis finishing late must not replace a newer result.
            if row is None:
                row = LeadAssessment(tenant_id=tid, lead_id=lid)
                session.add(row)
            row.source_call_id, row.assessment, row.updated_at = call_id, assessment, timestamp
            await session.commit()
            return assessment
    except Exception as exc:
        logger.warning("lead.assessment_unavailable kind=%s", type(exc).__name__)
        return None


async def assess_existing_contact(meta: dict, call_id: str, outcome: dict) -> dict | None:
    """Negative outcomes update a known lead's priority without creating a lead or changing its stage."""
    if outcome.get("disposition") not in ("not_interested", "wrong_number") and outcome.get("contact_preference") != "do_not_call":
        return None
    from server.services.saas.call_callback_service import normalize_e164
    from server.db.models.saas_models import Lead
    try:
        tid, aid = uuid.UUID(str(meta.get("tenant_id"))), str(uuid.UUID(str(meta.get("agent_id"))))
        facts = outcome.get("facts") or {}
        phone = normalize_e164(facts.get("phone") or facts.get("callback_phone") or
            (meta.get("callee_e164") if meta.get("direction") == "outbound" else meta.get("caller_id")))
        if not phone or get_session_factory() is None:
            return None
        async with get_session_factory()() as session:
            rows = await session.stream_scalars(select(Lead).where(Lead.tenant_id == tid, Lead.agent_id == aid,
                Lead.phone.is_not(None)).order_by(Lead.created_at, Lead.lead_id).execution_options(yield_per=100))
            lead_id = None
            async for row in rows:
                if normalize_e164(row.phone) == phone:
                    lead_id = str(row.lead_id)
                    break
            if lead_id is None:
                return None
        return await persist_assessment(str(tid), aid, lead_id, call_id, outcome, at=assessment_time(meta))
    except Exception as exc:
        logger.warning("lead.rejection_assessment_unavailable kind=%s", type(exc).__name__)
        return None


async def enrich_leads(items: list[dict], tenant_id: uuid.UUID) -> list[dict]:
    factory = get_session_factory()
    if factory is None or not items:
        return items
    from server.services.saas.call_callback_service import normalize_e164
    async with factory() as session:
        phones = {p for r in items if (p := normalize_e164(r.get("phone")))}
        blocked = set((await session.scalars(select(DncEntry.phone_e164).where(DncEntry.tenant_id == tenant_id,
            DncEntry.phone_e164.in_(phones), DncEntry.active.is_(True)))).all()) if phones else set()
    assessments = {}
    try:
        async with factory() as session:
            rows = (await session.scalars(select(LeadAssessment).where(LeadAssessment.tenant_id == tenant_id,
                LeadAssessment.lead_id.in_([uuid.UUID(r["leadId"]) for r in items])))).all()
            assessments = {str(r.lead_id): {**r.assessment, "sourceCallId": r.source_call_id, "assessedAt": r.updated_at.isoformat()} for r in rows}
    except Exception as exc:
        logger.warning("lead.score_read_unavailable kind=%s", type(exc).__name__)
    for item in items:
        item["assessment"] = assessments.get(item["leadId"])
        item["doNotCall"] = normalize_e164(item.get("phone")) in blocked
    return items


async def retire_converted_followups(tenant_id: uuid.UUID, phone: str | None) -> None:
    """Conversion retires follow-ups, without opting the customer out of all service calls."""
    from sqlalchemy import update
    from server.db.models.entities import CallCallback
    from server.services.saas.call_callback_service import normalize_e164
    target = normalize_e164(phone)
    if not target or get_session_factory() is None:
        return
    try:
        async with get_session_factory()() as session:
            await session.execute(update(CallCallback).where(CallCallback.tenant_id == tenant_id,
                CallCallback.to_e164 == target, CallCallback.mode == "requested", CallCallback.status == "requested")
                .values(status="converted", updated_at=datetime.now(timezone.utc)))
            await session.commit()
        from server.services.saas.followup_service import suppress_jobs
        await suppress_jobs(tenant_id, phone=target, reason="lead_converted")
    except Exception as exc:
        logger.warning("lead.followup_retirement_pending kind=%s", type(exc).__name__)
