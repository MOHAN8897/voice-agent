"""The calls list pages, filters and counts in SQL, so big tenants get correct totals."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, event, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.call import call_store as store_module
from server.call.call_store import call_attempt_store, call_store
from server.call.call_timeline import list_timeline
from server.db.models.entities import Agent, Call, CallAttempt, Tenant
from server.db.models.saas_models import BillingWallet, BillingWalletTransaction, Lead
from server.services.saas.agent_performance import performance

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
async def db(monkeypatch, tmp_path):
    from server.db import connection
    from server.services.saas import agent_performance

    tables = [Tenant, Agent, Call, CallAttempt, Lead, BillingWallet, BillingWalletTransaction]
    changed = [(c, c.type) for m in tables for c in m.__table__.columns if isinstance(c.type, (ARRAY, JSONB))]
    for c, _ in changed:
        c.type = JSON()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'calls.db'}")
    try:
        async with engine.begin() as conn:
            for model in tables:
                await conn.run_sync(lambda sync, table=model.__table__: table.create(sync))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        for module in (store_module, connection, agent_performance):
            monkeypatch.setattr(module, "get_session_factory", lambda: factory)
        call_attempt_store.reset_for_tests()
        tid, aid = uuid.uuid4(), uuid.uuid4()
        async with factory() as session:
            session.add_all([Tenant(tenant_id=tid, name="Synthetic"), Agent(agent_id=aid, tenant_id=tid, name="A")])
            # 130 finished outbound calls with a materialised status.
            for i in range(130):
                session.add(Call(call_id=uuid.uuid4(), tenant_id=tid, agent_id=aid, combination_id="c",
                    storage_path="t", direction="outbound", channel="pstn", status="outbound",
                    started_at=NOW - timedelta(minutes=i), ended_at=NOW - timedelta(minutes=i) + timedelta(seconds=30),
                    duration_sec=30, is_test=False, status_tags=[]))
            # 5 legacy rows written before the status column (status NULL, ended, 2s inbound -> missed).
            for i in range(5):
                session.add(Call(call_id=uuid.uuid4(), tenant_id=tid, agent_id=aid, combination_id="c",
                    storage_path="t", direction="inbound", channel="pstn", status=None,
                    started_at=NOW - timedelta(days=1, minutes=i), ended_at=NOW - timedelta(days=1, minutes=i) + timedelta(seconds=2),
                    duration_sec=2, is_test=False, status_tags=[]))
            # 2 open calls (status is NULL until the call ends).
            for i in range(2):
                session.add(Call(call_id=uuid.uuid4(), tenant_id=tid, agent_id=aid, combination_id="c",
                    storage_path="t", direction="inbound", channel="pstn", status=None,
                    started_at=NOW + timedelta(minutes=i + 1), is_test=False, status_tags=[]))
            # A test call never shows up.
            session.add(Call(call_id=uuid.uuid4(), tenant_id=tid, agent_id=aid, combination_id="c",
                storage_path="t", direction="inbound", channel="browser", status="answered",
                started_at=NOW, ended_at=NOW, duration_sec=60, is_test=True, status_tags=[]))
            linked = Call(call_id=uuid.uuid4(), tenant_id=tid, agent_id=aid, combination_id="c",
                storage_path="t", direction="inbound", channel="pstn", status="answered",
                started_at=NOW - timedelta(days=2), ended_at=NOW - timedelta(days=2) + timedelta(seconds=90),
                duration_sec=90, is_test=False, status_tags=[])
            session.add(linked)
            # 3 never-answered attempts plus one that became the linked call above.
            for i in range(3):
                session.add(CallAttempt(attempt_id=uuid.uuid4(), tenant_id=tid, agent_id=aid,
                    provider_call_control_id=f"ctl-{i}", direction="inbound", status="missed",
                    started_at=NOW - timedelta(hours=3, minutes=i), ended_at=NOW - timedelta(hours=3, minutes=i)))
            session.add(CallAttempt(attempt_id=uuid.uuid4(), tenant_id=tid, agent_id=aid,
                provider_call_control_id="ctl-linked", direction="inbound", status="answered",
                linked_call_id=linked.call_id, started_at=linked.started_at, answered_at=linked.started_at,
                ended_at=linked.ended_at))
            await session.commit()
        yield SimpleNamespace(engine=engine, factory=factory, tid=str(tid), aid=str(aid))
    finally:
        await engine.dispose()
        for c, original in changed:
            c.type = original


def _capture_sql(engine):
    seen: list[str] = []

    def before(conn, cursor, statement, *args):
        seen.append(statement.lower())

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    return seen


async def test_total_counts_every_row_beyond_the_old_100_cap(db):
    items, total = await list_timeline(tenant_id=db.tid, limit=20, offset=0)
    # 130 outbound + 5 legacy + 2 open + 1 linked call + 3 unlinked attempts; no test call, no duplicate.
    assert total == 141
    assert len(items) == 20
    assert items[0]["in_progress"] is True
    tail, tail_total = await list_timeline(tenant_id=db.tid, limit=20, offset=140)
    assert tail_total == 141 and len(tail) == 1
    # The deepest page is the oldest row: the linked call, not its attempt.
    assert tail[0]["is_attempt"] is False and tail[0]["status"] == "answered"


async def test_count_is_a_sql_count_not_a_row_load(db):
    seen = _capture_sql(db.engine)
    rows, total = await call_store.list_calls(tenant_id=db.tid, limit=5)
    assert total == 138 and len(rows) == 5
    assert any("count(" in s for s in seen)


async def test_status_and_direction_filters_run_in_sql_and_include_legacy_rows(db):
    missed, missed_total = await list_timeline(tenant_id=db.tid, statuses=["missed"], limit=50)
    assert missed_total == 8  # 5 legacy calls (materialised on first filter) + 3 attempts
    assert {i["status"] for i in missed} == {"missed"}
    async with db.factory() as session:
        nulls = (await session.execute(select(Call).where(Call.status.is_(None), Call.ended_at.isnot(None)))).all()
    assert nulls == []

    outbound, outbound_total = await list_timeline(tenant_id=db.tid, direction="outbound", limit=10)
    assert outbound_total == 130 and len(outbound) == 10
    assert all(i["direction"] == "outbound" for i in outbound)

    live, live_total = await list_timeline(tenant_id=db.tid, statuses=["in_progress"], limit=10)
    assert live_total == 2 and all(i["in_progress"] for i in live)


async def test_performance_groups_by_status_and_classifies_only_null_rows(db):
    result = await performance(db.tid)
    assert result["total"] == 141
    assert result["counts"]["outbound"] == 130
    assert result["counts"]["missed"] == 8
    assert result["counts"]["in_progress"] == 2
    assert result["counts"]["answered"] == 1
    # Connected: every call row (138) — unanswered attempts never connect.
    assert result["connected"] == 138
    assert result["completedConnected"] == 136
    assert result["totalDurationSec"] == 130 * 30 + 5 * 2 + 90
