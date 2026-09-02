"""Agent brief → calling script flow tests."""
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from server.config.env import get_settings
import server.app as app_mod


def _client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-agent-brief")
    monkeypatch.setenv("SARVAM_API_KEY", "sv-agent-brief")
    get_settings.cache_clear()
    return TestClient(app_mod.app)


def test_agent_brief_creates_script_and_brain(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-brief-1"
    brief = (
        "Create a Telugu telecaller for Acme Realty. "
        "Agent name Swetha. Talk naturally. Qualify budget and location."
    )
    mock_script = {
        "agent_script": (
            "AGENT IDENTITY\nSwetha from Acme Realty.\n\n"
            "OPENING\nNamaste, nenu Swetha Acme Realty nundi.\n\n"
            "CONVERSATION FLOW\nAsk budget and location one at a time.\n\n"
            "GUARDRAILS\nNever invent prices.\n\n"
            "CLOSING\nBook site visit and thank caller."
        ),
        "agent_name": "Swetha",
        "company_name": "Acme Realty",
        "key_facts": ["Acme Realty", "Swetha"],
    }
    with patch(
        "server.brain.agent_script_compiler._llm_generate_script",
        new=AsyncMock(return_value=mock_script),
    ):
        r = c.post("/api/instructions", json={"sessionId": sid, "agentBrief": brief})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("compiledVersion", 0) >= 1
    assert j.get("agentBrief") == brief
    assert "Swetha" in j.get("agentScript", "")
    assert j["estimatedTokens"] >= 1024
    g = c.get("/api/instructions", params={"sessionId": sid, "includeCompiled": True}).json()
    assert g["present"] is True
    assert g["agentBrief"] == brief
    assert "Swetha" in g.get("agentScript", "")
    assert g["limits"]["agentBriefMax"] == 1200
    assert g["limits"]["agentBriefMaxWords"] == 180
    eff = c.get("/api/prompt/effective", params={"sessionId": sid, "transcript": "test"}).json()
    assert "Swetha" in eff["brainPrompt"]
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_agent_brief_too_long_rejected(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-brief-cap"
    long_brief = "word " * 250
    r = c.post("/api/instructions", json={"sessionId": sid, "agentBrief": long_brief})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "prompt_section_too_long"
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_agent_brief_deterministic_fallback(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-brief-fallback"
    brief = "Telecaller for Sai Tech. Agent name Ravi."
    with patch(
        "server.brain.agent_script_compiler._llm_generate_script",
        new=AsyncMock(return_value=None),
    ):
        r = c.post("/api/instructions", json={"sessionId": sid, "agentBrief": brief})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("compiledVersion", 0) >= 1
    assert "Sai Tech" in j.get("agentScript", "") or "Sai Tech" in j.get("brainPromptFull", "")
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()
