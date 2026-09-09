"""
Eight-turn integration: agent script adherence, LLM cache, working memory, pricing.
Run: pytest server/tests/test_eight_turn_flow.py -v -s --tb=short
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.config.env import get_settings
from server.services.usage_pricing import cost_tts_usd, estimate_turn_cost, split_llm_tokens
from server.utils.text_billing import billing_char_count
import server.app as app_mod

SESSION = "eight-turn-test"
BRIEF = (
    "Create a Telugu telecaller for GreenHomes Realty. "
    "Agent name Priya. Talk naturally. Qualify budget and location. "
    "Book site visits. Never invent prices."
)

TURNS = [
    "నమస్కారం",
    "నా పేరు రాము",
    "నాకు ఫ్లాట్ కావాలి",
    "బడ్జెట్ ఐదు లక్షలు",
    "హైదరాబాద్ లో ఉంది",
    "సైట్ విజిట్ బుక్ చేయండి",
    "రేపు సాయంత్రం కాల్ చేయండి",
    "ధన్యవాదాలు, బై",
]

MOCK_SCRIPT = {
    "agent_script": (
        "AGENT IDENTITY\n"
        "You are Priya, telecaller for GreenHomes Realty. Speak natural Telugu.\n\n"
        "OPENING\n"
        "Namaste! Nenu Priya, GreenHomes Realty nundi matladutunnanu. "
        "Meeru ela sahayam kavali?\n\n"
        "CONVERSATION FLOW\n"
        "Answer first. Ask at most one missing useful fact if it changes the recommendation. "
        "When enough is known, recommend one fit and offer a site visit. Never a Step tree.\n\n"
        "GUARDRAILS\n"
        "Never invent prices. If budget unknown, ask politely only when needed.\n\n"
        "CLOSING\n"
        "Confirm next step and thank caller."
    ),
    "agent_name": "Priya",
    "company_name": "GreenHomes Realty",
}


def _client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-eight-turn")
    monkeypatch.setenv("SARVAM_API_KEY", "sv-eight-turn")
    monkeypatch.setenv("ENABLE_WORKING_MEMORY", "true")
    monkeypatch.setenv("VOICE_PIPELINE_MODE", "classic")
    get_settings.cache_clear()
    return TestClient(app_mod.app)


@pytest.fixture
def client(monkeypatch):
    return _client(monkeypatch)


def test_telugu_billing_char_count():
    telugu = "నమస్కారం Priya"
    assert billing_char_count(telugu) == len(telugu)
    assert billing_char_count(telugu) == 14


def test_tts_pricing_three_rupees_per_1k_telugu_chars():
    fx = 95.64
    text = "నమస్కారం" * 125  # 8 * 125 = 1000 Telugu code points
    chars = billing_char_count(text)
    assert chars == 1000
    usd = cost_tts_usd(chars=chars, provider="sarvam", fx_rate_inr=fx)
    assert abs(usd * fx - 3.0) < 1e-6


def test_llm_miss_tokens_use_split_not_raw_subtract():
    parts = split_llm_tokens(input_tokens=2000, cached_tokens=500, cache_write_tokens=1800)
    assert parts["uncached"] == 0
    assert parts["written"] == 1500


@pytest.mark.asyncio
async def test_eight_turn_script_cache_and_memory(client, monkeypatch):
    sid = SESSION
    client.delete("/api/instructions", params={"sessionId": sid})

    with patch(
        "server.brain.agent_script_compiler._llm_generate_script",
        new=AsyncMock(return_value=MOCK_SCRIPT),
    ):
        save = client.post(
            "/api/instructions",
            json={"sessionId": sid, "agentBrief": BRIEF, "language_code": "te-IN"},
        )
    assert save.status_code == 200, save.text
    save_j = save.json()
    assert save_j.get("compiledVersion", 0) >= 1
    assert save_j.get("cacheEligible") is True
    assert "Priya" in (save_j.get("agentScript") or "")

    agents = client.get("/api/agents").json()
    agent_id = agents["agents"][0]["agent_id"]

    start = client.post(
        "/api/call/start",
        json={"agentId": agent_id, "sessionId": sid, "channel": "browser"},
    )
    assert start.status_code == 200, start.text
    call_id = start.json()["call_id"]
    locked = start.json().get("locked_versions", {})
    assert locked.get("compiled_brain_version"), "session brain should lock on call start"

    turn_idx = {"n": 0}
    CACHE_PREFIX = 1100

    def _memory_ops(transcript: str) -> list[dict]:
        ops: list[dict] = []
        if "రాము" in transcript:
            ops.append({"op": "set_fact", "key": "caller_name", "value": "Ramu"})
        if "లక్ష" in transcript:
            ops.append({"op": "set_fact", "key": "budget", "value": "5 lakhs"})
        if "హైదరాబాద్" in transcript:
            ops.append({"op": "set_fact", "key": "location", "value": "Hyderabad"})
        if "ఫ్లాట్" in transcript:
            ops.append({"op": "append_context", "value": "Interested in flat"})
        return ops

    async def mock_turn(**kwargs):
        turn_idx["n"] += 1
        n = turn_idx["n"]
        transcript = kwargs.get("transcript", "")
        cached = CACHE_PREFIX if n > 1 else 0
        write = CACHE_PREFIX if n == 1 else 0
        ops = _memory_ops(transcript)
        text = (
            "Namaste! Nenu Priya, GreenHomes Realty nundi matladutunnanu."
            if n == 1
            else "Ardham ayyindi, dhanyavaadalu."
        )
        return {
            "text": text,
            "language_context": {"responseLanguage": "te-IN"},
            "usage": {
                "input_tokens": 1200 + n * 5,
                "output_tokens": 18,
                "cached_tokens": cached,
                "cache_write_tokens": write,
            },
            "memory_update": {"operations": ops},
            "request_id": f"mock-{n}",
        }

    results: list[dict] = []
    with patch(
        "server.call.live_turn_orchestrator.generate_response",
        new=AsyncMock(side_effect=mock_turn),
    ):
        for transcript in TURNS:
            r = client.post(
                "/api/brain",
                json={
                    "sessionId": sid,
                    "callId": call_id,
                    "transcript": transcript,
                    "language_code": "te-IN",
                },
            )
            assert r.status_code == 200, r.text
            results.append(r.json())

    assert int(results[0].get("usage", {}).get("cache_write_tokens") or 0) == CACHE_PREFIX
    for i in range(1, 8):
        cached = int(results[i].get("usage", {}).get("cached_tokens") or 0)
        assert cached == CACHE_PREFIX, f"turn {i+1} expected cache hit"

    early_text = " ".join(r.get("text", "") for r in results[:2])
    assert re.search(r"Priya|GreenHomes", early_text, re.I)

    mem = client.get(f"/api/call/{call_id}/memory")
    assert mem.status_code == 200
    snap = mem.json().get("memory") or {}
    facts = snap.get("facts") or {}
    # Deterministic caller-detail capture preserves the name as actually said,
    # overriding the mock model's Latin transliteration.
    assert facts.get("caller_name") == "రాము"
    assert "budget" in facts
    assert facts.get("location") == "Hyderabad"

    events = client.get(f"/api/call/{call_id}/memory/events").json().get("events") or []
    assert len(events) >= 3

    last_usage = results[-1].get("usage") or {}
    cost = estimate_turn_cost(
        stt_audio_sec=3.5,
        tts_chars=billing_char_count(results[-1].get("text", "")),
        tts_provider="sarvam",
        input_tokens=int(last_usage.get("input_tokens") or 0),
        output_tokens=int(last_usage.get("output_tokens") or 0),
        cached_tokens=int(last_usage.get("cached_tokens") or 0),
        cache_write_tokens=int(last_usage.get("cache_write_tokens") or 0),
        fx_rate_inr=95.64,
    )
    assert cost["total_usd"] > 0
    assert cost["cache_event"] == "cache_hit"

    client.post("/api/call/end", json={"callId": call_id, "reason": "user_stop"})
    client.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()
