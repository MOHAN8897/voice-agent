"""
Seven-turn agent-brief flow: script generation with voice rules + conversation transcript.

Run: python -m pytest server/tests/test_seven_turn_agent_brief.py -v -s --tb=short
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.config.env import get_settings
from server.prompts.agent_voice_rules import AGENT_VOICE_RULE_MARKERS
import server.app as app_mod

SESSION = "seven-turn-brief-demo"
BRIEF = (
    "Create a Telugu telecaller for PenMart stationery shop. "
    "Agent name Kavya. Sell premium pens and gift sets. "
    "Qualify quantity, budget, and delivery (pickup or delivery). "
    "Offer order confirmation. Never invent prices."
)

TURNS = [
    ("నమస్కారం", "user greets"),
    ("నాకు pens కావాలి corporate gifting కి", "user wants pens for gifting"),
    ("50 pieces budget 5000 rupees", "user shares quantity and budget"),
    ("delivery cheyandi Hyderabad lo", "user wants delivery in Hyderabad"),
    ("blue color pens kavali", "user specifies color"),
    ("order confirm cheyandi", "user confirms order"),
    ("ధన్యవాదాలు", "user thanks and ends"),
]

MOCK_SCRIPT = {
    "agent_script": (
        "AGENT IDENTITY\n"
        "You are Kavya, telecaller for PenMart stationery. Speak natural Telugu with conversational English.\n\n"
        "OPENING\n"
        "Namaste! Nenu Kavya, PenMart nundi matladutunnanu. Corporate gifting ki pens kavala?\n\n"
        "VOICE STYLE\n"
        "Speak natural Tanglish — Telugu + everyday English, not pandit-style literary Telugu. "
        "Be persuasive until a firm refusal, then stop. Keep every live reply to 60–80 characters unless the caller asks for more detail. "
        "Avoid filler words at the start of every turn — no repeated అవును or సరే. "
        "Speak like a real human; vary wording. Never ask again for quantity, color, delivery, or budget once given. "
        "Understand intent before responding. Ask only one useful question at a time. "
        "Use natural Telugu with English words like pickup, delivery, price, order, confirm. "
        "Adapt to the customer's tone. Always move the conversation forward — answer, handle objection, or advance the sale.\n\n"
        "CONVERSATION FLOW\n"
        "Step 1: Confirm product need (pens, gift sets). "
        "Step 2: Ask quantity if unknown. "
        "Step 3: Ask budget if unknown. "
        "Step 4: Ask pickup or delivery and location. "
        "Step 5: Confirm color preference if relevant. "
        "Step 6: Summarize order and ask to confirm.\n\n"
        "OBJECTION HANDLING\n"
        "If price concern: offer to check best pack within budget without inventing numbers.\n\n"
        "GUARDRAILS\n"
        "Never invent prices or stock. Confirm unclear speech once.\n\n"
        "CLOSING\n"
        "Confirm order details and thank the customer."
    ),
    "agent_name": "Kavya",
    "company_name": "PenMart",
}


def _client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-seven-turn")
    monkeypatch.setenv("SARVAM_API_KEY", "sv-seven-turn")
    monkeypatch.setenv("ENABLE_WORKING_MEMORY", "true")
    get_settings.cache_clear()
    return TestClient(app_mod.app)


def _script_has_voice_rules(text: str) -> bool:
    lower = text.lower()
    hits = sum(1 for m in AGENT_VOICE_RULE_MARKERS if m.lower() in lower)
    return hits >= 4


@pytest.fixture
def client(monkeypatch):
    return _client(monkeypatch)


@pytest.mark.asyncio
async def test_seven_turn_agent_brief_script_rules_and_conversation(client, capsys):
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
    agent_script = save_j.get("agentScript") or ""
    brain_full = save_j.get("brainPromptFull") or ""

    assert save_j.get("compiledVersion", 0) >= 1
    assert "Kavya" in agent_script
    assert _script_has_voice_rules(agent_script), f"voice rules missing from script: {agent_script[:400]}"

    eff = client.get("/api/prompt/effective", params={"sessionId": sid, "transcript": "test"}).json()
    brain_used = eff.get("brainPrompt") or brain_full
    assert "Kavya" in brain_used
    assert _script_has_voice_rules(brain_used)

    agents = client.get("/api/agents").json()
    agent_id = agents["agents"][0]["agent_id"]
    start = client.post(
        "/api/call/start",
        json={"agentId": agent_id, "sessionId": sid, "channel": "browser"},
    )
    assert start.status_code == 200, start.text
    call_id = start.json()["call_id"]

    turn_idx = {"n": 0}
    CACHE_PREFIX = 1100
    transcript_log: list[dict] = []

    def _memory_ops(transcript: str) -> list[dict]:
        ops: list[dict] = []
        if "50" in transcript or "pieces" in transcript.lower():
            ops.append({"op": "set_fact", "key": "quantity", "value": "50 pieces"})
        if "5000" in transcript or "budget" in transcript.lower():
            ops.append({"op": "set_fact", "key": "budget", "value": "5000 rupees"})
        if "Hyderabad" in transcript or "హైదరాబాద్" in transcript:
            ops.append({"op": "set_fact", "key": "location", "value": "Hyderabad"})
        if "blue" in transcript.lower():
            ops.append({"op": "set_fact", "key": "color", "value": "blue"})
        if "confirm" in transcript.lower():
            ops.append({"op": "append_context", "value": "Order confirmation requested"})
        return ops

    async def mock_turn(**kwargs):
        turn_idx["n"] += 1
        n = turn_idx["n"]
        transcript = kwargs.get("transcript", "")
        cached = CACHE_PREFIX if n > 1 else 0
        write = CACHE_PREFIX if n == 1 else 0
        ops = _memory_ops(transcript)
        responses = {
            1: "Namaste! Nenu Kavya, PenMart nundi. Corporate gifting ki pens kavala?",
            2: "Premium pens and gift sets unnaayi. Enni pieces kavali?",
            3: "50 pieces, 5000 budget — noted. Pickup aa delivery?",
            4: "Hyderabad delivery — noted. Blue color preference unda?",
            5: "Blue pens — noted. Order confirm cheyyala?",
            6: "Order confirm chesanu — 50 blue pens, delivery Hyderabad, budget 5000. Thank you!",
            7: "Dhanyavaadalu! PenMart ki call chesinanduku thanks.",
        }
        text = responses.get(n, "Sare, inka emaina help kavala?")
        return {
            "text": text,
            "language_context": {"responseLanguage": "te-IN"},
            "usage": {
                "input_tokens": 1200 + n * 5,
                "output_tokens": 22,
                "cached_tokens": cached,
                "cache_write_tokens": write,
            },
            "memory_update": {"operations": ops},
            "request_id": f"mock-{n}",
        }

    with patch(
        "server.call.live_turn_orchestrator.generate_response",
        new=AsyncMock(side_effect=mock_turn),
    ):
        for user_text, note in TURNS:
            r = client.post(
                "/api/brain",
                json={
                    "sessionId": sid,
                    "callId": call_id,
                    "transcript": user_text,
                    "language_code": "te-IN",
                },
            )
            assert r.status_code == 200, r.text
            j = r.json()
            transcript_log.append(
                {
                    "turn": len(transcript_log) + 1,
                    "user": user_text,
                    "agent": j.get("text", ""),
                    "note": note,
                    "cached_tokens": j.get("usage", {}).get("cached_tokens", 0),
                }
            )

    assert len(transcript_log) == 7
    assert re.search(r"Kavya|PenMart", transcript_log[0]["agent"], re.I)
    for i in range(1, 7):
        assert transcript_log[i]["cached_tokens"] == CACHE_PREFIX

    mem = client.get(f"/api/call/{call_id}/memory").json().get("memory") or {}
    facts = mem.get("facts") or {}
    assert facts.get("quantity") == "50 pieces"
    assert facts.get("budget") == "5000 rupees"
    assert facts.get("location") == "Hyderabad"
    assert facts.get("color") == "blue"

    # UTF-8 report for inspection (pytest -s on Windows may fail on Telugu print)
    report_path = "data/dev-logs/seven_turn_agent_brief_report.txt"
    import os
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("AGENT BRIEF\n" + "=" * 72 + "\n" + BRIEF + "\n\n")
        f.write("GENERATED CALLING SCRIPT\n" + "=" * 72 + "\n" + agent_script + "\n\n")
        f.write("BRAIN PROMPT USED (excerpt)\n" + "=" * 72 + "\n")
        f.write(brain_used[:2500] + ("..." if len(brain_used) > 2500 else "") + "\n\n")
        f.write("7-TURN CONVERSATION\n" + "=" * 72 + "\n")
        for row in transcript_log:
            f.write(f"\n--- Turn {row['turn']} ({row['note']}) ---\n")
            f.write(f"USER:  {row['user']}\n")
            f.write(f"AGENT: {row['agent']}\n")
            if row["cached_tokens"]:
                f.write(f"       [cache hit: {row['cached_tokens']} tokens]\n")

    client.post("/api/call/end", json={"callId": call_id, "reason": "user_stop"})
    client.delete("/api/instructions", params={"sessionId": sid})
    get_settings.cache_clear()
