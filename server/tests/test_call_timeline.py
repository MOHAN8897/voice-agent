"""Unified call timeline: connected calls and never-answered attempts in one list."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from server.call.call_store import call_attempt_store, call_store


@pytest.fixture(autouse=True)
def _clean_stores():
    call_store.reset_for_tests()
    call_attempt_store.reset_for_tests()
    yield
    call_store.reset_for_tests()
    call_attempt_store.reset_for_tests()


def _iso(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


async def _seed_connected_call(tenant: str, agent: str, *, minutes_ago: int, duration: int, direction="inbound", end_reason="pstn_hangup"):
    cid = str(uuid.uuid4())
    await call_store.insert(
        {
            "call_id": cid,
            "tenant_id": tenant,
            "agent_id": agent,
            "channel": "pstn",
            "direction": direction,
            "combination_id": "combo",
            "storage_path": "x",
            "started_at": _iso(minutes_ago),
            "ended_at": _iso(max(0, minutes_ago - 1)),
        }
    )
    await call_store.update(cid, {"duration_sec": duration, "end_reason": end_reason})
    return cid


async def _seed_attempt(tenant: str, agent: str, *, minutes_ago: int, status="missed", control: str | None = None):
    control = control or f"ctl-{uuid.uuid4().hex[:10]}"
    await call_attempt_store.upsert_by_control(
        control,
        tenant_id=tenant,
        agent_id=agent,
        from_number="+919999999999",
        to_number="+918000000000",
        status="in_progress",
        policy_reason="answered",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )
    await call_attempt_store.finalize_by_control(control, status=status, end_reason="hangup")
    return control


async def test_missed_attempt_appears_alongside_connected_calls():
    from server.call.call_timeline import list_timeline

    tenant = str(uuid.uuid4())
    agent = str(uuid.uuid4())
    await _seed_connected_call(tenant, agent, minutes_ago=10, duration=60)
    await _seed_attempt(tenant, agent, minutes_ago=5, status="missed")

    items, total = await list_timeline(tenant_id=tenant, limit=50)
    assert total == 2
    statuses = {i["status"] for i in items}
    assert statuses == {"answered", "missed"}
    # Newest first.
    assert items[0]["status"] == "missed"


async def test_attempt_carries_the_number_to_call_back():
    from server.call.call_timeline import list_timeline

    tenant = str(uuid.uuid4())
    await _seed_attempt(tenant, str(uuid.uuid4()), minutes_ago=1, status="missed")
    items, _ = await list_timeline(tenant_id=tenant, limit=10)
    missed = next(i for i in items if i["status"] == "missed")
    assert missed["caller_phone"] == "+919999999999"
    assert missed["is_attempt"] is True
    assert missed["connected"] is False


async def test_attempts_can_be_excluded():
    from server.call.call_timeline import list_timeline

    tenant = str(uuid.uuid4())
    agent = str(uuid.uuid4())
    await _seed_connected_call(tenant, agent, minutes_ago=10, duration=60)
    await _seed_attempt(tenant, agent, minutes_ago=5, status="missed")

    items, total = await list_timeline(tenant_id=tenant, limit=50, include_attempts=False)
    assert total == 1
    assert items[0]["status"] == "answered"


async def test_status_filter_selects_missed_only():
    from server.call.call_timeline import list_timeline

    tenant = str(uuid.uuid4())
    agent = str(uuid.uuid4())
    await _seed_connected_call(tenant, agent, minutes_ago=10, duration=60)
    await _seed_connected_call(tenant, agent, minutes_ago=8, duration=0, end_reason="no_answer")
    await _seed_attempt(tenant, agent, minutes_ago=5, status="missed")

    items, total = await list_timeline(tenant_id=tenant, statuses=["missed"], limit=50)
    assert total == 2
    assert all(i["status"] == "missed" for i in items)


async def test_stats_count_every_status():
    from server.call.call_timeline import timeline_stats

    tenant = str(uuid.uuid4())
    agent = str(uuid.uuid4())
    await _seed_connected_call(tenant, agent, minutes_ago=10, duration=60)
    await _seed_connected_call(tenant, agent, minutes_ago=9, duration=120, direction="outbound")
    await _seed_attempt(tenant, agent, minutes_ago=5, status="missed")
    await _seed_attempt(tenant, agent, minutes_ago=4, status="voicemail")

    stats = await timeline_stats(tenant_id=tenant)
    assert stats["total"] == 4
    assert stats["connected"] == 2
    assert stats["missed"] == 1
    assert stats["counts"]["voicemail"] == 1
    assert stats["totalDurationSec"] == 180
    assert stats["avgDurationSec"] == 90


async def test_linked_attempt_is_not_double_counted():
    """When an attempt became a real call, history shows one entry."""
    from server.call.call_timeline import list_timeline

    tenant = str(uuid.uuid4())
    agent = str(uuid.uuid4())
    call_id = await _seed_connected_call(tenant, agent, minutes_ago=10, duration=60)
    control = f"ctl-{uuid.uuid4().hex[:10]}"
    await call_attempt_store.upsert_by_control(
        control,
        tenant_id=tenant,
        agent_id=agent,
        from_number="+919999999999",
        to_number="+918000000000",
        status="in_progress",
    )
    await call_attempt_store.link_to_call(control, call_id)

    items, total = await list_timeline(tenant_id=tenant, limit=50)
    assert total == 1
    assert items[0]["call_id"] == call_id
    assert items[0]["is_attempt"] is False


async def test_tenant_isolation_between_workspaces():
    from server.call.call_timeline import list_timeline

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    await _seed_connected_call(tenant_a, str(uuid.uuid4()), minutes_ago=5, duration=60)
    await _seed_connected_call(tenant_b, str(uuid.uuid4()), minutes_ago=4, duration=60)

    items, total = await list_timeline(tenant_id=tenant_a, limit=50)
    assert total == 1
    assert items[0]["tenant_id"] == tenant_a


async def test_agent_filter_scopes_the_timeline():
    from server.call.call_timeline import list_timeline

    tenant = str(uuid.uuid4())
    agent_a = str(uuid.uuid4())
    agent_b = str(uuid.uuid4())
    await _seed_connected_call(tenant, agent_a, minutes_ago=5, duration=60)
    await _seed_connected_call(tenant, agent_b, minutes_ago=4, duration=60)

    items, total = await list_timeline(tenant_id=tenant, agent_id=agent_a, limit=50)
    assert total == 1
    assert items[0]["agent_id"] == agent_a
