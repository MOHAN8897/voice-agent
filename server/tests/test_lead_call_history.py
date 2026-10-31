import threading
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from server.routes import calls


@pytest.mark.parametrize("direction", ["inbound", "outbound"])
def test_connected_call_contact_fields_survive_timeline_enrichment(monkeypatch, direction):
    monkeypatch.setattr(calls, "_enrich_call_list_item", lambda item: {**item, "customer": "Enquiry"})
    monkeypatch.setattr(calls.call_ledger, "read_meta", lambda _cid: {
        "tenant_id": "own-tenant", "direction": direction,
        "caller_id": "+12025550101", "callee_e164": "+12025550102", "internal_secret": "never copy",
    })
    result = calls._enrich_timeline_item({"call_id": "fixture-call", "connected": True,
        "tenant_id": "own-tenant", "direction": direction})
    assert result["caller_phone"] == "+12025550101"
    assert result["called_phone"] == "+12025550102"
    assert "internal_secret" not in result


def test_foreign_ledger_never_supplies_contact_details(monkeypatch):
    monkeypatch.setattr(calls, "_enrich_call_list_item", lambda item: item)
    monkeypatch.setattr(calls.call_ledger, "read_meta", lambda _cid: {
        "tenant_id": "another-tenant", "caller_id": "+12025550101", "callee_e164": "+12025550102",
    })
    result = calls._enrich_timeline_item({"call_id": "fixture-call", "connected": True, "tenant_id": "own-tenant"})
    assert not result.get("caller_phone") and not result.get("called_phone")


async def test_list_enrichment_runs_off_event_loop_and_preserves_tenant_scope(monkeypatch):
    timeline = AsyncMock(return_value=([{"call_id": "fixture-call", "connected": True, "tenant_id": "own-tenant"}], 1))
    monkeypatch.setattr(calls, "list_timeline", timeline)
    monkeypatch.setattr(calls, "_attach_tenant_wallet_charges", AsyncMock())
    loop_thread = threading.get_ident()
    observed = []

    def enrich(item):
        observed.append(threading.get_ident())
        return {**item, "called_phone": "+12025550101"}

    monkeypatch.setattr(calls, "_enrich_timeline_item", enrich)
    app = FastAPI()
    app.include_router(calls.router)
    app.dependency_overrides[calls.resolve_calls_tenant_id] = lambda: "own-tenant"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/calls", params={"agentId": "own-agent"})
    assert response.status_code == 200
    assert response.json()["calls"][0]["called_phone"] == "+12025550101"
    assert observed and observed[0] != loop_thread
    assert timeline.await_args.kwargs["tenant_id"] == "own-tenant"
    assert timeline.await_args.kwargs["agent_id"] == "own-agent"
