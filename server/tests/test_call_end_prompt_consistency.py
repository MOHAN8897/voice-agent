from unittest.mock import AsyncMock

import pytest

from server.call.call_end_policy import allowed_reasons_for, default_call_end_policy
from server.prompts.agent_voice_rules import SPOKEN_PACKS, script_writer_system, live_realtime_output_rules
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.mark.parametrize("locale", tuple(SPOKEN_PACKS))
def test_script_writer_does_not_override_locale_or_claim_human_identity(locale):
    prompt = script_writer_system(language=locale, budget_tokens=3500)
    assert "The agent is always a person" not in prompt
    if not locale.startswith("en"):
        assert "VOICE STYLE: natural spoken phone English" not in prompt
    assert "brief's currency" in prompt


@pytest.mark.parametrize("locale", tuple(SPOKEN_PACKS))
def test_live_output_allows_policy_approved_goal_completion(locale):
    prompt = live_realtime_output_rules(locale)
    assert "completed script objective with the agreed next step confirmed" in prompt
    assert "Never hang up on okay/thanks alone" in prompt


@pytest.mark.parametrize("policy", [None, {}, {"allowedReasons": ["invalid"]}])
def test_missing_policy_cannot_enable_out_of_scope_hangup(policy):
    assert allowed_reasons_for(policy) == frozenset(default_call_end_policy()["allowedReasons"])
    assert "out_of_scope" not in allowed_reasons_for(policy)


def test_explicit_out_of_scope_overlay_is_preserved():
    assert allowed_reasons_for({"allowedReasons": ["out_of_scope"]}) == {"out_of_scope"}


@pytest.mark.asyncio
async def test_silent_farewell_retry_does_not_loop_until_watchdog():
    loop = PstnRealtimeVoiceLoop(session_id="test", call_id=None, on_agent_wire=AsyncMock(), adapter=object())
    loop._pending_end_call = {"should_end": True, "reason": "goodbye"}
    loop._pending_farewell_text = "Thank you. Goodbye."
    loop._start_injected_response = AsyncMock()
    loop._finish_hangup = AsyncMock()
    await loop._finalize_hangup_after_farewell()
    loop._start_injected_response.assert_awaited_once()
    loop._finish_hangup.assert_not_awaited()
    await loop._finalize_hangup_after_farewell()
    loop._start_injected_response.assert_awaited_once()
    loop._finish_hangup.assert_awaited_once()
    assert loop._farewell_complete
