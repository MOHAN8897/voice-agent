from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from server.db.models.entities import Agent, Call
from server.db.models.phase5_models import Campaign
from server.db.models.saas_models import BillingWalletTransaction
from server.services.saas import billing_wallet_service


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return iter(self.rows)


class _Session:
    def __init__(self, results):
        self.results = results
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        self.statements.append((entity, statement))
        return _Rows(self.results.get(entity, []))


@pytest.mark.asyncio
async def test_wallet_call_enrichment_queries_stay_in_tenant(monkeypatch):
    tenant_id = uuid.uuid4()
    call_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    agent_id = uuid.uuid4()
    tx = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=None,
        amount_cents=-25,
        amount_inr_paise=0,
        kind="usage_pstn",
        reference_id=f"call:{call_id}",
        created_at=None,
    )
    call = SimpleNamespace(
        call_id=call_id,
        campaign_id=campaign_id,
        agent_id=agent_id,
        duration_sec=15,
        direction="outbound",
        channel="pstn",
    )
    campaign = SimpleNamespace(campaign_id=campaign_id, name="Example campaign")
    agent = SimpleNamespace(agent_id=agent_id, name="Example agent")
    session = _Session(
        {
            BillingWalletTransaction: [tx],
            Call: [call],
            Campaign: [campaign],
            Agent: [agent],
        }
    )
    monkeypatch.setattr(billing_wallet_service, "get_session_factory", lambda: lambda: session)

    rows = await billing_wallet_service.list_wallet_transactions(tenant_id)

    assert rows[0]["campaignName"] == "Example campaign"
    assert rows[0]["agentName"] == "Example agent"
    for entity, statement in session.statements:
        if entity in (Call, Campaign, Agent):
            where = str(statement).split("WHERE", 1)[1].lower()
            assert "tenant_id" in where
