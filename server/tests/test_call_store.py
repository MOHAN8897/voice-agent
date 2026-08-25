"""Call store index, pagination, tenant scope."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from server.call.call_store import call_store
from server.config.env import get_settings


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    get_settings.cache_clear()
    call_store.reset_for_tests()
    yield call_store
    call_store.reset_for_tests()
    get_settings.cache_clear()


def _rec(call_id: str, tenant: str, agent: str, started: str) -> dict:
    return {
        "call_id": call_id,
        "tenant_id": tenant,
        "agent_id": agent,
        "session_id": "s",
        "channel": "browser",
        "direction": "inbound",
        "environment": "development",
        "tier": "medium",
        "combination_id": "combo",
        "storage_path": f"data/calls/{call_id}/",
        "started_at": datetime.fromisoformat(started).replace(tzinfo=timezone.utc),
        "finalization_status": "pending",
    }


@pytest.mark.asyncio
async def test_pagination_and_tenant_scope(store):
    t1 = "11111111-1111-1111-1111-111111111111"
    t2 = "22222222-2222-2222-2222-222222222222"
    a1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    await store.insert(_rec("c1", t1, a1, "2026-08-25T10:00:00"))
    await store.insert(_rec("c2", t1, a1, "2026-08-25T11:00:00"))
    await store.insert(_rec("c3", t2, a1, "2026-08-25T12:00:00"))

    page, total = await store.list_calls(tenant_id=t1, limit=1, offset=0)
    assert total == 2
    assert len(page) == 1
    assert page[0]["call_id"] == "c2"

    page2, total2 = await store.list_calls(tenant_id=t1, limit=1, offset=1)
    assert total2 == 2
    assert page2[0]["call_id"] == "c1"

    other, other_total = await store.list_calls(tenant_id=t2)
    assert other_total == 1
    assert other[0]["call_id"] == "c3"

    dated, dated_total = await store.list_calls(
        tenant_id=t1, since="2026-08-25T10:30:00+00:00", until="2026-08-25T11:30:00+00:00"
    )
    assert dated_total == 1
    assert dated[0]["call_id"] == "c2"
