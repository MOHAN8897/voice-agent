"""Real persistence and authorization for internal actions and action discovery."""
import uuid

import pytest
from sqlalchemy import select

from server.tests.test_integration_security_hardening import AID, OTHER, TID
from server.tests.test_integration_security_hardening import db as shared_db

db = shared_db


@pytest.fixture
async def call_db(db, monkeypatch):
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import ARRAY

    from server.db import connection
    from server.db.models.entities import Base, Call
    from server.db.models.saas_models import Lead

    for model in (Call, Lead):
        for column in model.__table__.columns:
            if isinstance(column.type, ARRAY):
                monkeypatch.setattr(column, "type", column.type.with_variant(JSON(), "sqlite"))

    async with db.kw["bind"].begin() as session:
        await session.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[Call.__table__, Lead.__table__]))
    monkeypatch.setattr(connection, "get_session_factory", lambda: db)
    call_id = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000201")
    async with db() as session:
        session.add(Call(call_id=call_id, tenant_id=TID, agent_id=AID, combination_id="test",
                         storage_path="test-call", channel="pstn", tier="medium"))
        await session.commit()
    return db, str(call_id)


@pytest.mark.asyncio
async def test_enquiry_creates_one_visible_lead_and_cannot_cross_tenants(call_db):
    from server.call.enquiry import save_enquiry
    from server.db.models.saas_models import Lead

    factory, call_id = call_db
    args = {"request": "Please record my request for 100 cards", "customer_name": "Sai Kiran", "quantity": "100"}
    first = await save_enquiry(call_id=call_id, tenant_id=str(TID), agent_id=str(AID), arguments=args)
    retry = await save_enquiry(call_id=call_id, tenant_id=str(TID), agent_id=str(AID), arguments=args)
    foreign = await save_enquiry(call_id=call_id, tenant_id=str(OTHER), agent_id=str(AID), arguments=args)
    assert first["request_saved"] and retry["already_saved"]
    assert foreign["status"] == "error"
    updated = await save_enquiry(call_id=call_id, tenant_id=str(TID), agent_id=str(AID),
                                 arguments={**args, "quantity": "200"})
    assert updated["updated"] is True
    async with factory() as session:
        rows = (await session.execute(select(Lead).where(Lead.tenant_id == TID))).scalars().all()
        assert len(rows) == 1
        assert rows[0].name == "Sai Kiran" and "100" in rows[0].notes
        assert rows[0].stage == "contacted"
        assert '"quantity": "200"' in rows[0].notes


