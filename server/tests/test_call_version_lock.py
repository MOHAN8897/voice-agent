"""Locked L1/L2 versions are immutable for the life of a call."""
from __future__ import annotations

from fastapi.testclient import TestClient

import server.app as app_mod
from server.call.audio_archive import audio_archive
from server.call.call_context import clear_all, get as get_ctx
from server.call.call_ledger import call_ledger
from server.call.call_store import call_store
from server.config.env import get_settings
from server.services.openai_brain_service import _resolve_brain_text


def _reset(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    clear_all()
    call_ledger.reset_for_tests()
    audio_archive.reset_for_tests()
    call_store.reset_for_tests()
    get_settings.cache_clear()


def test_stack_locked_at_start(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    c = TestClient(app_mod.app)
    started = c.post("/api/call/start", json={"sessionId": "lock", "tier": "medium"})
    assert started.status_code == 200
    body = started.json()
    call_id = body["call_id"]
    combo = body["locked_versions"]["combination_id"]
    ctx = get_ctx(call_id)
    assert ctx is not None
    assert ctx.resolved_stack.combination_id == combo
    # Mid-call stack pointer must not change
    assert ctx.resolved_stack.stt.provider == "sarvam"
    assert ctx.resolved_stack.llm.provider == "openai"
    get_settings.cache_clear()


def test_compiled_brain_lock_used_by_live_path(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    from server.call.call_context import CallContext, put
    from server.providers.base import ResolvedStack, StageSelection
    from datetime import datetime, timezone

    stack = ResolvedStack(
        combination_id="lockedcombo",
        tier="medium",
        mode="frontend",
        stt=StageSelection("sarvam", "saaras:v3-realtime", {}),
        llm=StageSelection("openai", "gpt-5.6-luna", {}),
        tts=StageSelection("sarvam", "bulbul:v3", {}),
        language="te-IN",
    )
    put(
        CallContext(
            call_id="brain-lock",
            tenant_id="t",
            agent_id="a",
            session_id="s",
            channel="browser",
            direction="inbound",
            environment="development",
            tier="medium",
            resolved_stack=stack,
            compiled_brain_version="cb_v_locked",
            compiled_brain_text="LOCKED BRAIN TEXT",
            started_at=datetime.now(timezone.utc),
            storage_path="data/calls/brain-lock/",
        )
    )
    text, version = _resolve_brain_text(
        session_id="s",
        language="te-IN",
        user_instructions="",
        business_instructions=None,
        response_style=None,
        budget=2500,
        use_stored_brain=True,
        call_id="brain-lock",
    )
    assert text == "LOCKED BRAIN TEXT"
    assert version == "cb_v_locked"
    get_settings.cache_clear()
