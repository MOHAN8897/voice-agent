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
    await call_ledger.init(call_id, {"call_id": call_id, "tenant_id": tenant_a,
        "live_transcription": {"mode": "live", "status": "streaming", "model": "saaras:v3-realtime",
                               "provider": "sarvam", "error_code": "private", "partial_text": "hello", "segments": 1}})
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
    assert r_a.json()["transcription"]["status"] == "streaming"
    assert r_a.json()["transcription"]["partial_text"] == "hello"
    assert not {"model", "provider", "error_code"}.intersection(r_a.json()["transcription"])


def test_call_id_path_traversal_blocked():
    """Verify malicious call_id with directory traversal characters is strictly rejected with 400."""
    from server.call.paths import validate_call_id_format, call_dir

    # 1. Direct path validator tests
    for evil_id in ("../../etc/passwd", "../system32", "call/../../secret", "foo\\..\\bar", "foo\x00bar", ""):
        with pytest.raises(ValueError):
            validate_call_id_format(evil_id)

    # 2. Endpoint validation tests
    async def _mock_admin():
        return "test-tenant", True

    app_mod.app.dependency_overrides[resolve_calls_scope] = _mock_admin
    try:
        c = TestClient(app_mod.app)
        for evil_path in (
            "/api/call/bad..id/audio",
            "/api/call/evil..path/transcript",
            "/api/call/test..123/finalization",
            "/api/call/bad$id/finalization",
        ):
            r = c.get(evil_path)
            assert r.status_code == 400, f"Expected 400 for path traversal {evil_path}, got {r.status_code}"
            data = r.json()
            err = data.get("error") or data.get("detail", {}).get("error")
            assert err["code"] == "validation_error"
    finally:
        app_mod.app.dependency_overrides.pop(resolve_calls_scope, None)


@pytest.mark.asyncio
async def test_tenant_call_rows_use_scoped_wallet_charge_and_hide_supplier_costs(monkeypatch):
    from types import SimpleNamespace

    from server.routes import calls as calls_route

    tenant_id = uuid.uuid4()
    call_id = str(uuid.uuid4())
    transaction = SimpleNamespace(
        reference_id=f"call:{call_id}", amount_cents=-14, amount_inr_paise=0
    )
    statements = []

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [transaction]

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _model, _key):
            return SimpleNamespace(currency="usd")

        async def execute(self, statement):
            statements.append(statement)
            return _Result()

    monkeypatch.setattr(calls_route, "get_session_factory", lambda: lambda: _Session())
    items = [{"call_id": call_id, "connected": True}]
    await calls_route._attach_tenant_wallet_charges(items, str(tenant_id))

    params = statements[0].compile().params
    assert tenant_id in params.values()
    assert [f"call:{call_id}"] in params.values()
    assert items[0]["tenant_charge"] == {"amount": 0.14, "currency": "USD"}

    monkeypatch.setattr(calls_route, "_enrich_call_list_item", lambda _item: {
        "summary": "Call summary",
        "usage": {"cost_usd": 4.2},
        "cost_usd": 4.2,
        "telephony_provider": "vobiz",
        "vobiz_usd": 1.0,
        "recording_source": "telnyx",
    })
    row = calls_route._enrich_timeline_item({
        "call_id": call_id, "connected": True, "usage": {"model_cost_usd": 2.0},
        "cost_usd": 4.2, "telephony_provider": "vobiz", "recording_source": "telnyx",
    })
    assert row["summary"] == "Call summary"
    assert not {"usage", "cost_usd", "telephony_provider", "vobiz_usd", "recording_source"}.intersection(row)


def test_partial_live_transcription_is_returned_as_saved_text_state():
    from server.services.saas.call_redaction import tenant_live_transcription

    result = tenant_live_transcription({
        "live_transcription": {"mode": "live", "status": "partial", "segments": 6}
    })
    assert result == {"mode": "live", "status": "partial", "segments": 6}

