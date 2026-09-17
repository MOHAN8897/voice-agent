"""Edited calling-script save, limits, and Fine-tune persist."""
import pytest

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from server.agent.brain_prompt_composer import MAX_AGENT_SCRIPT_CHARS, MAX_AGENT_SCRIPT_WORDS
from server.agent.instruction_store import instruction_store
from server.config.env import get_settings
from server.services.runtime_settings import runtime_settings
import server.app as app_mod


def _client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-agent-script-edit")
    monkeypatch.setenv("SARVAM_API_KEY", "sv-agent-script-edit")
    get_settings.cache_clear()
    return TestClient(app_mod.app)


def test_instructions_limits_include_script_caps(monkeypatch):
    c = _client(monkeypatch)
    g = c.get("/api/instructions", params={"sessionId": "limits-script-caps"}).json()
    assert g["limits"]["agentScriptMax"] == MAX_AGENT_SCRIPT_CHARS
    assert g["limits"]["agentScriptMaxWords"] == MAX_AGENT_SCRIPT_WORDS
    assert g["limits"]["recommendedAgentScriptWords"] == 500
    get_settings.cache_clear()


def test_agent_script_edit_saves_without_recompile(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-script-edit-1"
    brief = (
        "Create a Telugu telecaller for Acme Realty. "
        "Agent name Swetha. Talk naturally. Answer first; don't interrogate."
    )
    created = c.post("/api/instructions", json={"sessionId": sid, "agentBrief": brief})
    assert created.status_code == 200, created.text
    script = created.json()["agentScript"]
    assert "Swetha" in script
    edited = script + "\n\nNever mention competitor nurseries."
    persist = AsyncMock(return_value=True)
    monkeypatch.setattr(instruction_store, "persist_to_db", persist)
    r = c.post(
        "/api/instructions",
        json={"sessionId": sid, "agentScript": edited, "agentBrief": brief, "language_code": "te-IN"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert "Never mention competitor nurseries" in j.get("agentScript", "")
    compiled = j.get("compiledBrainPrompt") or j.get("brainPromptFull") or ""
    assert "--- CALLING SCRIPT ---" in compiled
    assert "Never mention competitor nurseries" in compiled
    assert j.get("cacheEligible") is True
    assert j.get("compiledVersion", 0) >= 2
    assert j.get("persistedToDb") is True
    persist.assert_awaited()
    g = c.get("/api/instructions", params={"sessionId": sid, "includeCompiled": True}).json()
    assert "Never mention competitor nurseries" in g.get("agentScript", "")
    assert "Never mention competitor nurseries" in (g.get("brainPrompt") or "")
    assert g.get("cacheEligible") is True
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_edited_script_locks_into_live_brain_and_busts_cache_key(monkeypatch):
    from server.call.call_lifecycle_service import CallLifecycleService
    from server.services.prompt_cache_key import compute_cache_key

    c = _client(monkeypatch)
    sid = "agent-script-cache-1"
    brief = (
        "Create a Telugu telecaller for Acme Realty. "
        "Agent name Swetha. Talk naturally. Answer first; don't interrogate."
    )
    created = c.post("/api/instructions", json={"sessionId": sid, "agentBrief": brief})
    assert created.status_code == 200, created.text
    before = created.json().get("compiledBrainPrompt") or created.json().get("brainPromptFull") or ""
    script = created.json()["agentScript"]
    marker = "UNIQUE_OFFER_CODE_HYD_77"
    edited = script.replace("Swetha", "Kailash") + f"\n\nKnown code: {marker}."
    r = c.post(
        "/api/instructions",
        json={"sessionId": sid, "agentScript": edited, "agentBrief": brief, "language_code": "te-IN"},
    )
    assert r.status_code == 200, r.text
    after = r.json().get("compiledBrainPrompt") or r.json().get("brainPromptFull") or ""
    assert marker in after
    assert "Kailash" in after
    assert "Never claim to be anyone except Kailash" in after
    assert compute_cache_key(before, 6000) != compute_cache_key(after, 6000)
    svc = CallLifecycleService()
    version, text = await svc._lock_compiled_brain("any-agent", session_id=sid)
    assert str(version).startswith("session-v")
    assert marker in (text or "")
    assert "Kailash" in (text or "")
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_agent_script_too_many_words_rejected(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-script-words"
    long_script = "word " * (MAX_AGENT_SCRIPT_WORDS + 20)
    r = c.post("/api/instructions", json={"sessionId": sid, "agentScript": long_script})
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["error"]["code"] == "prompt_section_too_long"
    assert r.json()["detail"]["error"]["section"] == "Agent script"
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_agent_script_too_many_chars_rejected(monkeypatch):
    c = _client(monkeypatch)
    sid = "agent-script-chars"
    long_script = "a" * (MAX_AGENT_SCRIPT_CHARS + 1)
    r = c.post("/api/instructions", json={"sessionId": sid, "agentScript": long_script})
    assert r.status_code in (400, 422)
    c.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()


def test_runtime_save_awaits_db_persist(monkeypatch):
    c = _client(monkeypatch)
    sid = "runtime-persist-1"
    persist = AsyncMock(return_value=True)
    monkeypatch.setattr(runtime_settings, "persist_to_db", persist)
    r = c.post(
        "/api/settings/runtime",
        json={"sessionId": sid, "openaiTemperature": 0.4, "brainPromptBudgetTokens": 2500},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("persistedToDb") is True
    persist.assert_awaited()
    c.delete("/api/settings/runtime", params={"sessionId": sid})
    get_settings.cache_clear()
