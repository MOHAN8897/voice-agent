"""Exercise provider wire protocols, ordered live delivery, teardown and accounting."""
import asyncio
import base64
import json
from unittest.mock import AsyncMock, Mock

import pytest

from server.services.live_caller_transcription import LiveCallerTranscriber
from server.services.transcription_policy import normalize_transcription_block
from server.services.usage_pricing import cost_live_transcribe


class Socket:
    def __init__(self, provider):
        self.provider = provider
        self.events = asyncio.Queue()
        self.sent = []
        self.audio_bytes = 0
        if provider == "sarvam":
            self.push({"event": "session.begin"})

    def push(self, event):
        self.events.put_nowait(json.dumps(event))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.recv()

    async def recv(self):
        return await self.events.get()

    async def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        kind = event.get("event", event.get("type"))
        if kind == "session.update":
            self.push({"type": "session.updated"})
        if "audio" in event:
            self.audio_bytes += len(base64.b64decode(event["audio"]))
        if kind == "end":
            self.push({"event": "transcript.final", "text": "రేపు call చేయండి", "start_s": 0, "end_s": 1})
            self.push({"event": "session.end", "audio_duration_s": 1.25})
        if kind == "input_audio_buffer.commit":
            self.push({"type": "input_audio_buffer.committed", "item_id": "tail"})
            self.push({"type": "conversation.item.input_audio_transcription.completed", "item_id": "tail", "transcript": "Call me tomorrow."})


