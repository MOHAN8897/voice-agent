"""Tests for Post-Call Analytics and CRM Contact Sync Export endpoints."""
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
from server.call.paths import call_dir
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
async def test_call_analytics_and_crm_export(monkeypatch):
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-that-is-long-enough-32bytes!")
    get_settings.cache_clear()

    tenant_id = str(uuid.uuid4())
    cross_tenant_id = str(uuid.uuid4())
    call_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())

    await call_store.insert(
        {
            "call_id": call_id,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "channel": "pstn",
            "direction": "inbound",
            "caller_id": "+919876543210",
            "duration_sec": 75,
            "started_at": "2026-10-15T00:00:00Z",
        }
    )
    await call_ledger.init(call_id, {"call_id": call_id, "tenant_id": tenant_id, "caller_id": "+919876543210"})
    await call_ledger.append_user_turn(call_id, "Hi, I am interested in booking a site visit for 3BHK.")
    await call_ledger.append_assistant_turn(call_id, "Certainly, we have prime slots available tomorrow.")

    # Write outcome
    import json
    cdir = call_dir(call_id)
    cdir.mkdir(parents=True, exist_ok=True)
    outcome_file = cdir / "outcome.json"
    outcome_file.write_text(
        json.dumps(
            {
                "disposition": "site_visit_planned",
                "disposition_confidence": 0.95,
                "summary_en": "Caller inquired about 3BHK and scheduled a site visit for tomorrow.",
                "summary_te": "",
                "next_action": "Confirm appointment via SMS",
                "facts": {
                    "name": "Rajesh Kumar",
                    "phone": "+919876543210",
                    "email": "rajesh@example.com",
                    "company": "Tech Corp",
                },
                "objections": [],
                "status_tags": ["outcome:site_visit_planned", "contact:name_known"],
            }
        ),
        encoding="utf-8",
    )

    client = TestClient(app_mod.app)

    # 1. Unauthenticated request -> 401
    r_unauth = client.get(f"/api/call/{call_id}/analytics")
    assert r_unauth.status_code in (401, 403)

    # 2. Cross-tenant request -> 404
    async def _resolve_cross():
        return cross_tenant_id, False

    app_mod.app.dependency_overrides[resolve_calls_scope] = _resolve_cross
    r_cross = client.get(f"/api/call/{call_id}/analytics")
    assert r_cross.status_code == 404

    # 3. Owner tenant request -> 200
    async def _resolve_owner():
        return tenant_id, False

    app_mod.app.dependency_overrides[resolve_calls_scope] = _resolve_owner

    # Test Analytics endpoint
    r_analytics = client.get(f"/api/call/{call_id}/analytics")
    assert r_analytics.status_code == 200
    data = r_analytics.json()["analytics"]
    assert data["sentiment"] == "positive"
    assert data["resolution_status"] == "resolved"
    assert data["contact"]["first_name"] == "Rajesh"
    assert data["contact"]["last_name"] == "Kumar"
    assert data["contact"]["phone"] == "+919876543210"
    assert data["talk_time"]["user_turns"] == 1
    assert data["talk_time"]["agent_turns"] == 1

    # Test CRM Sync endpoint
    r_sync = client.post(f"/api/call/{call_id}/crm-sync", json={})
    assert r_sync.status_code == 200
    sync_data = r_sync.json()
    assert sync_data["ok"] is True
    assert "contact" in sync_data
    assert sync_data["contact"]["name"] == "Rajesh Kumar"

    # Test CRM Export formats
    # vCard (.vcf)
    r_vcf = client.get(f"/api/call/{call_id}/crm-export?format=vcf")
    assert r_vcf.status_code == 200
    assert "text/vcard" in r_vcf.headers.get("content-type", "")
    assert "FN:Rajesh Kumar" in r_vcf.text
    assert "TEL;TYPE=CELL,VOICE:+919876543210" in r_vcf.text

    # CSV
    r_csv = client.get(f"/api/call/{call_id}/crm-export?format=csv")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers.get("content-type", "")
    assert "Call ID,Full Name" in r_csv.text
    assert "Rajesh Kumar" in r_csv.text

    # JSON
    r_json = client.get(f"/api/call/{call_id}/crm-export?format=json")
    assert r_json.status_code == 200
    assert r_json.json()["ok"] is True
    assert r_json.json()["contact"]["email"] == "rajesh@example.com"
