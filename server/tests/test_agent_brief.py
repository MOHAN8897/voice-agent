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
        "Agent name Swetha. Talk naturally. Answer first; don't interrogate."
    )
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
    assert "BUSINESS KNOWLEDGE" in script_text or "COMPANY & OFFER" in script_text
    assert "LIVE CALL GUIDE" not in script_text
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
    assert "--- SPOKEN LANGUAGE (te-IN) ---" in compiled
    assert "60–80" not in script


def test_agent_brief_too_long_rejected(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-brief-cap"
    long_brief = "word " * 250
    r = c.post("/api/instructions", json={"sessionId": sid, "agentBrief": long_brief})
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "prompt_section_too_long"
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_english_brief_compiles_english_script_and_pack(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-brief-en"
    brief = "Telecaller for Acme Realty. Agent name Priya. Book site visits."
    with patch(
        "server.brain.agent_script_compiler._llm_generate_script",
        new=AsyncMock(return_value=None),
    ):
        r = c.post(
            "/api/instructions",
            json={"sessionId": sid, "agentBrief": brief, "language_code": "en-IN"},
        )
    assert r.status_code == 200, r.text
    j = r.json()
    script = j.get("agentScript", "")
    brain = j.get("brainPromptFull", "")
    assert "Priya" in script
    assert "representing Acme Realty" in script
    assert "matladutunnanu" not in script
    assert "60–80" not in script
    assert "--- SPOKEN LANGUAGE (en-IN) ---" in brain
    assert "--- SPOKEN LANGUAGE (te-IN) ---" not in brain
    assert "Indian English" in brain
    assert "--- CALL END POLICY ---" in brain
    assert "Thank you for your time. Goodbye." in brain
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_agent_brief_truncated_llm_json_returns_200(monkeypatch):
    """Luna JSON truncation must not 500 Test Studio — fall back to a deterministic script."""
    c = _client(monkeypatch)
    sid = "agent-brief-trunc-json"
    brief = "Telecaller for Sai Tech. Agent name Ravi. Qualify budget and close a site visit."
    with patch(
        "server.providers.openai_llm.OpenAILLMAdapter.structured_completion",
        new=AsyncMock(
            side_effect=ValueError(
                "structured_completion JSON parse failed: Unterminated string starting at: line 1 column 17 (char 16)"
            )
        ),
    ):
        r = c.post("/api/instructions", json={"sessionId": sid, "agentBrief": brief})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("compiledVersion", 0) >= 1
    script = j.get("agentScript", "")
    assert "Ravi" in script
    assert "Sai Tech" in script or "Sai Tech" in (j.get("brainPromptFull") or "")
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_agent_brief_truncated_json_payload_uses_deterministic(monkeypatch):
    """Salvaged empty agent_script must not be treated as a successful LLM script."""
    c = _client(monkeypatch)
    sid = "agent-brief-empty-salvage"
    brief = "Telecaller for Sai Tech. Agent name Ravi."
    with patch(
        "server.providers.openai_llm.OpenAILLMAdapter.structured_completion",
        new=AsyncMock(return_value={"agent_script": "", "agent_name": "Ravi", "company_name": "Sai Tech"}),
    ):
        r = c.post("/api/instructions", json={"sessionId": sid, "agentBrief": brief})
    assert r.status_code == 200, r.text
    script = r.json().get("agentScript", "")
    assert "BUSINESS KNOWLEDGE" in script or "COMPANY & OFFER" in script
    assert "Ravi" in script
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
    assert "BUSINESS KNOWLEDGE" in script or "COMPANY & OFFER" in script
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
    assert "BUSINESS KNOWLEDGE" in script or "COMPANY & OFFER" in script
    assert "Priya" in script
    assert "OPENING HINT" in script or "CANONICAL OPENING" in script
    assert "nundi matladutunnanu" not in script
    assert "[agent name]" not in script.lower()
    assert "[company" not in script.lower()
    assert "book a car" in script.lower() or "car" in script.lower()
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_call_end_policy_is_written_into_brain(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-brief-call-end"
    brief = "Telecaller for Acme Realty. Agent name Priya. Book site visits."
    with patch(
        "server.brain.agent_script_compiler._llm_generate_script",
        new=AsyncMock(return_value=None),
    ):
        r = c.post(
            "/api/instructions",
            json={
                "sessionId": sid,
                "agentBrief": brief,
                "language_code": "en-IN",
                "callEndPolicy": {
                    "allowedReasons": ["goodbye", "firm_refusal"],
                    "farewell": "Thanks for your time. Take care.",
                },
            },
        )
    assert r.status_code == 200, r.text
    brain = r.json().get("brainPromptFull", "")
    assert "Thanks for your time. Take care." in brain
    assert "goodbye, firm_refusal" in brain
    g = c.get("/api/instructions", params={"sessionId": sid}).json()
    assert "brainPrompt" not in g
    assert g["callEndPolicy"]["farewell"] == "Thanks for your time. Take care."
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_missing_hangup_uses_default_farewell(monkeypatch):
    """No Call-end card / no custom farewell → default hangup is stored and compiled."""
    c = _client(monkeypatch)
    sid = "agent-brief-default-hangup"
    c.delete("/api/instructions", params={"sessionId": sid})
    empty = c.get("/api/instructions", params={"sessionId": sid}).json()
    assert empty["callEndPolicy"]["farewell"] == "Sare, time ichinanduku thanks. Good day."
    assert empty["callEndPolicy"]["allowedReasons"]
    brief = "Telecaller for Acme Realty. Agent name Priya. Book site visits."
    with patch(
        "server.brain.agent_script_compiler._llm_generate_script",
        new=AsyncMock(return_value=None),
    ):
        r = c.post(
            "/api/instructions",
            json={"sessionId": sid, "agentBrief": brief, "language_code": "en-IN"},
        )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["callEndPolicy"]["farewell"] == "Thank you for your time. Goodbye."
    assert "--- CALL END POLICY ---" in j["brainPromptFull"]
    assert "Thank you for your time. Goodbye." in j["brainPromptFull"]
    g = c.get("/api/instructions", params={"sessionId": sid}).json()
    assert g["callEndPolicy"]["farewell"] == "Thank you for your time. Goodbye."
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()
