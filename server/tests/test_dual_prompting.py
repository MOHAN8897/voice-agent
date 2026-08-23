"""Dual-channel prompting (behaviour + business) — Phase 5.5 tests."""
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from server.config.env import get_settings
import server.app as app_mod


def _client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dual")
    monkeypatch.setenv("SARVAM_API_KEY", "sv-dual")
    get_settings.cache_clear()
    return TestClient(app_mod.app)


def test_save_and_get_both_channels(monkeypatch):
    c = _client(monkeypatch)
    sid = "dual-1"
    r = c.post("/api/instructions", json={
        "sessionId": sid,
        "behaviourInstructions": "Always answer in Telugu, be friendly.",
        "businessInstructions": "We sell InventoryPro at Rs.999/mo; 7-day refund policy.",
        "responseStyle": "friendly, casual like a friend",
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["behaviourLength"] > 0 and j["businessLength"] > 0
    g = c.get("/api/instructions", params={"sessionId": sid}).json()
    assert g["present"] is True
    assert "Telugu" in g["behaviour"]
    assert "InventoryPro" in g["business"]
    assert g["style"] == "friendly, casual like a friend"
    # limits exposed
    assert g["limits"]["behaviourMax"] == 10000
    assert g["limits"]["businessMax"] == 10000
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_10k_caps_enforced(monkeypatch):
    c = _client(monkeypatch)
    sid = "dual-cap"
    long_b = "b" * 12000
    long_z = "z" * 12000
    r = c.post("/api/instructions", json={
        "sessionId": sid,
        "behaviourInstructions": long_b,
        "businessInstructions": long_z,
    })
    assert r.status_code == 200
    j = r.json()
    assert j["behaviourLength"] == 10000
    assert j["businessLength"] == 10000
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_legacy_instructions_field_maps_to_behaviour(monkeypatch):
    c = _client(monkeypatch)
    sid = "dual-legacy"
    r = c.post("/api/instructions", json={"sessionId": sid, "instructions": "legacy text"})
    assert r.status_code == 200
    g = c.get("/api/instructions", params={"sessionId": sid}).json()
    assert "legacy text" in g["behaviour"]
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_brain_receives_both_channels(monkeypatch):
    c = _client(monkeypatch)
    sid = "dual-brain"
    c.post("/api/instructions", json={
        "sessionId": sid,
        "behaviourInstructions": "BEHAVE-MARKER",
        "businessInstructions": "BUSINESS-MARKER",
    })
    mock_resp = {"text": "ok", "language_context": {"responseLanguage": "te-IN"}, "usage": None, "request_id": "x"}
    with patch("server.routes.brain.generate_response", new=AsyncMock(return_value=mock_resp)) as mock:
        r = c.post("/api/brain", json={"transcript": "హలో", "sessionId": sid})
        assert r.status_code == 200
        kw = mock.call_args.kwargs
        assert kw["user_instructions"] == "BEHAVE-MARKER"
        assert kw["business_instructions"] == "BUSINESS-MARKER"
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_brain_request_accepts_business_field(monkeypatch):
    """Direct request-level business instructions flow through."""
    c = _client(monkeypatch)
    with patch("server.routes.brain.generate_response", new=AsyncMock(return_value={"text": "ok", "language_context": {}, "usage": None, "request_id": "x"})) as mock:
        r = c.post("/api/brain", json={
            "transcript": "ధర ఎంత?",
            "sessionId": "dual-direct",
            "userInstructions": "",
            "businessInstructions": "InventoryPro costs Rs.999/mo.",
        })
        assert r.status_code == 200
        kw = mock.call_args.kwargs
        assert "Rs.999" in kw["business_instructions"]
    get_settings.cache_clear()


def test_effective_prompt_shows_both_wrappers(monkeypatch):
    c = _client(monkeypatch)
    sid = "dual-prompt"
    c.post("/api/instructions", json={
        "sessionId": sid,
        "behaviourInstructions": "Be brief and kind.",
        "businessInstructions": "Domain facts here.",
    })
    r = c.get("/api/prompt/effective", params={"sessionId": sid, "transcript": "test"})
    j = r.json()
    assert "<agent_behaviour_instructions>" in j["developer_instructions_preview"]
    assert "<business_context_instructions>" in j["developer_instructions_preview"]
    assert j["channels"]["behaviour_present"] is True
    assert j["channels"]["business_present"] is True
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()
