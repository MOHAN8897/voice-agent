"""A saved enquiry is an owned workspace lead, never an external handoff."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Platform-native actions: no external gateway, available on every agent's calls.
PLATFORM_ACTIONS = frozenset({"SAVE_ENQUIRY", "CONFIRM_ORDER", "REQUEST_HUMAN_HANDOFF"})

SAVE_ENQUIRY_TOOL: dict[str, Any] = {
    "type": "function", "name": "SAVE_ENQUIRY",
    "description": "Save a caller-requested enquiry for workspace review after they agree to that next step. Works without external integrations. Does not confirm an order, payment, email or scheduled callback. Announce saving only after status ok.",
    "parameters": {
        "type": "object", "additionalProperties": False,
        "properties": {key: {"type": "string", "maxLength": limit} for key, limit in (
            ("request", 1600), ("customer_name", 120), ("product", 160),
            ("quantity", 80), ("delivery_address", 400), ("payment_method", 80))},
        "required": ["request"],
    },
}


async def save_enquiry(*, call_id: str, tenant_id: str, agent_id: str, arguments: dict) -> dict:
    from server.call.call_ledger import call_ledger
    from server.db.connection import get_session_factory
    from server.db.models.entities import Call
    from server.db.models.saas_models import Lead

    factory = get_session_factory()
    try:
        tenant, agent, call = uuid.UUID(tenant_id), uuid.UUID(agent_id), uuid.UUID(call_id)
    except (ValueError, TypeError, AttributeError):
        return {"status": "error", "message": "This action is unavailable."}
    request = str(arguments.get("request") or "").strip()
    if not factory or not request or len(request) > 1600:
        return {"status": "error", "message": "A caller request is required before saving."}
    if set(arguments) - set(SAVE_ENQUIRY_TOOL["parameters"]["properties"]):
        return {"status": "error", "message": "Invalid enquiry details."}
    lead_id = uuid.uuid5(uuid.NAMESPACE_URL, f"call-enquiry:{tenant_id}:{call_id}")
    meta = await asyncio.to_thread(call_ledger.read_meta, call_id)
    customer_phone = meta.get("callee_e164") if meta.get("direction") == "outbound" else meta.get("caller_id")
    details = {key: str(value).strip()[:SAVE_ENQUIRY_TOOL["parameters"]["properties"][key]["maxLength"]]
               for key, value in arguments.items() if value is not None}
    async with factory() as session:
        owned = (await session.execute(select(Call.call_id).where(
            Call.tenant_id == tenant, Call.agent_id == agent, Call.call_id == call,
        ))).scalar_one_or_none()
        if owned is None:
            return {"status": "error", "message": "This action is unavailable."}
        existing = (await session.execute(select(Lead).where(
            Lead.tenant_id == tenant, Lead.agent_id == agent_id, Lead.lead_id == lead_id,
        ).with_for_update())).scalar_one_or_none()
        if existing is not None:
            payload = json.dumps(details, ensure_ascii=False)
            if payload in (existing.notes or ""):
                return {"status": "ok", "request_saved": True, "already_saved": True}
            existing.notes = (existing.notes or "") + "\n\nEnquiry update:\n" + payload
            if details.get("customer_name"):
                existing.name = details["customer_name"]
            await session.commit()
            return {"status": "ok", "request_saved": True, "updated": True}
        session.add(Lead(
            lead_id=lead_id, tenant_id=tenant, agent_id=agent_id,
            name=details.get("customer_name") or "New enquiry", stage="contacted",
            phone=str(customer_phone or "")[:32] or None,
            notes=f"Caller enquiry — call {call_id}\n" + json.dumps(details, ensure_ascii=False),
        ))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = (await session.execute(select(Lead.lead_id).where(
                Lead.tenant_id == tenant, Lead.agent_id == agent_id, Lead.lead_id == lead_id,
            ))).scalar_one_or_none()
            if existing is None:
                return {"status": "unknown", "message": "Saving could not be confirmed."}
    return {"status": "ok", "request_saved": True}


async def execute_platform_action(tool_name: str, *, call_id: str, tenant_id: str, agent_id: str, arguments: dict) -> dict:
    """Native audio and composed calls share the same scoped platform actions."""
    from server.call import call_context

    ctx = call_context.get(call_id)
    if (ctx is None or getattr(ctx, "status", "active") != "active" or str(getattr(ctx, "tenant_id", "")) != tenant_id
            or str(getattr(ctx, "agent_id", "")) != agent_id):
        return {"status": "error", "message": "This action is unavailable."}
    if tool_name == "SAVE_ENQUIRY":
        return await save_enquiry(call_id=call_id, tenant_id=tenant_id, agent_id=agent_id, arguments=arguments)
    if tool_name == "REQUEST_HUMAN_HANDOFF":
        from server.call.human_handoff import save_human_handoff

        return await save_human_handoff(ctx=ctx, arguments=arguments)
    from server.brain.capabilities import order_confirmation_allowed_from_script
    from server.call.order_confirmation import record_order_confirmation

    if tool_name != "CONFIRM_ORDER" or not order_confirmation_allowed_from_script(getattr(ctx, "compiled_brain_text", "")):
        return {"status": "error", "message": "Order confirmation is unavailable for this workflow."}
    return await asyncio.to_thread(record_order_confirmation, call_id=call_id, tenant_id=tenant_id,
                                   agent_id=agent_id, arguments=arguments)
