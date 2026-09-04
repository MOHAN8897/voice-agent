"""Agent brief → calling script flow tests."""
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from server.agent.brain_prompt_composer import BUDGET_MAX_TOKENS, CACHE_MIN_TOKENS, estimate_tokens
from server.brain.agent_script_compiler import _ensure_cache_floor
from server.config.env import get_settings
from server.prompts.agent_voice_rules import AGENT_VOICE_RULE_MARKERS
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
            "VOICE STYLE\n"
            "Speak natural Tanglish — Telugu with everyday English (budget, delivery, order). "
            "Never literary or pandit-style Telugu. "
            "Be persuasive until a firm refusal. Keep every live reply to 60–80 characters unless the caller asks for more detail. "
            "Avoid filler words. Ask only one useful question at a time. "
            "Always move the conversation forward.\n\n"
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
    script_text = g.get("agentScript", "")
    hits = sum(1 for m in AGENT_VOICE_RULE_MARKERS if m.lower() in script_text.lower())
    assert hits >= 2 or "VOICE STYLE" in script_text or "one question" in script_text.lower()
    assert g["limits"]["agentBriefMax"] == 1200
    assert g["limits"]["agentBriefMaxWords"] == 180
    eff = c.get("/api/prompt/effective", params={"sessionId": sid, "transcript": "test"}).json()
    assert "Swetha" in eff["brainPrompt"]
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_agent_script_not_truncated_for_cache_or_budget():
    """Long scripts must keep GUARDRAILS/CLOSING — only pad below cache min, never trim."""
    long_body = (
        "AGENT IDENTITY\nPriya from SKM Plants.\n\n"
        "OPENING\nNamaste, nenu Priya SKM Plants nundi.\n\n"
        "VOICE STYLE\nNatural Tanglish only.\n\n"
        "CONVERSATION FLOW\n" + ("Qualify nursery needs and plant types. " * 80) + "\n\n"
        "OBJECTION HANDLING\n" + ("Price concern — explain value and delivery. " * 40) + "\n\n"
        "GUARDRAILS\nNever invent stock or prices.\n\n"
        "CLOSING\nConfirm order and thank the caller."
    )
    assert "GUARDRAILS" in long_body
    assert long_body.rstrip().endswith("CLOSING\nConfirm order and thank the caller.")

    script, compiled = _ensure_cache_floor(script=long_body, language="te-IN", style=None)
    assert "GUARDRAILS" in script
    assert "CLOSING" in script
    assert script.rstrip().endswith("CLOSING\nConfirm order and thank the caller.")
    assert len(script) >= len(long_body)
    assert estimate_tokens(compiled) >= CACHE_MIN_TOKENS
    assert estimate_tokens(compiled) <= BUDGET_MAX_TOKENS


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
    script = j.get("agentScript", "")
    assert "Ravi" in script
    assert "[agent name]" not in script.lower()
    assert "WORK SCOPE" in script
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_agent_brief_unnamed_no_company_uses_work_scope(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-brief-work-scope"
    brief = "Help callers book a car. Qualify pickup city, drop location, and time. Never invent fares."
    with patch(
        "server.brain.agent_script_compiler._llm_generate_script",
        new=AsyncMock(return_value=None),
    ):
        r = c.post("/api/instructions", json={"sessionId": sid, "agentBrief": brief})
    assert r.status_code == 200, r.text
    script = r.json().get("agentScript", "")
    assert "WORK SCOPE" in script
    assert "Ravi" in script
    assert "Namaste!" in script
    assert "nundi matladutunnanu" not in script
    assert "[agent name]" not in script.lower()
    assert "[company" not in script.lower()
    assert "book a car" in script.lower() or "car" in script.lower()
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()
