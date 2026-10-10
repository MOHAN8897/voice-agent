"""Tests reproducing and verifying PERF-02: Agent configured language resolution without forced te-IN default."""
from __future__ import annotations

import uuid
import pytest

from server.call.call_lifecycle_service import call_lifecycle_service
from server.call.call_context import get as get_ctx
from server.brain.agent_service import agent_service


@pytest.mark.asyncio
async def test_agent_configured_english_language_not_overridden_by_telugu(monkeypatch):
    """PERF-02: Agents configured with en-IN or hi-IN must resolve to their own configured language."""
    agent_id = str(uuid.uuid4())

    async def _mock_get_agent(_aid):
        return {
            "agent_id": agent_id,
            "tenant_id": str(uuid.uuid4()),
            "languages": ["en-IN"],
            "default_tier": "medium",
        }

    monkeypatch.setattr(agent_service, "get_agent", _mock_get_agent)

    # Start call without explicit language override
    res = await call_lifecycle_service.start(agent_id=agent_id, session_id="test-lang-en")
    call_id = res["call_id"]
    ctx = get_ctx(call_id)
    assert ctx is not None

    meta = res.get("meta") or {}
    # Context or ledger language must be en-IN, NOT te-IN
    from server.call.call_ledger import call_ledger
    read_meta = call_ledger.read_meta(call_id)
    assert read_meta.get("language") == "en-IN", f"Expected en-IN, got {read_meta.get('language')}"

    await call_lifecycle_service.end(call_id)
