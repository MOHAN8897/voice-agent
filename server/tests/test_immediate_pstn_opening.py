"""Immediate cached Vobiz opening and same-session Gemini conversation handoff."""
from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from server.call.call_ledger import call_ledger
from server.config.env import get_settings
from server.realtime.models import realtime_voice_config
from server.realtime.testing import FakeRealtimeVoiceAdapter
from server.realtime.voice_manager import RealtimeVoiceManager
from server.services import pstn_prewarm, vobiz_pstn_bridge
from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.fixture
async def prepared(monkeypatch, tmp_path):
    from server.realtime import voice_manager

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    call_ledger.reset_for_tests()
    manager = RealtimeVoiceManager(adapter_factory=FakeRealtimeVoiceAdapter)
    registry = pstn_prewarm.PstnPrewarmRegistry()
    monkeypatch.setattr(voice_manager, "realtime_voice_manager", manager)
    monkeypatch.setattr(pstn_prewarm, "pstn_prewarm_registry", registry)
    monkeypatch.setattr(registry, "_expire_if_unclaimed", AsyncMock())
    stack = {"pipeline": "realtime_voice", "language": "en-IN", "direction": "outbound",
             "llm": {"provider": "gemini", "model": "gemini-3.8-live"}}
    brain = "Prepared agent identity and personalized conversation."
    adapter = await manager.create("prepared-socket", compiled_brain=brain,
                                   instructions="Prepared instructions", model="gemini-3.8-live", stack_override=stack)
    adapter.pstn_prewarm_brain = brain
    adapter.pstn_prewarm_tools = []
    adapter.opening_generated_on_session = True
    adapter.opening_history_clean = False
    adapter.note_opening_delivered = AsyncMock(wraps=adapter.note_opening_delivered)
    bundle = pstn_prewarm.PstnPrewarmBundle(
        provider="vobiz", external_id="outbound-tracking", realtime_key="prepared-socket",
        agent_id="prepared-agent", compiled_brain_text=brain, compiled_brain_version="prepared-v1",
        greeting_text="Hello, this is the appointment assistant.", greeting_model="gemini-3.8-live",
        greeting_source="realtime_voice", greeting_wire_frames=[b"\0\1" * 320] * 3,
    )
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    registry._entries["vobiz:outbound-tracking"] = SimpleNamespace(
        provider="vobiz", external_id=bundle.external_id, realtime_key=bundle.realtime_key,
        task=done, bundle=bundle, created_at=time.monotonic(), error=None,
    )
    yield SimpleNamespace(manager=manager, registry=registry, adapter=adapter, bundle=bundle, stack=stack)
    for key in list(manager._sessions):
        await manager.destroy(key)
    call_ledger.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("fast_answer", [False, True])
async def test_distinct_tracking_request_and_answer_ids_reuse_one_prepared_session(prepared, fast_answer):
    if not fast_answer:
        await prepared.registry.bind("vobiz", "outbound-tracking", "provider-request")
    bundle = await pstn_prewarm.take_prewarm_for_answer(
        "vobiz", "answered-call", fallback_external_ids=("outbound-tracking", "provider-request"),
    )
    assert bundle is prepared.bundle
    if fast_answer:
        await prepared.registry.bind("vobiz", "outbound-tracking", "provider-request")
    assert not prepared.registry._entries
    assert prepared.manager.adopt_session(bundle.realtime_key, "conversation") is prepared.adapter
    assert prepared.adapter.is_open()
    assert not prepared.adapter.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("block_registry", [False, True])
