"""Call-level live prompt preview API."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import server.app as app_mod
from server.agent.instruction_store import instruction_store
from server.call.audio_archive import audio_archive
from server.call.call_context import CallContext, clear_all, get as get_ctx
from server.call.call_ledger import call_ledger
from server.call.call_prompt_preview import build_live_prompt_for_call, get_call_prompt_preview
from server.call.call_store import call_store
from server.config.env import get_settings
from server.providers.base import ResolvedStack, StageSelection


def _reset(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "false")
    clear_all()
    call_ledger.reset_for_tests()
    audio_archive.reset_for_tests()
    call_store.reset_for_tests()
    get_settings.cache_clear()


def test_prompt_preview_api_active_call(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    sid = "preview-api-session"
    brain = (
        "--- AGENT IDENTITY ---\nYou are Priya from Acme Insurance.\n\n"
        "--- CANONICAL OPENING ---\nExample opening: Hi, Priya from Acme. Moment?\n"
    )
    instruction_store.save_agent_script(
        sid,
        "Priya sells insurance for Acme.",
        "ROLE\nSell term plans.",
        "friendly",
        compiled_brain=brain,
        optimizer_report={},
        source_checksum="prev1",
    )
    c = TestClient(app_mod.app)
    started = c.post(
        "/api/call/start",
        json={"sessionId": sid, "channel": "browser", "direction": "outbound"},
    )
    assert started.status_code == 200
    call_id = started.json()["call_id"]
    r = c.get(f"/api/call/{call_id}/prompt-preview")
    assert r.status_code == 200
    body = r.json()
    assert body["call_id"] == call_id
    assert body["brain_source"] == "test_studio_session"
    assert "Acme" in body["live_prompt"]
    assert body["compiled_brain_version"] == "session-v1"
    assert body["layers"][0]["layer"] == "compiled_brain"
    assert body["token_estimate"] > 0
    instruction_store.clear(sid)


@pytest.mark.asyncio
async def test_prompt_preview_session_brain_locked_in_meta(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    sid = "preview-lock-meta"
    locked = "LOCKED SESSION BRAIN " + ("z " * 200)
    instruction_store.save_agent_script(
        sid,
        "brief",
        "script",
        "friendly",
        compiled_brain=locked,
        optimizer_report={},
        source_checksum="x",
    )
    c = TestClient(app_mod.app)
    call_id = c.post("/api/call/start", json={"sessionId": sid}).json()["call_id"]
    meta = call_ledger.read_meta(call_id)
    assert "LOCKED SESSION BRAIN" in (meta.get("compiled_brain_text") or "")
    assert meta.get("brain_source") == "test_studio_session"

    clear_all()
    preview = await get_call_prompt_preview(call_id)
    assert "LOCKED SESSION BRAIN" in preview["live_prompt"]
    assert preview["brain_source"] == "test_studio_session"
    instruction_store.clear(sid)


def test_live_prompt_gemini_includes_pinned_flow_header():
    brain = (
        "--- AGENT IDENTITY ---\nPriya, Acme.\n\n"
        "--- OUTBOUND WORKFLOW ---\nAsk if they have a moment.\n"
    )
    live, provider, layers = build_live_prompt_for_call(
        brain,
        pipeline="realtime_voice",
        stack_override={"llm": {"provider": "gemini", "model": "gemini-3.8-live"}},
        llm_model="gemini-3.8-live",
        language="en-IN",
        direction="outbound",
        caller_id=None,
    )
    assert provider == "gemini"
    assert "GEMINI LIVE PSTN" in live
    assert "PINNED CONVERSATION FLOW" in live or "moment" in live.lower()
    assert layers[1]["layer"] == "realtime_voice_session"


def test_live_prompt_openai_realtime_voice_path():
    brain = "--- AGENT IDENTITY ---\nYou are Alex.\n"
    live, provider, _layers = build_live_prompt_for_call(
        brain,
        pipeline="realtime_voice",
        stack_override={"llm": {"provider": "openai", "model": "gpt-realtime-2.1-mini"}},
        llm_model="gpt-realtime-2.1-mini",
        language="te-IN",
        direction="inbound",
        caller_id="+919999999999",
    )
    assert provider == "openai"
    assert "Alex" in live
    assert "OUTPUT MODALITY RULES" in live
    assert "GEMINI LIVE PSTN" not in live


@pytest.mark.asyncio
async def test_prompt_preview_from_active_context():
    stack = ResolvedStack(
        combination_id="c1",
        tier="medium",
        mode="frontend",
        stt=StageSelection("sarvam", "m", {}),
        llm=StageSelection("openai", "gpt-realtime-2.1-mini", {}),
        tts=StageSelection("sarvam", "v", {}),
        language="en-IN",
    )
    put_ctx = CallContext(
        call_id="ctx-preview",
        tenant_id="t1",
        agent_id="a1",
        session_id="s1",
        channel="pstn",
        direction="outbound",
        environment="development",
        tier="medium",
        resolved_stack=stack,
        compiled_brain_version="session-v3",
        compiled_brain_text="--- AGENT IDENTITY ---\nOutbound seller.\n",
        started_at=datetime.now(timezone.utc),
        storage_path="data/calls/ctx-preview/",
        pipeline="realtime_voice",
    )
    from server.call.call_context import put

    put(put_ctx)
    call_ledger.meta_path("ctx-preview").parent.mkdir(parents=True, exist_ok=True)
    call_ledger.meta_path("ctx-preview").write_text(
        '{"call_id":"ctx-preview","language":"en-IN","pipeline":"realtime_voice"}',
        encoding="utf-8",
    )
    preview = await get_call_prompt_preview("ctx-preview")
    assert "Outbound seller" in preview["live_prompt"]
    assert preview["direction"] == "outbound"
    assert preview["provider"] == "openai"
    clear_all()
