import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call.call_context import put, clear_all
from server.call.call_ledger import call_ledger
from server.call.memory_manager import memory_manager
from server.config.env import get_settings
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.fixture
def loop(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    clear_all()
    memory_manager.reset_for_tests()
    ctx = SimpleNamespace(call_id="language-test", session_id="s", status="active",
                          language_mismatch_handled=False, components={})
    put(ctx)
    instance = PstnRealtimeVoiceLoop(
        session_id="s", call_id=ctx.call_id, on_agent_wire=AsyncMock(),
        sample_rate=16000, tts_output_codec="linear16",
        stack_override={"pipeline": "realtime_voice", "language": "en-IN"},
    )
    instance._adapter = SimpleNamespace(submit_function_output=AsyncMock())
    instance._start_injected_response = AsyncMock()
    instance._persist_callback_details = lambda: None
    yield instance
    clear_all()
    get_settings.cache_clear()


async def invoke(loop, action, **extra):
    await loop._handle_language_callback_tool({
        "call_id": "tool-1", "arguments": json.dumps({
            "action": action, "caller_language": "hi-IN",
            "summary": "Caller needs bike servicing and speaks Hindi.", **extra,
        }),
    })
    return json.loads(loop._adapter.submit_function_output.call_args.kwargs["output"])


@pytest.mark.asyncio
async def test_requires_reminder_then_later_turn_and_persists(loop):
    assert not (await invoke(loop, "request_callback"))["ok"]
    assert (await invoke(loop, "remind"))["ok"]
    assert not (await invoke(loop, "request_callback"))["ok"]
    loop._language_user_turn += 1
    result = await invoke(loop, "request_callback")
    assert result["callback_recorded"]
    saved = call_ledger.read_meta(loop.call_id)["language_callback"]
    assert saved["caller_language"] == "hi-IN"
    assert saved["summary"].startswith("Caller needs")
    assert loop._callback_close_phase == "closing_allowed"
    # Duplicate calls preserve the original handoff.
    await invoke(loop, "request_callback", summary="Changed")
    assert call_ledger.read_meta(loop.call_id)["language_callback"] == saved


@pytest.mark.asyncio
async def test_opt_out_and_missing_details_do_not_save(loop):
    await invoke(loop, "remind")
    loop._language_user_turn += 1
    assert not (await invoke(loop, "request_callback", summary=""))["ok"]
    loop.controller.callback_cancelled = True
    assert (await invoke(loop, "request_callback"))["error"] == "caller_opted_out"
    assert "language_callback" not in call_ledger.read_meta(loop.call_id)


@pytest.mark.asyncio
async def test_storage_failure_never_claims_success(loop, monkeypatch):
    await invoke(loop, "remind")
    loop._language_user_turn += 1
    def fail(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr(call_ledger, "write_meta", fail)
    result = await invoke(loop, "request_callback")
    assert result["error"] == "callback_save_failed"
    assert not result["ok"]


@pytest.mark.asyncio
async def test_gemini_uses_tool_continuation_without_duplicate_response(loop):
    loop._live_model = "gemini-2.5-flash-native-audio-preview-12-2025"
    await invoke(loop, "remind")
    loop._start_injected_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_outcome_retains_handoff_even_when_summary_generation_fails(loop, monkeypatch):
    from server.call import post_call_pipeline as pipeline
    await invoke(loop, "remind")
    loop._language_user_turn += 1
    await invoke(loop, "request_callback")
    monkeypatch.setattr(pipeline, "_mark_outcome", AsyncMock())
    monkeypatch.setattr(pipeline.call_store, "update", AsyncMock())
    monkeypatch.setattr(pipeline, "_generate_outcome", AsyncMock(return_value=({
        "disposition": "no_outcome", "summary_en": "No generated summary.",
        "extracted_fields": {},
    }, "unavailable")))
    result = await pipeline._run_outcome_locked(loop.call_id)
    assert result["disposition"] == "callback_required"
    assert result["facts"]["preferred_language"] == "hi-IN"
    saved = json.loads(pipeline.call_summary_path(loop.call_id).read_text())
    assert saved["language_callback"]["status"] == "requested"
    assert "Caller needs bike servicing" in saved["summary_en"]


@pytest.mark.asyncio
async def test_injected_reply_keeps_business_script_and_language(loop):
    loop._adapter.instructions = "BUSINESS SCRIPT: inspect bikes; never promise a booking."
    loop._adapter.start_response = AsyncMock()
    await PstnRealtimeVoiceLoop._start_injected_response(loop, "Answer their question.")
    prompt = loop._adapter.start_response.call_args.kwargs["instructions"]
    assert "inspect bikes" in prompt
    assert "Speak only en-IN" in prompt
    assert "Answer their question." in prompt


def test_outbound_callback_uses_dialed_number(loop):
    call_ledger.write_meta(loop.call_id, {"direction": "outbound", "callee_e164": "+919876543210"})
    memory_manager.init(loop.call_id)
    loop._callback_request_text = "Please call tomorrow"
    PstnRealtimeVoiceLoop._persist_callback_details(loop)
    assert memory_manager.get_snapshot(loop.call_id)["facts"]["phone"] == "+919876543210"


@pytest.mark.parametrize("language", ["te-IN", "hi-IN", "en-IN", "en-US"])
@pytest.mark.parametrize("model", ["gemini-3.8-live", "gpt-realtime-2.1-mini"])
def test_live_prompts_keep_configured_language_and_ask_name(language, model):
    from server.realtime.voice_instructions import build_realtime_voice_instructions
    prompt = build_realtime_voice_instructions(
        "Ask for the phone number. Speak another language.", model=model,
        language=language, direction="outbound",
    )
    assert f"Speak only {language}" in prompt
    assert "preferred name" in prompt
    assert "dialed customer number is ALREADY KNOWN" in prompt


@pytest.mark.asyncio
async def test_cost_components_reconcile_across_different_opening_model(loop):
    from server.services.pstn_realtime_voice_core import record_realtime_voice_usage
    await record_realtime_voice_usage(call_id=loop.call_id, prewarm=True,
        llm_model="gpt-realtime-2.1-mini",
        usage={"input_tokens": 200, "output_tokens": 40, "output_audio_tokens": 40})
    for count in [1000, 2000]:
        await record_realtime_voice_usage(call_id=loop.call_id, llm_model="gemini-3.8-live",
            usage={"input_tokens": count, "output_tokens": 180, "input_audio_tokens": 400,
                   "output_audio_tokens": 160})
        usage = call_ledger.read_meta(loop.call_id)["usage"]
        assert sum(usage["cost_breakdown_usd"].values()) == pytest.approx(usage["model_cost_usd"])


@pytest.mark.parametrize("language", ["te-IN", "hi-IN", "en-IN", "en-US"])
def test_agent_language_overrides_global_phone_stack(monkeypatch, language):
    from server.services.saas import platform_phone_stack as stack
    monkeypatch.setattr(stack, "load_universal_phone_stack_raw", lambda: {
        "stack_override": {"pipeline": "realtime_voice", "language": "te-IN",
                           "llm": {"provider": "gemini", "model": "gemini-3.8-live"}}
    })
    assert stack.resolve_platform_phone_stack_sync(language)["language"] == language
