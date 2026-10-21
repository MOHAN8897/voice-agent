"""Primary Gemini/Vobiz lifecycle regressions; no live provider requests."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from server.call.call_ledger import call_ledger
from server.config.env import get_settings
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.fixture
async def native_call(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    stack = {"pipeline": "realtime_voice", "language": "te-IN",
             "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
        "transcription": {"live_enabled": True, "post_call_enabled": False, "live_model": "gemini-native"}}
    await call_ledger.init("primary-regression", {"call_id": "primary-regression", "channel": "pstn", "direction": "outbound", "resolved_stack": stack})
    loop = PstnRealtimeVoiceLoop(session_id="regression", call_id="primary-regression", on_agent_wire=AsyncMock(), stack_override=stack)
    loop._live_model = "gemini-3.8-live"
    yield loop
    await loop.close()
    call_ledger.reset_for_tests()


@pytest.mark.asyncio
async def test_primary_live_transcript_uses_same_gemini_audio_session(native_call):
    loop = native_call
    loop._start_caller_stt_sidecar("te-IN", "gemini")
    assert loop._caller_stt is None
    text = "సాయంత్రం కాల్ చేయండి."
    await loop._handle_event({"type": "user_transcript", "text": text, "final": True})
    assert any(row["text"] == text for row in call_ledger.read_lines(loop.call_id))
    await loop._finalize_live_transcript_usage()
    meta = call_ledger.read_meta(loop.call_id)
    assert meta["transcript_source"] == "gemini_live_native"
    assert meta["usage"]["transcription_billing"] == "native_live_included"
    from server.call.call_ledger import _sync_live_transcript_usage
    assert _sync_live_transcript_usage(meta["usage"], meta, duration_sec=80, fx=95) == (0.0, 0.0)


@pytest.mark.asyncio
async def test_telugu_evening_callback_and_spoken_farewell_repair_missed_end_tool(native_call):
    loop = native_call
    text = "ఇప్పుడు కొంచెం బిజీగా ఉన్నాను. మీరు సాయంత్రం కాల్ చేస్తారా ప్లీజ్?"
    loop._user_partial = text
    loop._last_user_final_text = text
    loop._callback_request_text = text
    loop._assistant_text = "సరేనండి, సాయంత్రం కాల్ చేస్తాను. ధన్యవాదాలు. Good day."
    loop._repair_arm_hangup = AsyncMock()
    await loop._maybe_hangup_missed_end_call()
    loop._repair_arm_hangup.assert_awaited_once()
    assert loop._repair_arm_hangup.call_args.args[0]["should_end"] is True


@pytest.mark.asyncio
async def test_greeting_capture_keeps_original_session_history():
    from server.services.pstn_realtime_greeting_prewarm import synthesize_realtime_greeting_frames

    class Adapter:
        start_response = AsyncMock()
        delete_synthetic_response_items = AsyncMock()
        def __init__(self):
            self.events = iter([{"type": "audio_delta", "pcm": b"\0\1" * 960}, {"type": "response_done", "usage": {"output_tokens": 20}}])
        async def poll_event(self, **kwargs):
            return next(self.events, None)
        def discard_queued(self):
            pass

    adapter = Adapter()
    frames, _, _ = await synthesize_realtime_greeting_frames(adapter, greeting_text="Hello, can we talk?", sample_rate=16000, tts_output_codec="linear16", preserve_history=True)
    assert frames
    assert adapter.opening_generated_on_session
    adapter.delete_synthetic_response_items.assert_not_awaited()


@pytest.mark.asyncio
async def test_recording_lookup_rejects_a_different_call():
    from server.services.vobiz_recordings import _find_recording
    client = type("Client", (), {"auth_id": "account", "_request": AsyncMock(return_value={"call_uuid": "someone-else", "recording_url": "https://media.vobiz.ai/private.wav"})})()
    assert await _find_recording(client, "our-call", "recording-id") == {}
    client._request.return_value = {"objects": [{"call_uuid": "someone-else"}, {"call_uuid": "our-call", "recording_id": "ours"}]}
    assert (await _find_recording(client, "our-call"))["recording_id"] == "ours"


@pytest.mark.asyncio
async def test_carrier_recording_callback_updates_internal_call_id(monkeypatch, native_call):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from server.routes import vobiz
    from server.services import vobiz_recordings

    monkeypatch.setattr(vobiz, "_verify_vobiz_request", AsyncMock())
    monkeypatch.setattr(vobiz.vobiz_call_registry, "get", lambda _: {"internal_call_id": native_call.call_id})
    monkeypatch.setattr(vobiz.vobiz_call_registry, "upsert", Mock())
    schedule = Mock()
    monkeypatch.setattr(vobiz_recordings, "schedule_recording_retrieval", schedule)
    app = FastAPI()
    app.include_router(vobiz.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.post("/api/vobiz/recording", json={"CallUUID": "carrier-id", "RecordingID": "recording-id", "RecordUrl": "https://media.vobiz.ai/record.wav"})
    assert response.status_code == 200
    assert call_ledger.read_meta(native_call.call_id)["vobiz_recording_id"] == "recording-id"
    schedule.assert_called_once_with(native_call.call_id)


@pytest.mark.parametrize("text", ["సాయంత్రం కాల్ చేయండి", "ఉదయం కాల్ చేయండి", "రాత్రి కాల్ చేయండి", "sayantram call cheyandi"])
def test_telugu_callback_time_words(text):
    from server.call.end_call_validate import caller_requested_callback
    assert caller_requested_callback(text)


@pytest.mark.asyncio
async def test_prewarmed_session_is_reused_and_opening_starts_without_caller_audio(native_call, monkeypatch):
    import asyncio

    from server.realtime.models import realtime_voice_config
    from server.realtime.testing import FakeRealtimeVoiceAdapter
    from server.realtime.voice_manager import realtime_voice_manager

    loop = native_call
    adapter = FakeRealtimeVoiceAdapter()
    monkeypatch.setattr(loop, "_resolve_direction", lambda: "outbound")
    await adapter.connect(model="gemini-3.8-live", instructions="Prepared instruction snapshot")
    adapter.pstn_prewarm_brain = loop._compiled_brain()
    adapter.pstn_prewarm_tools = []
    adapter.model = "gemini-3.8-live"
    adapter.voice = realtime_voice_config(loop.stack_override)["voice"]
    adapter.opening_generated_on_session = True
    adapter.close = AsyncMock()
    loop._injected_adapter = adapter
    loop._play_deferred_greeting = AsyncMock()
    loop._arm_pickup_fallback = Mock()
    monkeypatch.setattr(realtime_voice_manager, "get", lambda _: adapter)
    await loop.start_call(greeting_text="Hello, can we talk?", greeting_wire_frames=[b"\0" * 640], immediate_greeting=True)
    await asyncio.sleep(0)
    assert loop._adapter is adapter
    adapter.close.assert_not_awaited()
    loop._play_deferred_greeting.assert_awaited_once()
    loop._arm_pickup_fallback.assert_not_called()


@pytest.mark.asyncio
async def test_recording_download_uses_owned_account_and_sniffs_actual_container(native_call, monkeypatch):
    import httpx

    from server.call.audio_archive import audio_archive
    from server.routes import calls
    from server.services import vobiz_recordings
    from server.services.saas import voice_kyc_service
    from server.services.vobiz_client import vobiz_call_registry

    cid = native_call.call_id
    monkeypatch.setattr(calls, "_ENRICH_CALL_CACHE", {cid: {"call_id": cid, "has_recording": False}})
    assert not calls._enrich_call_list_item({"call_id": cid})["has_recording"]
    meta = call_ledger.read_meta(cid)
    meta["vobiz_call_uuid"] = "carrier-owned"
    call_ledger.write_meta(cid, meta)
    client = Mock(auth_id="owned-account")
    client._request = AsyncMock(return_value={"objects": [{"call_uuid": "carrier-owned", "recording_id": "recording-owned", "recording_format": "mp3", "recording_url": "https://media.vobiz.ai/recording.mp3"}]})
    client._headers.return_value = {"X-Auth-ID": "owned-account", "X-Auth-Token": "unit-test-token"}
    monkeypatch.setattr(voice_kyc_service, "vobiz_client_for_call", AsyncMock(return_value=client))
    monkeypatch.setattr(vobiz_call_registry, "get", lambda _: {})
    wav = b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 80
    async def respond(request):
        assert request.headers["X-Auth-ID"] == "owned-account"
        return httpx.Response(200, content=wav)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    assert await vobiz_recordings.retrieve_recording(cid)
    assert audio_archive.recording_source(cid) == "vobiz"
    assert audio_archive.file_for(cid, "mix").read_bytes() == wav
    assert audio_archive.file_for(cid, "mix").suffix == ".wav"
    assert calls._enrich_call_list_item({"call_id": cid})["has_recording"]
    assert calls._enrich_call_list_item({"call_id": cid})["recording_source"] == "vobiz"


@pytest.mark.asyncio
@pytest.mark.parametrize("preparation_fails", [False, True])
@pytest.mark.parametrize("composed", [False, True])
async def test_dial_prepares_opening_before_contacting_carrier(monkeypatch, preparation_fails, composed):
    from types import SimpleNamespace

    from server.brain.agent_service import agent_service
    from server.routes import dev_telephony
    from server.services.pstn_prewarm import pstn_prewarm_registry
    from server.services.saas import voice_kyc_service
    from server.services.vobiz_client import vobiz_call_registry, vobiz_stream_tokens

    order = []
    client = Mock()
    client.build_stream_ws_url.return_value = "wss://example.invalid/stream"
    async def prepare(*args, **kwargs):
        order.append("greeting_ready")
        if preparation_fails:
            raise TimeoutError("Greeting not ready")
    async def dial(**kwargs):
        order.append("carrier_dial")
        return {"request_uuid": "carrier-test"}
    client.create_outbound_call = AsyncMock(side_effect=dial)
    monkeypatch.setattr(pstn_prewarm_registry, "prepare", prepare)
    bind = AsyncMock()
    monkeypatch.setattr(pstn_prewarm_registry, "bind", bind)
    monkeypatch.setattr(agent_service, "get_agent", AsyncMock(return_value={}))
    monkeypatch.setattr(voice_kyc_service, "vobiz_client_for_number", AsyncMock(return_value=(client, "tenant")))
    monkeypatch.setattr(vobiz_call_registry, "upsert", Mock())
    monkeypatch.setattr(vobiz_call_registry, "alias", Mock())
    token_create = Mock(return_value="unit-test-token")
    monkeypatch.setattr(vobiz_stream_tokens, "create", token_create)
    stack_override = (
        {
            "pipeline": "composed_voice",
            "voice_flow": "composed_stages",
            "language": "te-IN",
            "llm": {"provider": "sarvam", "model": "test-model"},
        }
        if composed
        else {"llm": {"provider": "gemini", "model": "gemini-3.8-live"}}
    )
    monkeypatch.setattr(dev_telephony, "_outbound_pstn_context", lambda _: ("medium", "te-IN", stack_override, []))
    monkeypatch.setattr(dev_telephony, "_resolve_outbound_source_session", lambda _: ("isolated", False))
    monkeypatch.setattr(dev_telephony, "_billed_user_id_from_session", lambda _: None)
    monkeypatch.setattr(dev_telephony, "_record_dev_dial", Mock(return_value={}))
    monkeypatch.setattr(dev_telephony, "_mirror_dev_telephony", AsyncMock())
    body = dev_telephony.OutboundTestBody(agentId="test-agent", fromE164="+12025550123", toE164="+12025550181")
    session = SimpleNamespace(kind="app", tenant_id="00000000-0000-4000-8000-000000000001")
    result = await dev_telephony._outbound_vobiz(body, session)
    assert token_create.call_args.kwargs["prewarm_required"] is True
    if composed:
        assert token_create.call_args.kwargs["stack_override"]["pipeline"] == "composed_voice"
    if preparation_fails:
        assert result["ok"] is False
        assert result["code"] == "voice_preparation_failed"
        client.create_outbound_call.assert_not_awaited()
        return
    assert result["ok"] is True
    assert order == ["greeting_ready", "carrier_dial"]
    assert bind.await_args.args[0] == "vobiz"
    assert bind.await_args.args[2] == "carrier-test"


@pytest.mark.asyncio
async def test_vobiz_prepared_contact_snapshot_is_not_invalidated_at_answer(monkeypatch):
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.services import pstn_prewarm

    bundle = pstn_prewarm.PstnPrewarmBundle(
        provider="vobiz", external_id="owned-call", realtime_key="prepared-session",
        greeting_text="Hello Sam", agent_id="agent-owned",
        compiled_brain_text="Contact name: Sam", compiled_brain_checksum="personalized-checksum",
    )
    monkeypatch.setattr(pstn_prewarm.pstn_prewarm_registry, "take", AsyncMock(return_value=bundle))
    reload_brain = AsyncMock(return_value=("new-version", "Contact name: {{full_name}}", "published"))
    monkeypatch.setattr(call_lifecycle_service, "_lock_compiled_brain", reload_brain)
    destroy = AsyncMock()
    monkeypatch.setattr(pstn_prewarm, "_destroy_realtime", destroy)
    assert await pstn_prewarm.take_prewarm_for_answer("vobiz", "owned-call") is bundle
    assert bundle.realtime_key == "prepared-session"
    reload_brain.assert_not_awaited()
    destroy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline", ["realtime_voice", "composed_voice"])
async def test_connected_call_keeps_exact_prepared_brain_and_session(native_call, monkeypatch, pipeline):
    from types import SimpleNamespace

    from server.call import call_context
    from server.call.call_lifecycle_service import CallLifecycleService
    from server.call.call_store import call_store
    from server.realtime.voice_manager import realtime_voice_manager
    from server.services import test_studio_config
    from server.services.saas import billing_rates, billing_wallet_service, campaign_script

    service = CallLifecycleService()
    agent = {"agent_id": "prepared-agent", "tenant_id": "00000000-0000-4000-8000-000000000001", "languages": ["te-IN"]}
    stack_override = native_call.stack_override
    if pipeline == "composed_voice":
        stack_override = {
            "pipeline": "composed_voice",
            "voice_flow": "composed_stages",
            "language": "te-IN",
            "stt": {"provider": "sarvam", "model": "test-stt", "config": {}},
            "llm": {"provider": "sarvam", "model": "test-llm", "config": {}},
            "tts": {"provider": "sarvam", "model": "test-tts", "config": {}},
            "_voice_stack_snapshot": {
                "tier": "medium",
                "retailRate": {
                    "complete": True,
                    "usdMicrosPerMin": 10000,
                    "inrPaisePerMin": 955,
                    "fxRateInr": 95.5,
                    "version": 1,
                },
            },
        }
    stack = SimpleNamespace(tier="medium", combination_id="profile-test", llm=SimpleNamespace(model="gemini-3.8-live"), to_safe_dict=lambda: stack_override)
    monkeypatch.setattr(service, "_resolve_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(service, "_resolve_locked_stack", Mock(return_value=stack))
    monkeypatch.setattr(service, "_coerce_pipeline_stack", Mock(return_value=stack))
    lock = AsyncMock()
    monkeypatch.setattr(service, "_lock_compiled_brain", lock)
    monkeypatch.setattr(service, "_schedule_max_duration_watchdog", Mock())
    monkeypatch.setattr(test_studio_config, "saved_call_config", lambda _: {})
    monkeypatch.setattr(call_store, "insert", AsyncMock())
    monkeypatch.setattr(billing_rates, "load_current_rates", AsyncMock(return_value={}))
    monkeypatch.setattr(billing_wallet_service, "max_allowed_call_duration_sec", AsyncMock(return_value=900))
    campaign = AsyncMock()
    monkeypatch.setattr(campaign_script, "campaign_call_script", campaign)
    adopt = Mock(return_value=object())
    monkeypatch.setattr(realtime_voice_manager, "adopt_session", adopt)
    brain = "Exact Telugu prepared opening. Contact: Sam."
    result = await service.start(agent_id="prepared-agent", session_id=f"snapshot-regression-{pipeline}",
                                 channel="pstn", direction="outbound", stack_override=stack_override,
                                 realtime_prewarm_key="original-gemini-session", prepared_brain=("snapshot-v1", brain))
    try:
        meta = call_ledger.read_meta(result["call_id"])
        assert meta["compiled_brain_text"] == brain
        assert meta["brain_source"] == "dial_snapshot"
        assert call_context.get(result["call_id"]).compiled_brain_text == brain
        if pipeline == "realtime_voice":
            adopt.assert_called_once_with("original-gemini-session", result["call_id"])
        else:
            adopt.assert_not_called()
        lock.assert_not_awaited()
        campaign.assert_not_awaited()
    finally:
        call_context.clear_all()


def test_recording_disclosure_preparation_matches_connected_script():
    from server.call.call_lifecycle_service import apply_recording_disclosure

    agent = {"recording_disclosure_enabled": True}
    brain = "### OPENING\nHello\n--- SAFETY ---\nBe polite"
    prepared = apply_recording_disclosure(brain, agent, "te-IN")
    assert "### RECORDING DISCLOSURE POLICY" in prepared
    assert apply_recording_disclosure(prepared, agent, "te-IN") == prepared


@pytest.mark.asyncio
async def test_recording_worker_retries_provider_not_ready_without_duplicate_jobs(monkeypatch):
    import asyncio

    from server.services import vobiz_recordings
    from server.services.vobiz_client import VobizApiError

    retrieve = AsyncMock(side_effect=[VobizApiError("Not ready", status=404), True])
    monkeypatch.setattr(vobiz_recordings, "retrieve_recording", retrieve)
    monkeypatch.setattr(vobiz_recordings.asyncio, "sleep", AsyncMock())
    vobiz_recordings.schedule_recording_retrieval("retry-recording")
    task = vobiz_recordings._jobs["retry-recording"]
    vobiz_recordings.schedule_recording_retrieval("retry-recording")
    assert vobiz_recordings._jobs["retry-recording"] is task
    await task
    assert retrieve.await_count == 2
    await asyncio.sleep(0)