@pytest.mark.parametrize(
    ("encoding", "sample_rate", "content_type", "frame_bytes"),
    [
        ("audio/x-l16", 16000, "audio/x-l16", 640),
        ("audio/x-mulaw", 8000, "audio/x-mulaw;rate=8000", 160),
        ("audio/x-alaw", 8000, "audio/x-alaw;rate=8000", 160),
    ],
)
async def test_first_audio_precedes_slow_lifecycle_and_same_adapter_handles_conversation(
    prepared, monkeypatch, block_registry, encoding, sample_rate, content_type, frame_bytes
):
    from server.call.call_lifecycle_service import call_lifecycle_service
    from server.services.runtime_settings import runtime_settings

    first_audio = asyncio.Event()
    lifecycle_entered = asyncio.Event()
    finish_lifecycle = asyncio.Event()
    finish_registry = threading.Event()
    if not block_registry:
        finish_registry.set()
    messages = []
    async def send(text):
        messages.append(json.loads(text))
        if messages[-1].get("event") == "playAudio":
            first_audio.set()
    ws = SimpleNamespace(send_text=AsyncMock(side_effect=send), close=AsyncMock())
    bridge = vobiz_pstn_bridge.VobizPstnBridge(ws)
    bridge.agent_id = "prepared-agent"
    bridge._token_meta = {"agent_id": bridge.agent_id, "call_uuid": "answered-call",
                          "outbound_id": "outbound-tracking", "request_uuid": "provider-request",
                          "direction": "outbound", "language": "en-IN", "prewarm_required": True,
                          "stack_override": prepared.stack}
    monkeypatch.setattr(vobiz_pstn_bridge.vobiz_call_registry, "get", lambda _: {})
    def update_registry(_call_id, values):
        if values.get("stream_connected"):
            assert finish_registry.wait(timeout=3)
    monkeypatch.setattr(vobiz_pstn_bridge.vobiz_call_registry, "upsert", update_registry)
    monkeypatch.setattr(vobiz_pstn_bridge.vobiz_call_registry, "alias", Mock())
    monkeypatch.setattr(runtime_settings, "get", lambda _: {})
    await call_ledger.init("internal-call", {"call_id": "internal-call", "channel": "pstn", "direction": "outbound"})
    async def start(**kwargs):
        lifecycle_entered.set()
        await finish_lifecycle.wait()
        assert kwargs["realtime_prewarm_key"] == "prepared-socket"
        assert prepared.manager.adopt_session(kwargs["realtime_prewarm_key"], "internal-call") is prepared.adapter
        return {"call_id": "internal-call", "session_id": "test-conversation"}
    monkeypatch.setattr(call_lifecycle_service, "start", start)
    monkeypatch.setattr(call_lifecycle_service, "end", AsyncMock())
    voices = []
    def voice_factory(**kwargs):
        voice = PstnRealtimeVoiceLoop(**kwargs)
        voice._compiled_brain = lambda: prepared.bundle.compiled_brain_text
        voice._wait_greeting_tail = AsyncMock()
        voices.append(voice)
        return voice
    monkeypatch.setattr(vobiz_pstn_bridge, "create_pstn_voice_loop", voice_factory)
    event = {"start": {"callId": "answered-call", "streamId": "stream-test",
                       "mediaFormat": {"encoding": encoding, "sampleRate": sample_rate}}}
    start_task = asyncio.create_task(bridge._on_start(event))
    try:
        await asyncio.wait_for(first_audio.wait(), timeout=1)
        if block_registry:
            assert not lifecycle_entered.is_set()
        finish_registry.set()
        await asyncio.wait_for(lifecycle_entered.wait(), timeout=1)
        assert not start_task.done()
        assert not voices
        audio_messages = [m for m in messages if m["event"] == "playAudio"]
        assert len(audio_messages) == 3
        for message in audio_messages:
            assert message["media"]["contentType"] == content_type
            assert len(base64.b64decode(message["media"]["payload"])) == frame_bytes
        finish_lifecycle.set()
        await asyncio.wait_for(start_task, timeout=2)
        await asyncio.wait_for(bridge._start_voice_task, timeout=2)
        await asyncio.wait_for(voices[0]._deferred_greeting_task, timeout=2)
        assert voices[0]._adapter is prepared.adapter
        assert prepared.adapter.voice == realtime_voice_config(prepared.stack)["voice"]
        assert not prepared.adapter.closed
        assert not voices[0]._deferred_greeting_armed
        prepared.adapter.note_opening_delivered.assert_awaited_once()
        # Neither a later hello nor a late pickup callback may replay the cache.
        await voices[0]._handle_event({"type": "user_transcript", "text": "Hello.", "final": True})
        await voices[0]._on_first_user_speech_deferred_greeting()
        await voices[0]._play_deferred_greeting()
        assert len([m for m in messages if m["event"] == "playAudio"]) == 3
    finally:
        finish_registry.set()
        finish_lifecycle.set()
        await asyncio.gather(start_task, return_exceptions=True)
        await bridge._cleanup("test_finished")