@pytest.mark.asyncio
async def test_native_actions_need_current_owned_call_context(call_db, monkeypatch):
    from types import SimpleNamespace

    from server.call import call_context
    from server.call.enquiry import execute_platform_action

    _, call_id = call_db
    ctx = SimpleNamespace(tenant_id=TID, agent_id=AID, compiled_brain_text="Answer course questions only.")
    monkeypatch.setattr(call_context, "get", lambda _: ctx)
    result = await execute_platform_action("CONFIRM_ORDER", call_id=call_id, tenant_id=str(TID), agent_id=str(AID), arguments={})
    assert result["status"] == "error"
    result = await execute_platform_action("SAVE_ENQUIRY", call_id=call_id, tenant_id=str(OTHER), agent_id=str(AID), arguments={"request": "Please note my question"})
    assert result["status"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize("direction,expected", [("outbound", "+12025550102"), ("inbound", "+12025550101")])
async def test_enquiry_uses_customer_phone_instead_of_business_line(call_db, monkeypatch, direction, expected):
    from server.call.call_ledger import call_ledger
    from server.call.enquiry import save_enquiry
    from server.db.models.saas_models import Lead

    factory, call_id = call_db
    monkeypatch.setattr(call_ledger, "read_meta", lambda _: {
        "direction": direction, "caller_id": "+12025550101", "callee_e164": "+12025550102",
    })
    result = await save_enquiry(call_id=call_id, tenant_id=str(TID), agent_id=str(AID), arguments={"request": "Please note my enquiry"})
    assert result["request_saved"]
    async with factory() as session:
        row = (await session.execute(select(Lead).where(Lead.tenant_id == TID))).scalar_one()
        assert row.phone == expected


@pytest.mark.asyncio
async def test_compile_and_call_share_agent_whitelist_and_platform_actions(call_db):
    from server.brain.capabilities import apply_available_tools
    from server.brain.compiled_brain_artifact import assemble_unified_brain
    from server.db.models.integration_models import AgentIntegration
    from server.services.tool_schema_registry import get_tools_for_agent

    factory, _ = call_db
    async with factory() as session:
        session.add(AgentIntegration(tenant_id=TID, agent_id=AID, app_name="GOOGLECALENDAR", enabled=True,
                                    timing_mode="in_call", action_whitelist=["GOOGLECALENDAR_FIND_FREE_SLOTS"]))
        await session.commit()
    # An order-only script never schedules, so its calendar tools are not offered
    # (call 35002575 carried ten unused calendar schemas on every turn).
    brain = assemble_unified_brain(language="te-IN", script="Collect delivery address and quantity, then confirm the order.")
    tools = await get_tools_for_agent(["GOOGLECALENDAR"], str(TID), str(AID), factory,
                                     include_platform=True, compiled_text=brain)
    names = {tool["name"] for tool in tools}
    assert names == {"SAVE_ENQUIRY", "REQUEST_HUMAN_HANDOFF", "CONFIRM_ORDER"}
    compiled = apply_available_tools(brain, tools)
    assert "GOOGLECALENDAR_FIND_FREE_SLOTS" not in compiled
    assert "order_confirmation: allowed" in compiled

    # A script that books keeps only the whitelisted calendar action.
    booking = assemble_unified_brain(
        language="te-IN",
        script="Find a free slot for a site visit and book the appointment, then confirm the order.",
    )
    tools = await get_tools_for_agent(["GOOGLECALENDAR"], str(TID), str(AID), factory,
                                     include_platform=True, compiled_text=booking)
    compiled = apply_available_tools(booking, tools)
    assert "GOOGLECALENDAR_FIND_FREE_SLOTS" in compiled
    assert "GOOGLECALENDAR_CREATE_EVENT" not in compiled


@pytest.mark.asyncio
async def test_disabled_tenant_has_no_discoverable_actions(call_db):
    from server.db.models.entities import Tenant
    from server.services.tool_schema_registry import get_tools_for_agent

    factory, _ = call_db
    async with factory() as session:
        tenant = await session.get(Tenant, TID)
        tenant.status = "suspended"
        await session.commit()
    assert await get_tools_for_agent(["GOOGLECALENDAR"], str(TID), str(AID), factory, include_platform=True) == []


@pytest.mark.asyncio
async def test_post_call_catalog_actions_require_explicit_in_call_permission(call_db):
    from server.db.models.integration_models import AgentIntegration, TenantIntegration
    from server.services.tool_router import DialtactToolRouter
    from server.services.tool_schema_registry import get_tools_for_agent

    factory, _ = call_db
    async with factory() as session:
        session.add(TenantIntegration(tenant_id=TID, app_name="GMAIL", connection_id="synthetic-gmail", metadata_={"gateway_verified": True}))
        await session.commit()
    router = DialtactToolRouter()
    assert not await router.authorized(str(TID), str(AID), "GMAIL_SEND_EMAIL")
    assert await get_tools_for_agent(["GMAIL", "TODOIST"], str(TID), str(AID), factory) == []
    async with factory() as session:
        session.add(AgentIntegration(tenant_id=TID, agent_id=AID, app_name="GMAIL", enabled=True,
                                    timing_mode="in_call", action_whitelist=["GMAIL_CREATE_DRAFT"]))
        await session.commit()
    tools = await get_tools_for_agent(["GMAIL"], str(TID), str(AID), factory)
    assert [tool["name"] for tool in tools] == ["GMAIL_CREATE_DRAFT"]
    assert await router.authorized(str(TID), str(AID), "GMAIL_CREATE_DRAFT")
    assert not await router.authorized(str(TID), str(AID), "GMAIL_SEND_EMAIL")
