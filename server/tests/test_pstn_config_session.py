"""PSTN outbound inherits Test Studio config session for brain + stack."""
from server.agent.instruction_store import instruction_store
from server.call.call_lifecycle_service import CallLifecycleService


async def test_pstn_start_locks_session_brain_via_config_session(monkeypatch):
    monkeypatch.setenv("USE_VERSIONED_BRAINS", "true")
    from server.config.env import get_settings

    get_settings.cache_clear()
    sid = "test-studio-pstn-lock"
    instruction_store.save_agent_script(
        sid,
        "Telecaller Priya for Acme.",
        "AGENT IDENTITY\nPriya from Acme.\n" + ("x " * 400),
        "friendly",
        compiled_brain="--- SAFETY ---\n\nPSTN inherits this script " + ("y " * 500),
        optimizer_report={},
        source_checksum="pstn-abc",
    )
    svc = CallLifecycleService()
    version, text = await svc._lock_compiled_brain("any-agent", session_id=sid)
    assert version == "session-v1"
    assert "PSTN inherits" in (text or "")
    instruction_store.clear(sid)
    get_settings.cache_clear()
