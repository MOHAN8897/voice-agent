"""Call lifecycle start/end tests — Phase 3."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

import server.app as app_mod
from server.call.audio_archive import audio_archive
from server.call.call_context import clear_all
from server.call.call_ledger import call_ledger
from server.call.call_store import call_store
from server.call.memory_manager import memory_manager
from server.config.env import get_settings


def _reset():
    clear_all()
    call_ledger.reset_for_tests()
    audio_archive.reset_for_tests()
    call_store.reset_for_tests()
    memory_manager.reset_for_tests()
    get_settings.cache_clear()


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CALL_AUTO_END_ON_START", "true")
    _reset()
    return TestClient(app_mod.app)


def test_call_start_and_end_idempotent_202(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    started = c.post("/api/call/start", json={"sessionId": "sess-a", "channel": "browser"})
    assert started.status_code == 200
    call_id = started.json()["call_id"]
    assert started.json()["locked_versions"]["combination_id"]
    assert "ws_urls" in started.json()
    assert started.json().get("pipeline") == "realtime_text"

    ended = c.post("/api/call/end", json={"callId": call_id, "reason": "user_stop"})
    assert ended.status_code == 202
    url = ended.json()["status_url"]
    assert url == f"/api/call/{call_id}/finalization"

    again = c.post("/api/call/end", json={"callId": call_id, "reason": "user_stop"})
    assert again.status_code == 202
    assert again.json()["status_url"] == url
    get_settings.cache_clear()


def test_call_end_missing_returns_404(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    r = c.post("/api/call/end", json={"callId": "00000000-0000-0000-0000-000000000001"})
    assert r.status_code == 404
    get_settings.cache_clear()


def test_auto_end_previous_on_start(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    first = c.post("/api/call/start", json={"sessionId": "same"}).json()["call_id"]
    second = c.post("/api/call/start", json={"sessionId": "same"}).json()["call_id"]
    assert first != second
    fin = c.get(f"/api/call/{first}/finalization")
    assert fin.status_code == 200
    assert fin.json()["status"] in ("processing", "complete", "finalizing")
    get_settings.cache_clear()


def test_finalization_endpoint_shape(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    call_id = c.post("/api/call/start", json={"sessionId": "fin"}).json()["call_id"]
    c.post("/api/call/end", json={"callId": call_id})
    fin = c.get(f"/api/call/{call_id}/finalization").json()
    assert fin["call_id"] == call_id
    assert "components" in fin
    assert "ledger" in fin["components"]
    tx = c.get(f"/api/call/{call_id}/transcript")
    assert tx.status_code == 200
    assert tx.json()["lines"] == []
    mem = c.get(f"/api/call/{call_id}/memory")
    assert mem.status_code == 200
    assert mem.json()["memory"]["facts"] == {}
    events = c.get(f"/api/call/{call_id}/memory-events")
    assert events.status_code == 200
    alias = c.get(f"/api/call/{call_id}/memory/events")
    assert alias.status_code == 200
    assert alias.json() == events.json()
    from server.call.paths import call_dir

    d = call_dir(call_id)
    assert (d / "memory_events.jsonl").exists()
    assert (d / "memory_snapshot.json").exists()
    get_settings.cache_clear()


def test_conflict_when_auto_end_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CALL_AUTO_END_ON_START", "false")
    _reset()
    c = TestClient(app_mod.app)
    first = c.post("/api/call/start", json={"sessionId": "one"})
    assert first.status_code == 200
    second = c.post("/api/call/start", json={"sessionId": "one"})
    assert second.status_code == 409
    get_settings.cache_clear()


def test_stack_override_applied_in_frontend_mode(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    baseline = c.post("/api/call/start", json={"sessionId": "ov-a"}).json()
    overridden = c.post(
        "/api/call/start",
        json={"sessionId": "ov-b", "stackOverride": {"stt": {"model": "saaras:v3"}}},
    )
    assert overridden.status_code == 200
    body = overridden.json()
    assert body["resolved_stack"]["stt"]["model"] == "saaras:v3"
    assert body["locked_versions"]["combination_id"] != baseline["locked_versions"]["combination_id"]
    get_settings.cache_clear()


def test_session_clear_ends_active_call(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    call_id = c.post("/api/call/start", json={"sessionId": "clr"}).json()["call_id"]
    cleared = c.post("/api/session/clear", json={"sessionId": "clr"})
    assert cleared.status_code == 200
    rec = c.get(f"/api/call/{call_id}")
    assert rec.status_code == 200
    assert rec.json().get("ended_at") or rec.json().get("status") in (
        "processing",
        "complete",
        "finalizing",
        "failed",
    )
    get_settings.cache_clear()


def test_memory_and_outcome_endpoints(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    call_id = c.post("/api/call/start", json={"sessionId": "mem-api"}).json()["call_id"]
    mem = c.get(f"/api/call/{call_id}/memory").json()
    assert mem["memory"]["facts"] == {}
    proj = c.get(f"/api/call/{call_id}/memory/projection").json()
    assert "projection" in proj
    pending = c.get(f"/api/call/{call_id}/outcome")
    assert pending.status_code in (200, 202)
    metrics = c.get(f"/api/metrics/calls/{call_id}")
    assert metrics.status_code == 200
    assert metrics.json()["call_id"] == call_id
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_recover_finalizes_all_open_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _reset()
    from datetime import datetime, timezone

    from server.call.call_lifecycle_service import call_lifecycle_service

    call_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    await call_store.insert(
        {
            "call_id": call_id,
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "agent_id": "22222222-2222-2222-2222-222222222222",
            "session_id": "dead",
            "channel": "browser",
            "direction": "inbound",
            "environment": "development",
            "tier": "medium",
            "combination_id": "deadcombo",
            "storage_path": f"data/calls/{call_id}/",
            "started_at": datetime.now(timezone.utc),
            "finalization_status": "pending",
        }
    )
    n = await call_lifecycle_service.recover_stale_calls()
    assert n == 1
    rec = await call_store.get(call_id)
    assert rec is not None
    assert rec.get("ended_at")
    assert rec.get("end_reason") == "stale_recovery"
    get_settings.cache_clear()


def test_outcome_retry_enqueues_and_returns_202(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    call_id = c.post("/api/call/start", json={"sessionId": "retry-out"}).json()["call_id"]
    c.post("/api/call/end", json={"callId": call_id})
    with patch("server.call.post_call_pipeline.enqueue", new_callable=AsyncMock) as enq:
        r = c.post(f"/api/call/{call_id}/outcome/retry")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "processing"
    assert body["status_url"] == f"/api/call/{call_id}/finalization"
    assert "outcome" not in body
    enq.assert_awaited()
    get_settings.cache_clear()


def test_call_start_clears_session_conversation_history(monkeypatch, tmp_path):
    from server.agent.conversation_manager import conversation_manager
    from server.agent.session_memory import session_memory

    c = _client(monkeypatch, tmp_path)
    conversation_manager.add_turn("leak-sess", "Don't call me again.", "Okay, goodbye.")
    session_memory.set_summary("leak-sess", "Caller asked not to be called.")
    assert conversation_manager.get_history("leak-sess")
    c.post("/api/call/start", json={"sessionId": "leak-sess", "channel": "browser"})
    assert conversation_manager.get_history("leak-sess") == []
    assert session_memory.get_summary("leak-sess") == ""
    get_settings.cache_clear()

