"""Server-side support for a quieter console: cached insights, batched campaign
analytics, and no carrier round trip for an already-approved KYC refresh."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.services.saas import cost_insights

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clear_cache():
    cost_insights.clear_cost_insights_cache()
    yield
    cost_insights.clear_cost_insights_cache()


async def test_cost_insights_are_cached_per_window_for_five_minutes(monkeypatch):
    builds: list[int] = []

    async def build(days):
        builds.append(days)
        return {"days": days, "build": len(builds)}

    clock = [1000.0]
    monkeypatch.setattr(cost_insights, "_build_cost_insights", build)
    monkeypatch.setattr(cost_insights.time, "monotonic", lambda: clock[0])

    first = await cost_insights.load_cost_insights(30)
    assert await cost_insights.load_cost_insights(30) == first
    assert builds == [30]
    # A different window is its own entry.
    await cost_insights.load_cost_insights(7)
    assert builds == [30, 7]
    # An explicit refresh recomputes.
    await cost_insights.load_cost_insights(30, fresh=True)
    assert builds == [30, 7, 30]
    # Expiry recomputes.
    clock[0] += cost_insights.CACHE_TTL_SECONDS + 1
    await cost_insights.load_cost_insights(30)
    assert builds == [30, 7, 30, 30]


async def test_approved_voice_kyc_refresh_skips_the_carrier_but_gates_still_check(monkeypatch):
    from server.services.saas import voice_kyc_service as svc

    account = SimpleNamespace(
        provisioning_status="active", auth_id="SA_1", encrypted_auth_token="x",
        last_status_sync_at=NOW - timedelta(hours=1), account_enabled=True,
        kyc_calls_blocked=False, kyc_status="approved", verifications={},
        business_type="company", account_name="Synthetic Ltd",
    )

    async def get_account(_tid):
        return account

    class Carrier:
        def __init__(self):
            raise AssertionError("carrier must not be called")

    import server.services.vobiz_client as vobiz_client
    monkeypatch.setattr(svc, "_get_account", get_account)
    monkeypatch.setattr(vobiz_client, "VobizClient", Carrier)

    status = await svc.refresh_kyc_status(uuid.uuid4(), force=True, skip_if_approved=True)
    assert status["approved"] is True
    # Enforcement still forces a live check.
    with pytest.raises((AssertionError, svc.VoiceKycError)):
        await svc.refresh_kyc_status(uuid.uuid4(), force=True)


@pytest.fixture
async def campaign_db(monkeypatch, tmp_path):
    from server.db.models.entities import Agent, Tenant
    from server.db.models.phase5_models import Campaign, CampaignContact
    from server.routes import campaigns as routes

    tables = [Tenant, Agent, Campaign, CampaignContact]
    changed = [(c, c.type) for m in tables for c in m.__table__.columns if isinstance(c.type, (ARRAY, JSONB))]
    for c, _ in changed:
        c.type = JSON()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'campaigns.db'}")
    try:
        async with engine.begin() as conn:
            for model in tables:
                await conn.run_sync(lambda sync, table=model.__table__: table.create(sync))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(routes, "get_session_factory", lambda: factory)
        tid, aid = uuid.uuid4(), uuid.uuid4()
        running, done = uuid.uuid4(), uuid.uuid4()
        async with factory() as session:
            session.add_all([
                Tenant(tenant_id=tid, name="Synthetic"), Agent(agent_id=aid, tenant_id=tid, name="A"),
                Campaign(campaign_id=running, tenant_id=tid, agent_id=aid, name="Run", status="running",
                         schedule={}, retry_rules={}, created_at=NOW),
                Campaign(campaign_id=done, tenant_id=tid, agent_id=aid, name="Done", status="completed",
                         schedule={}, retry_rules={}, created_at=NOW - timedelta(days=1)),
            ])
            for i, (status, tries) in enumerate([("connected", 1), ("completed", 2), ("pending", 0), ("dialing", 1)]):
                session.add(CampaignContact(campaign_id=running, phone_e164=f"+1202555010{i}", status=status,
                                            attempts=tries, metadata_={}, resolved_variables={}))
            session.add(CampaignContact(campaign_id=done, phone_e164="+12025550199", status="completed",
                                        attempts=3, metadata_={}, resolved_variables={}))
            await session.commit()
        yield SimpleNamespace(routes=routes, tid=tid, running=str(running), done=str(done))
    finally:
        await engine.dispose()
        for c, original in changed:
            c.type = original


async def test_campaign_list_embeds_the_same_analytics_as_the_per_campaign_endpoint(campaign_db):
    ctx = SimpleNamespace(role="customer_admin", workspace_tenant_id=campaign_db.tid)
    listed = await campaign_db.routes.list_campaigns(limit=50, offset=0, ctx=ctx)
    by_id = {c["id"]: c for c in listed["campaigns"]}
    for cid in (campaign_db.running, campaign_db.done):
        single = await campaign_db.routes.campaign_analytics(cid, ctx=ctx)
        assert by_id[cid]["analytics"] == single
    assert by_id[campaign_db.running]["analytics"]["connects"] == 2
    assert by_id[campaign_db.running]["analytics"]["attempts"] == 4
    assert by_id[campaign_db.running]["totalContacts"] == 4
