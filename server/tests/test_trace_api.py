"""Trace API returns turn ordering for a call."""
from __future__ import annotations

from fastapi.testclient import TestClient

import server.app as app_mod
from server.call.audio_archive import audio_archive
from server.call.call_context import clear_all
from server.call.call_ledger import call_ledger
from server.call.call_store import call_store
from server.config.env import get_settings


def test_trace_turn_ordering(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    clear_all()
    call_ledger.reset_for_tests()
    audio_archive.reset_for_tests()
    call_store.reset_for_tests()
    get_settings.cache_clear()

    c = TestClient(app_mod.app)
    call_id = c.post("/api/call/start", json={"sessionId": "trace"}).json()["call_id"]
    call_ledger.append_trace_turn(call_id, {"turn": 1, "llm_ttft_ms": 80, "errors": []})
    call_ledger.append_trace_turn(call_id, {"turn": 2, "llm_ttft_ms": 70, "errors": []})
    r = c.get(f"/api/call/{call_id}/trace")
    assert r.status_code == 200
    turns = r.json()["turns"]
    assert [t["turn"] for t in turns] == [1, 2]
    get_settings.cache_clear()


def test_calls_list_is_server_authoritative(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    clear_all()
    call_ledger.reset_for_tests()
    audio_archive.reset_for_tests()
    call_store.reset_for_tests()
    get_settings.cache_clear()

    c = TestClient(app_mod.app)
    c.post("/api/call/start", json={"sessionId": "list-1"})
    listed = c.get("/api/calls")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    assert listed.json()["calls"][0]["call_id"]
    get_settings.cache_clear()