async def eventually(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(.001)


@pytest.mark.parametrize("model", ["gpt-transcribe", "gpt-4o-mini-transcribe", "saaras:v3-realtime"])
async def test_real_provider_protocol_flushes_final_and_counts_sent_audio(monkeypatch, model):
    finals, states = [], []
    async def on_final(text): finals.append(text)
    async def on_state(status, partial): states.append((status, partial))
    stream = LiveCallerTranscriber(model=model, language="te-IN", input_rate=16000, on_final=on_final, on_state=on_state)
    socket = Socket(stream.provider)
    monkeypatch.setattr(stream, "_connect", lambda: socket)
    stream.start()
    await eventually(lambda: ("streaming", "") in states)
    for _ in range(50):
        stream.feed_pcm16(b"\x01\x00" * 320)  # one second at 16 kHz
    await eventually(lambda: socket.audio_bytes >= stream.rate * 2 - 8)
    await stream.close()
    assert stream._task.done()
    assert len(finals) == 1
    assert states[-1] == ("complete", "")
    assert stream.billed_audio_sec == pytest.approx(1.25 if stream.provider == "sarvam" else 1.0, abs=.001)
    if stream.provider == "openai":
        config = socket.sent[0]["session"]["audio"]["input"]
        assert config["transcription"]["model"] == model
        assert config["format"]["rate"] == 24000
        if model == "gpt-transcribe":
            assert config["transcription"]["languages"] == ["te", "en"]


async def test_openai_completions_retain_turn_order_and_deduplicate(monkeypatch):
    finals, states = [], []
    stream = LiveCallerTranscriber(model="gpt-transcribe", language="te-IN", input_rate=24000,
        on_final=AsyncMock(side_effect=finals.append), on_state=AsyncMock(side_effect=lambda s,p: states.append((s,p))))
    socket = Socket("openai")
    monkeypatch.setattr(stream, "_connect", lambda: socket)
    stream.start()
    await eventually(lambda: ("streaming", "") in states)
    for item in ("one", "two"):
        socket.push({"type": "input_audio_buffer.committed", "item_id": item})
    socket.push({"type": "conversation.item.input_audio_transcription.completed", "item_id": "two", "transcript": "Second"})
    socket.push({"type": "conversation.item.input_audio_transcription.completed", "item_id": "one", "transcript": "First"})
    socket.push({"type": "conversation.item.input_audio_transcription.completed", "item_id": "one", "transcript": "First"})
    await eventually(lambda: len(finals) == 2)
    assert finals == ["First", "Second"]
    await stream.close()


async def test_connection_rejection_is_visible_and_does_not_bill_unsent_audio(monkeypatch):
    states = []
    stream = LiveCallerTranscriber(model="gpt-transcribe", language="hi-IN", input_rate=16000,
        on_final=AsyncMock(), on_state=AsyncMock(side_effect=lambda s,p: states.append((s,p))))
    monkeypatch.setattr(stream, "_connect", Mock(side_effect=RuntimeError("sensitive provider error")))
    stream.feed_pcm16(b"\0\0" * 320)
    stream.start()
    await eventually(lambda: stream._task.done())
    assert states[-1] == ("failed", "")
    assert stream.billed_audio_sec == 0
    assert stream._queued_bytes == 0
    await stream.close()


async def test_audio_backpressure_is_bounded_and_no_silent_drop(monkeypatch):
    states = []
    stream = LiveCallerTranscriber(model="saaras:v3-realtime", language="te-IN", input_rate=16000,
        on_final=AsyncMock(), on_state=AsyncMock(side_effect=lambda s,p: states.append((s,p))))
    socket = Socket("sarvam")
    monkeypatch.setattr(stream, "_connect", lambda: socket)
    stream.start()
    await eventually(lambda: ("streaming", "") in states)
    stream.feed_pcm16(b"\0\0" * (16000 * 6))
    await eventually(lambda: stream._task.done())
    assert states[-1] == ("failed", "")
    assert stream._queued_bytes == 0


@pytest.mark.parametrize("model", ["gpt-transcribe", "saaras:v3-realtime"])
async def test_transport_close_without_final_ack_is_not_reported_complete(monkeypatch, model):
    states = []
    stream = LiveCallerTranscriber(model=model, language="te-IN", input_rate=16000,
        on_final=AsyncMock(), on_state=AsyncMock(side_effect=lambda s,p: states.append((s,p))))
    class TruncatedSocket(Socket):
        async def send(self, raw):
            kind = json.loads(raw).get("event", json.loads(raw).get("type"))
            if kind in {"end", "input_audio_buffer.commit"}:
                self.events.put_nowait(None)
            else:
                await super().send(raw)
        async def __anext__(self):
            event = await self.recv()
            if event is None:
                raise StopAsyncIteration
            return event
    socket = TruncatedSocket(stream.provider)
    monkeypatch.setattr(stream, "_connect", lambda: socket)
    stream.start()
    await eventually(lambda: ("streaming", "") in states)
    stream.feed_pcm16(b"\x01\0" * 8000)
    await eventually(lambda: socket.audio_bytes > 0)
    await stream.close()
    assert states[-1] == ("failed", "")


@pytest.mark.parametrize("model", ["gpt-transcribe", "saaras:v3-realtime", "gpt-4o-mini-transcribe", "gemini-native"])
def test_admin_normalization_preserves_selection(model):
    normalized = normalize_transcription_block({"live_enabled": True, "post_call_enabled": False, "live_model": model})
    assert normalized["live_model"] == model
    assert not normalized["post_call_enabled"]


def test_unsupported_model_is_not_silently_replaced():
    with pytest.raises(ValueError):
        normalize_transcription_block({"live_enabled": True, "live_model": "untrusted-model"})


@pytest.mark.parametrize("model", ["gpt-transcribe", "saaras:v3-realtime"])
def test_preflight_rejects_missing_selected_credentials(monkeypatch, model):
    from server.services import live_caller_transcription as module
    monkeypatch.setattr(module, "live_api_key", lambda _: "")
    with pytest.raises(ValueError, match="credentials"):
        module.validate_live_transcription({"llm": {"provider": "gemini", "model": "gemini-3.8-live"},
            "transcription": {"live_enabled": True, "live_model": model}})


@pytest.mark.parametrize("model", ["gpt-transcribe", "saaras:v3-realtime"])
async def test_admin_route_persists_recognizer_without_changing_voice_provider(monkeypatch, model):
    from types import SimpleNamespace

    from server.routes import dev_stack
    from server.services.saas import platform_phone_stack
    mirror, save = AsyncMock(return_value=True), Mock()
    monkeypatch.setattr(dev_stack, "require_permission", lambda *_: None)
    monkeypatch.setattr(platform_phone_stack, "mirror_universal_phone_stack_to_db", mirror)
    monkeypatch.setattr(platform_phone_stack, "save_universal_phone_stack_raw", save)
    monkeypatch.setattr(dev_stack, "_saas_phone_stack_credentials", dict)
    monkeypatch.setattr(dev_stack, "_saas_phone_stack_warnings", lambda _: [])
    result = await dev_stack.dev_stack_saas_phone_put(dev_stack.SaasPhoneStackBody(stackOverride={
        "pipeline": "realtime_voice", "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
        "transcription": {"live_enabled": True, "post_call_enabled": False, "live_model": model}}),
        SimpleNamespace(subject="isolated-admin"))
    assert result["resolved"]["transcription"]["live_model"] == model
    assert result["resolved"]["llm"]["provider"] == "gemini"
    assert result["databasePersisted"] is True
    assert mirror.await_args.args[0] == save.call_args.args[0]


@pytest.mark.parametrize("model,usd,inr", [("gpt-transcribe", .0045, .45), ("gpt-4o-mini-transcribe", .003, .30), ("saaras:v3-realtime", .005, .50), ("gemini-native", 0, 0)])
def test_cost_uses_selected_model_and_sent_audio_duration(model, usd, inr):
    cost = cost_live_transcribe(duration_sec=60, model=model, fx_rate_inr=100)
    assert cost["usd"] == pytest.approx(usd)
    assert cost["inr"] == pytest.approx(inr)


async def test_selected_service_writes_only_its_caller_text_and_safe_tenant_metadata(tmp_path, monkeypatch):
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
    from server.services.saas.call_redaction import redact_call_detail_for_tenant
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    loop = PstnRealtimeVoiceLoop(session_id="live-test", call_id=None, on_agent_wire=AsyncMock(),
        stack_override={"transcription": {"live_enabled": True, "live_model": "saaras:v3-realtime"}})
    loop.call_id = "live-tx-test"
    await call_ledger.init(loop.call_id, {"call_id": loop.call_id, "stack_override": loop.stack_override})
    loop._caller_stt = object()
    assert not loop._persist_user_turn_to_ledger()
    await loop._on_live_stt_state("streaming", "నమస్కారం")
    await loop._on_caller_stt_final("నమస్కారం, tomorrow appointment ఉందా?")
    meta = call_ledger.read_meta(loop.call_id)
    assert len(call_ledger.read_lines(loop.call_id)) == 1
    assert meta["live_transcription"]["model"] == "saaras:v3-realtime"
    safe = redact_call_detail_for_tenant(meta)["live_transcription"]
    assert safe["status"] == "streaming" and safe["segments"] == 1
    assert "provider" not in safe and "model" not in safe
    get_settings.cache_clear()


async def test_native_choice_and_failed_external_usage_remain_accurate(tmp_path, monkeypatch):
    from server.call.call_ledger import call_ledger
    from server.config.env import get_settings
    from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    for selected in ["gemini-native", "gpt-transcribe"]:
        stack = {"llm": {"provider": "gemini", "model": "gemini-3.8-live"},
                 "transcription": {"live_enabled": True, "post_call_enabled": False, "live_model": selected}}
        cid = "usage-" + selected
        await call_ledger.init(cid, {"call_id": cid, "channel": "pstn", "stack_override": stack})
        loop = PstnRealtimeVoiceLoop(session_id="usage", call_id=cid, on_agent_wire=AsyncMock(), stack_override=stack)
        loop._live_model = "gemini-3.8-live"
        await loop._finalize_live_transcript_usage(sidecar_sec=0)
        call_ledger.stamp_ended_usage(cid, reason="user_stop", duration_sec=60)
        meta = call_ledger.read_meta(cid)
        assert meta["usage"]["live_transcript_usd"] == 0
        if selected == "gemini-native":
            assert meta["live_transcription"]["status"] == "complete"
            assert meta["transcript_source"] == "gemini_live_native"
        else:
            assert meta["usage"]["live_transcript_seconds"] == 0
            assert meta["usage"]["live_transcript_metered"] is True
    get_settings.cache_clear()


@pytest.mark.parametrize("carrier_success", [True, False])
async def test_only_confirmed_carrier_hangup_releases_admission(monkeypatch, carrier_success):
    from server.services.vobiz_pstn_bridge import VobizPstnBridge
    bridge = VobizPstnBridge(Mock(close=AsyncMock()))
    bridge.call_uuid = "aaaaaaaa-0000-4000-8000-000000006019"
    bridge._token_meta = {"admission_tenant_id": "aaaaaaaa-0000-4000-8000-000000006001", "admission_key": "isolated"}
    client = Mock(hangup_call=AsyncMock(return_value={}, side_effect=None if carrier_success else TimeoutError()))
    monkeypatch.setattr("server.services.vobiz_client.vobiz_call_registry.get", lambda _: {})
    monkeypatch.setattr("server.services.vobiz_client.vobiz_enabled", lambda: True)
    monkeypatch.setattr("server.services.saas.voice_kyc_service.vobiz_client_for_call", AsyncMock(return_value=client))
    event = AsyncMock()
    monkeypatch.setattr("server.services.saas.call_admission.provider_event", event)
    await bridge.hangup()
    assert event.await_count == int(carrier_success)
    if carrier_success:
        assert event.await_args.kwargs["key"] == "isolated"
        assert event.await_args.kwargs["status"] == "ended"
