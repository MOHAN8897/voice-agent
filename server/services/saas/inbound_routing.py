"""Resolve inbound PSTN DID → tenant + agent (PRD-05, PRD-12 B4/B5)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from server.db.connection import get_session_factory
from server.db.models.entities import Agent, Tenant
from server.db.models.phase5_models import PhoneNumber
from server.services.saas.pstn_saas_stack import saas_stack_override_for_agent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InboundRoute:
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    tier: str
    language: str
    stack_override: dict


def _normalize_e164(value: str) -> str:
    v = (value or "").strip().replace(" ", "")
    if v and not v.startswith("+"):
        v = f"+{v}"
    return v


async def resolve_inbound_route(to_e164: str | None) -> InboundRoute | None:
    """None → no SaaS row (dev/default telephony may handle). 'reject' via caller hanging up."""
    if not to_e164:
        return None
    factory = get_session_factory()
    if factory is None:
        return None
    e164 = _normalize_e164(to_e164)
    async with factory() as session:
        result = await session.execute(
            select(PhoneNumber, Tenant)
            .join(Tenant, Tenant.tenant_id == PhoneNumber.tenant_id)
            .where(PhoneNumber.e164 == e164, PhoneNumber.released_at.is_(None))
        )
        row = result.first()
        if row is None:
            return None
        pn, tenant = row
        if tenant.status != "active" or tenant.deleted_at is not None:
            logger.info("[SAAS_INBOUND] reject suspended tenant did=%s", e164)
            return None
        if not pn.inbound_enabled or pn.status not in ("active", "pending"):
            logger.info("[SAAS_INBOUND] reject disabled number did=%s", e164)
            return None
        agent_uuid = pn.agent_id or tenant.default_agent_id
        if agent_uuid is None:
            logger.info("[SAAS_INBOUND] no agent for did=%s", e164)
            return None
        agent = await session.get(Agent, agent_uuid)
        if agent is None or agent.tenant_id != tenant.tenant_id:
            return None
        agent_status = str(agent.status or "").strip().lower()
        if agent_status in ("paused", "inactive", "disabled"):
            logger.info("[SAAS_INBOUND] reject paused/inactive agent=%s did=%s", agent_uuid, e164)
            return None
        agent_dict = {
            "agent_id": str(agent.agent_id),
            "languages": agent.languages or ["te-IN"],
        }
        stack_override = await saas_stack_override_for_agent(agent_dict)
        lang = str(stack_override.get("language") or (agent.languages or ["te-IN"])[0])
        return InboundRoute(
            tenant_id=tenant.tenant_id,
            agent_id=agent.agent_id,
            tier=agent.default_tier or "medium",
            language=lang,
            stack_override=stack_override,
        )
