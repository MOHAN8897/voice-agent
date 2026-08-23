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


def test_save_and_get_single_brain_prompt(monkeypatch):
    from server.prompts.brain_prompt import get_factory_brain_prompt

    c = _client(monkeypatch)
    sid = "brain-single"
    prompt = get_factory_brain_prompt() + "\n\n--- CUSTOM ---\nAlways mention InventoryPro."
    r = c.post("/api/instructions", json={"sessionId": sid, "brainPrompt": prompt})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["customBrainPrompt"] is True
    assert j["estimatedTokens"] >= 1024
    g = c.get("/api/instructions", params={"sessionId": sid}).json()
    assert g["present"] is True
    assert "InventoryPro" in g["brainPrompt"]
    assert g["limits"]["brainPromptMax"] > 0
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_default_brain_prompt_endpoint(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/api/instructions/default")
    assert r.status_code == 200
    j = r.json()
    assert "brainPrompt" in j
    assert "--- TELUGU VOICE ---" in j["brainPrompt"]
    assert j["estimatedTokens"] >= 1024
    assert j["cacheMinTokens"] == 1024
    assert j["budgetMinTokens"] == 1500
    assert j["budgetMaxTokens"] == 2500
    get_settings.cache_clear()


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
    assert g["limits"]["behaviourMax"] == 8000
    assert g["limits"]["businessMax"] == 8000
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_8k_caps_enforced(monkeypatch):
    c = _client(monkeypatch)
    sid = "dual-cap"
    long_b = "b" * 12_000
    long_z = "z" * 12_000
    r = c.post("/api/instructions", json={
        "sessionId": sid,
        "behaviourInstructions": long_b,
        "businessInstructions": long_z,
        "brainPromptBudgetTokens": 2500,
    })
    # Legacy dual-channel compose at 8k caps exceeds the 2500-token brain budget.
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "prompt_budget_exceeded"
    from server.agent.brain_prompt_composer import sanitize_behaviour, sanitize_business
    assert len(sanitize_behaviour(long_b)) == 8000
    assert len(sanitize_business(long_z)) == 8000
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
        assert kw["user_instructions"] is None
        assert kw["business_instructions"] is None
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


def test_effective_prompt_shows_composed_brain(monkeypatch):
    c = _client(monkeypatch)
    sid = "dual-prompt"
    c.post("/api/instructions", json={
        "sessionId": sid,
        "behaviourInstructions": "Be brief and kind.",
        "businessInstructions": "Domain facts here.",
    })
    r = c.get("/api/prompt/effective", params={"sessionId": sid, "transcript": "test"})
    j = r.json()
    assert "--- BEHAVIOUR ---" in j["brainPrompt"]
    assert "--- BUSINESS ---" in j["brainPrompt"]
    assert "Be brief and kind." in j["brainPrompt"]
    assert j["channels"]["behaviour_present"] is True
    assert j["channels"]["business_present"] is True
    assert j["cacheEligible"] == (j["estimatedTokens"] >= get_settings().prompt_cache_min_tokens)
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()
