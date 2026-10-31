"""Tenant takeout/deletion integration for the new follow-up tables only."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError

from server.db.connection import get_session_factory
from server.db.models.followup_models import AgentFollowUpPolicy, FollowUpJob, LeadAssessment


def table_not_installed(exc: DBAPIError) -> bool:
    # 046 remains supported until the additive migration is approved/applied.
    return getattr(exc.orig, "sqlstate", None) == "42P01" or "no such table:" in str(exc.orig).lower()


async def purge_followup_data(tenant_id: uuid.UUID) -> None:
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        for model in (FollowUpJob, AgentFollowUpPolicy, LeadAssessment):
            try:
                async with session.begin_nested():
                    await session.execute(delete(model).where(model.tenant_id == tenant_id))
            except DBAPIError as exc:
                if not table_not_installed(exc):
                    raise
        await session.commit()


async def export_followup_data(tenant_id: uuid.UUID) -> dict:
    from server.services.saas.followup_service import job_public, policy_public
    result = {"policies": [], "jobs": [], "leadAssessments": []}
    factory = get_session_factory()
    if factory is None:
        return result
    for model, key in ((AgentFollowUpPolicy, "policies"), (FollowUpJob, "jobs"), (LeadAssessment, "leadAssessments")):
        try:
            async with factory() as session:
                rows = (await session.scalars(select(model).where(model.tenant_id == tenant_id))).all()
                if model is AgentFollowUpPolicy:
                    result[key] = [{"agentId": str(r.agent_id), **policy_public(r)} for r in rows]
                elif model is FollowUpJob:
                    result[key] = [job_public(r) for r in rows]
                else:
                    result[key] = [{"leadId": str(r.lead_id), "sourceCallId": r.source_call_id,
                        "assessment": r.assessment, "assessedAt": r.updated_at.isoformat()} for r in rows]
        except DBAPIError as exc:
            if not table_not_installed(exc):
                raise
    return result
