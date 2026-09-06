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


async def test_fitted_session_brain_keeps_default_hangup():
    from unittest.mock import AsyncMock, patch

    from server.brain.business_prompt_optimizer import OptimizerResult
    from server.brain.session_brain_compiler import compile_session_brain

    long_body = "Qualify budget and location for every plot inquiry. " * 220
    opt = OptimizerResult(optimized_business_prompt=long_body)
    with patch(
        "server.brain.session_brain_compiler.optimize_session_dual_prompt",
        new=AsyncMock(return_value=opt),
    ):
        compiled, *_ = await compile_session_brain(
            behaviour="Be brief.",
            business="We sell plots in Hyderabad.",
            language="en-IN",
            budget_tokens=1800,
        )
    assert "--- CALL END POLICY ---" in compiled
    assert "Thank you for your time. Goodbye." in compiled
