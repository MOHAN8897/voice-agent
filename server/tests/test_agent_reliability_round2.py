"""Second round of the 10 Nov 2026 audit: default voice, tool waits, in-flight actions,
expired connections, inbound start failures, the control-check model and bare thanks."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from server.services import pstn_voice_core as core
from server.services.pstn_backchannel import (
    HOLDING_PHRASES,
    STILL_CHECKING_PHRASES,
    PstnBackchannelController,
)


# ------------------------------------------------------------------ a new agent can be called
def _profile_record():
    return {"revision": 9, "publicAliases": {
        "engines": {"e1": "eng_pub"},
        "models": {"e1::m1": "mod_pub"},
        "voices": {"e1::m1::v_hi": "voc_hindi", "e1::m1::v_te": "voc_telugu", "e1::m1::v_multi": "voc_multi"},
    }, "profile": {"supportedLanguages": ["te-IN", "hi-IN"], "engines": [{"id": "e1", "models": [{"id": "m1", "voices": [
        {"id": "v_multi", "languages": ["hi-IN", "te-IN"], "preferredLanguages": ["hi-IN"]},
        {"id": "v_hi", "languages": ["hi-IN"]},
        {"id": "v_te", "languages": ["te-IN"], "preferredLanguages": ["te-IN"]},
    ]}]}]}}


@pytest.fixture
def profiles(monkeypatch):
    from server.services.saas import voice_stack_profiles as vsp

    monkeypatch.setattr(vsp, "load_profile_records", AsyncMock(return_value={"medium": _profile_record()}))
    monkeypatch.setattr(vsp, "_load_rates_without_fallback", AsyncMock(return_value={}))
    monkeypatch.setattr(vsp, "readiness_for_profile", lambda *_: {"ready": True, "enabled": True, "blockers": []})
    return vsp


@pytest.mark.asyncio
async def test_default_voice_is_one_that_speaks_the_agent_language(profiles):
    telugu = await profiles.default_agent_voice_selection("development", "medium", "te-IN")
    assert telugu == {"stackSelectionVersion": 1, "profileRevision": 9,
                      "engineId": "eng_pub", "modelId": "mod_pub", "voiceId": "voc_telugu"}
    hindi = await profiles.default_agent_voice_selection("development", "medium", "hi-IN")
    assert hindi["voiceId"] == "voc_multi"   # the voice that prefers Hindi wins


@pytest.mark.asyncio
async def test_no_default_voice_when_the_profile_cannot_speak_the_language(profiles, monkeypatch):
    assert await profiles.default_agent_voice_selection("development", "medium", "ta-IN") is None
    monkeypatch.setattr(profiles, "readiness_for_profile", lambda *_: {"ready": False, "enabled": True, "blockers": []})
    assert await profiles.default_agent_voice_selection("development", "medium", "te-IN") is None


@pytest.mark.asyncio
async def test_creation_saves_the_default_voice_and_survives_its_failure(monkeypatch):
    from server.routes import app_agents

    selection = {"stackSelectionVersion": 1, "profileRevision": 9, "engineId": "e", "modelId": "m", "voiceId": "v"}
    monkeypatch.setattr("server.services.saas.voice_stack_profiles.default_agent_voice_selection",
                        AsyncMock(return_value=selection))
    patched = AsyncMock(return_value={"agent_id": "a1", "voice_settings": selection})
    monkeypatch.setattr(app_agents.agent_service, "patch_agent", patched)
    agent = await app_agents._save_default_voice({"agent_id": "a1"}, "a1", tenant_id="t1", language="te-IN")
    assert agent["voice_settings"] == selection
    assert patched.await_args.kwargs["expected_voice_revision"] == 0
    # A voice the tenant already chose is never replaced.
    patched.reset_mock()
    kept = {"agent_id": "a1", "voice_settings": {"stackSelectionVersion": 1, "voiceId": "own"}}
    assert await app_agents._save_default_voice(kept, "a1", tenant_id="t1", language="te-IN") is kept
    patched.assert_not_awaited()
    # Saving the voice can fail; the created agent is still returned.
    patched.side_effect = RuntimeError("store down")
    fresh = {"agent_id": "a1"}
    assert await app_agents._save_default_voice(fresh, "a1", tenant_id="t1", language="te-IN") is fresh


# ------------------------------------------------------------------ tool waits
def test_every_language_has_a_still_checking_line():
    assert set(STILL_CHECKING_PHRASES) == set(HOLDING_PHRASES)


@pytest.fixture
def waiting(monkeypatch):
    """A composed turn that is thinking while an action runs."""
    loop = core.PstnVoiceLoop(session_id="tool-wait", call_id=None, on_agent_wire=AsyncMock())
    loop.current_generation_id = "gen"
    loop.current_turn_id = "turn-1"
    loop._turn_busy = True
    loop._set_phase(core.PHASE_THINKING)
    controller = loop._backchannel
    controller._hold_frames = [b"\x01" * 640]
    controller._checking_frames = [b"\x02" * 640]
    return loop, controller


@pytest.mark.asyncio
async def test_a_tool_wait_speaks_at_once_then_keeps_the_caller_company(waiting, monkeypatch):
    loop, controller = waiting
    monkeypatch.setattr("server.services.pstn_backchannel.TOOL_HOLD_REPEAT_S", 0.05)
    controller.note_tool_wait("turn-1")
    await asyncio.sleep(0.02)
    assert loop.on_agent_wire.await_count == 1          # "one second", no 1.5 s delay
    await asyncio.sleep(0.2)
    sent = [call.args[0][:1] for call in loop.on_agent_wire.await_args_list]
    assert sent[0] == b"\x01" and b"\x02" in sent[1:]    # then "still checking"
    # The reply is ready: the loop stops and nothing more is said.
    controller.cancel_hold()
    count = loop.on_agent_wire.await_count
    await asyncio.sleep(0.12)
    assert loop.on_agent_wire.await_count == count


@pytest.mark.asyncio
async def test_settle_hold_waits_for_the_line_then_stops_the_loop(waiting, monkeypatch):
    loop, controller = waiting
    monkeypatch.setattr("server.services.pstn_backchannel.TOOL_HOLD_REPEAT_S", 5.0)
    controller.note_tool_wait("turn-1")
    await asyncio.sleep(0.02)
    await asyncio.wait_for(controller.settle_hold(), timeout=1.0)   # never waits for the repeat
    assert controller._hold_task is None


def test_caller_speech_does_not_cancel_a_turn_whose_action_is_running(monkeypatch):
    value = [100.0]
    monkeypatch.setattr(core, "time", SimpleNamespace(monotonic=lambda: value[0], perf_counter=time.perf_counter))
    loop = core.PstnVoiceLoop(session_id="in-flight", call_id=None, on_agent_wire=AsyncMock())
    loop._set_phase(core.PHASE_THINKING)
    loop._turn_busy = True
    loop._last_vad_voice_at = 100.0
    loop._current_turn_transcript = "book it for 4 PM"
    text = "actually can you also tell me the price"
    loop._turn_tool_wait = False
    assert loop._should_cancel_unheard_reply(text) is True
    loop._turn_tool_wait = True
    assert loop._should_cancel_unheard_reply(text) is False
    assert loop._should_think_cancel("stop") is False


# ------------------------------------------------------------------ expired connections
@pytest.mark.asyncio
async def test_an_expired_connection_is_flagged_so_it_stops_being_offered(monkeypatch):
    from server.services import nango_service as module

    gateway = module.NangoService(secret_key="k", base_url="http://nango.test")
    monkeypatch.setattr(gateway, "_get_nango_connection_id", AsyncMock(return_value="conn-1"))
    response = httpx.Response(424, request=httpx.Request("POST", "http://nango.test/proxy"))
    monkeypatch.setattr(gateway, "_execute_proxy_tool", AsyncMock(
        side_effect=httpx.HTTPStatusError("refresh failed", request=response.request, response=response)))
    flagged = AsyncMock()
    monkeypatch.setattr(gateway, "_flag_needs_reauth", flagged)
    monkeypatch.setattr("server.services.tool_schema_registry.validate_tool_arguments", lambda *_: None)
    result = await gateway.execute_in_call_tool("00000000-0000-4000-8000-000000000001", "GMAIL_SEND_EMAIL",
                                                {"to": "a@example.com", "subject": "s", "body": "b"})
    assert result["status"] == "error" and "re-authorized" in result["message"]
    flagged.assert_awaited_once()
    assert flagged.await_args.args[1].upper().startswith("GMAIL")


# ------------------------------------------------------------------ inbound start failure
@pytest.mark.asyncio
async def test_an_answered_call_that_cannot_start_hears_an_apology(monkeypatch):
    from server.services import vobiz_pstn_bridge as bridge_module

    bridge = bridge_module.VobizPstnBridge(MagicMock(send_text=AsyncMock()))
    bridge.call_uuid = "live-call-uuid"
    transfer = AsyncMock(return_value={})
    monkeypatch.setattr("server.services.saas.voice_kyc_service.vobiz_client_for_call",
                        AsyncMock(return_value=SimpleNamespace(transfer_call=transfer)))
    monkeypatch.setattr("server.config.urls.public_api_base", lambda: "https://voice.example")
    monkeypatch.setattr(bridge_module.vobiz_call_registry, "get", lambda _uuid: {})
    await bridge._speak_start_failure("RuntimeError")
    transfer.assert_awaited_once_with("live-call-uuid", aleg_url="https://voice.example/api/vobiz/fallback")
    # A failure to redirect never raises: cleanup still ends the call.
    transfer.side_effect = RuntimeError("carrier down")
    await bridge._speak_start_failure("RuntimeError")


# ------------------------------------------------------------------ control-check model
def test_control_checks_stay_on_the_call_model_unless_an_enabled_one_is_configured(monkeypatch):
    from server.call import close_classifier as cc
    from server.providers.base import StageSelection

    stack = StageSelection(provider="sarvam", model="sarvam-105b-conversations", config={"api_mode": "x"})
    registry = SimpleNamespace(is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True)
    monkeypatch.setattr("server.providers.get_provider_registry", lambda: registry)

    def settings(provider="", model=""):
        monkeypatch.setattr("server.config.env.get_settings", lambda: SimpleNamespace(
            control_check_llm_provider=provider, control_check_llm_model=model))

    settings()
    assert cc.control_llm(stack) is stack
    settings("gemini", "gemini-fast")
    chosen = cc.control_llm(stack)
    assert (chosen.provider, chosen.model) == ("gemini", "gemini-fast")
    registry.is_provider_enabled = lambda *_: False
    assert cc.control_llm(stack) is stack          # a disabled provider is never used
    settings("gemini", "")
    assert cc.control_llm(stack) is stack          # half a setting changes nothing


# ------------------------------------------------------------------ bare thanks
def _ctx(**overrides):
    base = dict(call_end_policy=None, status="active", agent_hangup_armed=False, barge_in_flight=False,
                last_stt_partial_at=None, pending_tool_result=False, action_receipts=[],
                communication_receipts=[], callback_request_text="", callback_when="", callback_close_phase="idle")
    return SimpleNamespace(**{**base, **overrides})


def _close(evidence):
    return {"decision": "close", "close_verified": True, "evidence": evidence, "remaining_request": "",
            "reason": "goodbye", "contact_intent": "end_this_call", "contact_verified": True}


@pytest.mark.parametrize("thanks", ["ఓకే థ్యాంక్ యూ.", "thank you", "ठीक है धन्यवाद"])
def test_a_bare_thanks_does_not_end_a_call_where_nothing_was_done(thanks):
    from server.call.semantic_call_control import close_rejection

    assert close_rejection(_close(thanks), ctx=_ctx(), transcript=thanks) == "thanks_without_outcome"


def test_thanks_closes_after_a_booking_and_a_goodbye_always_closes():
    from server.call.semantic_call_control import close_rejection

    booked = _ctx(action_receipts=[{"outcome": "appointment_confirmed"}])
    assert close_rejection(_close("ఓకే థ్యాంక్ యూ."), ctx=booked, transcript="ఓకే థ్యాంక్ యూ.") is None
    noted = _ctx(callback_request_text="call me at 6")
    assert close_rejection(_close("thank you"), ctx=noted, transcript="thank you") is None
    assert close_rejection(_close("ok thank you, bye"), ctx=_ctx(), transcript="ok thank you, bye") is None


# ------------------------------------------------------------------ creation under a rate limit
@pytest.mark.asyncio
async def test_a_rate_limited_generation_waits_long_enough_to_retry(monkeypatch):
    from pydantic import BaseModel

    from server.brain import employee_script_pipeline as pipeline, generation_runtime
    from server.providers.base import LLMConfig

    class Out(BaseModel):
        ok: bool

    calls, sleeps = [], []

    async def completion(**_kw):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Gemini request failed (HTTP 429)")
        return {"ok": True}

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(generation_runtime, "generation_target", lambda: (
        SimpleNamespace(structured_completion=completion), LLMConfig(provider="gemini", model="m")))
    monkeypatch.setattr(pipeline.asyncio, "sleep", fake_sleep)
    result = await pipeline._completion("write", "rules", {}, Out, temperature=0, tokens=500, correlation_id="c")
    assert result.ok is True and len(calls) == 2 and sleeps == [8.0]
