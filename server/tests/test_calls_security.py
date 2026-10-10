"""Tests reproducing and verifying SEC-01: Call endpoints tenant isolation and authentication."""
from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

import server.app as app_mod
from server.auth.calls_tenant import resolve_calls_scope
from server.call.audio_archive import audio_archive
from server.call.call_context import clear_all
from server.call.call_ledger import call_ledger
from server.call.call_store import call_store
from server.config.env import get_settings


@pytest.fixture(autouse=True)
def _reset():
    app_mod.app.dependency_overrides.clear()
    clear_all()
    call_ledger.reset_for_tests()
    audio_archive.reset_for_tests()
    call_store.reset_for_tests()
    get_settings.cache_clear()
    yield
    app_mod.app.dependency_overrides.clear()
    clear_all()
    call_ledger.reset_for_tests()
    audio_archive.reset_for_tests()
    call_store.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_call_endpoints_require_auth_and_tenant_scoping_in_saas_mode(monkeypatch):
    """SEC-01: Call inspection endpoints must reject unauthenticated/cross-tenant requests when SaaS auth is on."""
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-that-is-long-enough-32bytes!")
    get_settings.cache_clear()

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    call_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())

    await call_store.insert(
        {
            "call_id": call_id,
            "session_id": "sess-sec-01",
            "tenant_id": tenant_a,
            "agent_id": agent_id,
            "combination_id": "comb-1",
            "storage_path": f"/tmp/{call_id}",
            "channel": "pstn",
            "direction": "inbound",
        }
    )
    await call_ledger.init(call_id, {"call_id": call_id, "tenant_id": tenant_a})
    await call_ledger.append_user_turn(call_id, "hello sensitive transcript")

    c = TestClient(app_mod.app)

    # 1. Unauthenticated request without token must fail with 401
    r_unauth = c.get(f"/api/call/{call_id}/transcript")
    assert r_unauth.status_code in (401, 403), f"Expected 401/403 unauthenticated, got {r_unauth.status_code}"

    # 2. Authenticated request for Tenant B (cross-tenant IDOR attack) -> must return 404
    async def _resolve_tenant_b():
        return str(tenant_b), False

    app_mod.app.dependency_overrides[resolve_calls_scope] = _resolve_tenant_b
    for endpoint in (
        f"/api/call/{call_id}/transcript",
        f"/api/call/{call_id}/trace",
        f"/api/call/{call_id}/audio-status",
        f"/api/call/{call_id}/audio",
        f"/api/call/{call_id}/memory",
        f"/api/call/{call_id}/outcome",
    ):
        res = c.get(endpoint)
        assert res.status_code == 404, f"Expected 404 cross-tenant for {endpoint}, got {res.status_code}"

    # Mutation endpoints must also return 404 for cross-tenant
    r_mutate = c.post(
        f"/api/call/{call_id}/memory/correction",
        json={"operations": [{"op": "set", "path": "summary", "value": "hacked"}], "reason": "testing"},
    )
    assert r_mutate.status_code == 404, f"Expected 404 for cross-tenant mutation, got {r_mutate.status_code}"

    # 3. Authenticated request for Tenant A (legitimate owner) -> returns 200
    async def _resolve_tenant_a():
        return str(tenant_a), False

    app_mod.app.dependency_overrides[resolve_calls_scope] = _resolve_tenant_a
    r_a = c.get(f"/api/call/{call_id}/transcript")
    assert r_a.status_code == 200, f"Expected 200 for owner, got {r_a.status_code}"
    assert "lines" in r_a.json()
    assert len(r_a.json()["lines"]) > 0
