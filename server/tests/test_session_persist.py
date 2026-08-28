"""Session override disk persistence."""
from __future__ import annotations

from fastapi.testclient import TestClient

import server.app as app_mod
from server.agent.instruction_store import instruction_store
from server.services.runtime_settings import runtime_settings


def test_instructions_survive_store_reload():
    c = TestClient(app_mod.app)
    sid = "persist-test-instructions"
    marker = "DISK_PERSIST_MARKER_XYZ"
    r = c.post(
        "/api/instructions",
        json={
            "sessionId": sid,
            "behaviourInstructions": marker,
            "businessInstructions": "business line",
            "language_code": "te-IN",
        },
    )
    assert r.status_code == 200, r.text

    instruction_store._store.clear()
    instruction_store._hydrate_from_disk()
    assert marker in instruction_store.get_behaviour(sid)

    c.delete("/api/instructions", params={"sessionId": sid})


def test_runtime_survive_store_reload():
    c = TestClient(app_mod.app)
    sid = "persist-test-runtime"
    r = c.post(
        "/api/settings/runtime",
        json={"sessionId": sid, "openaiModel": "gpt-5.6-luna", "openaiMaxTokens": 120},
    )
    assert r.status_code == 200, r.text

    runtime_settings._store.clear()
    runtime_settings._hydrate_from_disk()
    vals = runtime_settings.get(sid)
    assert vals.get("openaiModel") == "gpt-5.6-luna"
    assert vals.get("openaiMaxTokens") == 120

    c.delete("/api/settings/runtime", params={"sessionId": sid})
