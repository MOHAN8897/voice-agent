"""Session brain locks on call start for Test Studio fine-tune."""
from server.call.call_lifecycle_service import CallLifecycleService
from server.agent.instruction_store import instruction_store


async def test_lock_session_brain_over_versioned(monkeypatch):
    monkeypatch.setenv("USE_VERSIONED_BRAINS", "true")
    from server.config.env import get_settings

    get_settings.cache_clear()
    sid = "lock-brain-test"
    instruction_store.save_agent_script(
        sid,
        "Telecaller Priya for Acme.",
        "AGENT IDENTITY\nPriya from Acme.\n" + ("x " * 400),
        "friendly",
        compiled_brain="--- SAFETY ---\n\nPriya script brain " + ("y " * 500),
        optimizer_report={},
        source_checksum="abc",
    )
    svc = CallLifecycleService()
    version, text = await svc._lock_compiled_brain("any-agent", session_id=sid)
    assert version == "session-v1"
    assert "Priya" in (text or "")
    instruction_store.clear(sid)
    get_settings.cache_clear()