@pytest.mark.asyncio
async def test_duplicate_greeting_tasks_consume_buffer_once(prepared):
    sent = AsyncMock()
    voice = PstnRealtimeVoiceLoop(session_id="once", call_id=None, adapter=prepared.adapter,
                                  on_agent_wire=sent, stack_override=prepared.stack)
    voice._deferred_greeting_frames = list(prepared.bundle.greeting_wire_frames)
    voice._deferred_greeting_text = prepared.bundle.greeting_text
    voice._deferred_greeting_armed = True
    voice._wait_greeting_tail = AsyncMock()
    try:
        await asyncio.gather(voice._play_deferred_greeting(), voice._play_deferred_greeting())
        assert sent.await_count == 3
        assert voice._deferred_greeting_frames is None
        assert not voice._deferred_greeting_armed
        prepared.adapter.note_opening_delivered.assert_awaited_once()
        assert not prepared.adapter.noted_assistant
    finally:
        await voice.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["wrong_agent", "closed_session", "missing_bundle"])
async def test_invalid_prepared_session_never_sends_audio_or_starts_a_cold_session(prepared, monkeypatch, failure):
    from server.call.call_lifecycle_service import call_lifecycle_service

    ws = SimpleNamespace(send_text=AsyncMock(), close=AsyncMock())
    bridge = vobiz_pstn_bridge.VobizPstnBridge(ws)
    bridge.agent_id = "different-agent" if failure == "wrong_agent" else "prepared-agent"
    bridge._token_meta = {"direction": "outbound", "prewarm_required": True,
                          "outbound_id": "outbound-tracking"}
    monkeypatch.setattr(vobiz_pstn_bridge.vobiz_call_registry, "get", lambda _: {})
    monkeypatch.setattr(vobiz_pstn_bridge.vobiz_call_registry, "upsert", Mock())
    monkeypatch.setattr(vobiz_pstn_bridge.vobiz_call_registry, "alias", Mock())
    start = AsyncMock()
    monkeypatch.setattr(call_lifecycle_service, "start", start)
    if failure == "closed_session":
        await prepared.adapter.close()
    elif failure == "missing_bundle":
        prepared.registry._entries.clear()
    try:
        with pytest.raises(RuntimeError, match="Prepared"):
            await bridge._on_start({"start": {"callId": "answered-call", "streamId": "test-stream"}})
        ws.send_text.assert_not_awaited()
        start.assert_not_awaited()
    finally:
        await bridge._cleanup("failed_start")


@pytest.mark.asyncio
async def test_cleanup_cancels_early_playback_and_closes_unadopted_adapter(prepared, monkeypatch):
    bridge = vobiz_pstn_bridge.VobizPstnBridge(SimpleNamespace(close=AsyncMock()))
    bridge._prewarm_bundle = prepared.bundle
    task = asyncio.create_task(asyncio.sleep(60))
    bridge._early_greeting_task = task
    monkeypatch.setattr(vobiz_pstn_bridge.vobiz_call_registry, "upsert", Mock())
    await bridge._cleanup("cancelled_start")
    assert task.cancelled()
    assert prepared.adapter.closed
    assert prepared.manager.get("prepared-socket") is None


def test_runtime_prompt_records_the_prepared_opening_contract():
    from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
    from server.realtime.providers.gemini_voice import OPENING_ALREADY_DELIVERED_NOTE

    text = build_gemini_audio_session_instructions("Business facts", direction="outbound", language="te-IN")
    assert "before dialing" in text
    assert "plays its cached audio once" in text
    assert "only if the caller asks who is calling" in text
    assert "after the callee speaks" not in text
    assert "Do not restart the greeting" in OPENING_ALREADY_DELIVERED_NOTE
