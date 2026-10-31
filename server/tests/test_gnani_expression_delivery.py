"""Regression coverage for the admitted prompt through provider PCM delivery."""
import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server.call.live_turn_orchestrator import LiveTurnOrchestrator
from server.prompts.agent_voice_rules import spoken_pack_for
from server.providers.base import StageSelection
from server.services import gnani_tts_ws


@pytest.mark.asyncio
@pytest.mark.parametrize("model,expressive", [("timbre-v3.0", True), ("timbre-v2.5", False)])
async def test_final_native_speech_contract_matches_admitted_tts(monkeypatch, model, expressive):
    ctx = SimpleNamespace(resolved_stack=SimpleNamespace(tts=StageSelection("gnani", model, {})))
    monkeypatch.setattr("server.call.call_context.get", lambda _: ctx)
    observed = {}

    class Adapter:
        uses_plain_live_speech = True

        async def stream_live_turn(self, **kwargs):
            observed.update(kwargs)
            yield {"done": True, "text": "<excited> That is great news!"}

    events = [event async for event in LiveTurnOrchestrator()._stream_composed_speech(
        adapter=Adapter(), messages=[{"role": "developer", "content": "Approved business facts"}],
        schema=None, stream_kwargs={}, call_id="expression-test", provider="sarvam", model="test")]
    contract = observed["input_messages"][-1]["content"]
    assert ("inline audio tags from the selected" in contract) is expressive
    assert ("without inline audio tags" in contract) is not expressive
    assert events[-1]["response_contract"] == "speech_text"


@pytest.mark.parametrize("compact", [True, False])
def test_telugu_keeps_polite_grammar_without_honorific_filler_examples(compact):
    prompt = spoken_pack_for("te-IN", core_only=compact)
    assert "Do not add standalone అండి" in prompt
    assert "sure అండి" not in prompt
    assert "polite `-andi` markers" not in prompt
    assert "ఆ విషయం నాకు తెలియదు." in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["complete", "final_audio", "both"])
async def test_websocket_serializes_requests_and_keeps_final_audio(monkeypatch, terminal):
    incoming = asyncio.Queue()
    ws = SimpleNamespace(send=AsyncMock(), recv=incoming.get, close=AsyncMock())
    monkeypatch.setattr(gnani_tts_ws.websockets, "connect", AsyncMock(return_value=ws))
    monkeypatch.setattr(gnani_tts_ws, "_gnani_api_key", lambda: "synthetic-key")
    async with gnani_tts_ws.connect_gnani_tts_ws(model="timbre-v3.0") as proxy:
        await proxy.send(json.dumps({"type": "text", "data": {"text": "<excited> Good news!"}}))
        second = asyncio.create_task(proxy.send(json.dumps({"type": "text", "data": {"text": "Here are the details."}})))
        await asyncio.sleep(0)
        assert ws.send.await_count == 1
        pcm = b"\x01\x00" * 32
        if terminal in {"final_audio", "both"}:
            await incoming.put(json.dumps({"type": "audio", "data": {
                "audio": base64.b64encode(pcm).decode(), "is_final": True}}))
            audio = json.loads(await asyncio.wait_for(proxy.__anext__(), 1))
            assert base64.b64decode(audio["data"]["audio"]) == pcm
        if terminal in {"complete", "both"}:
            await incoming.put(json.dumps({"type": "complete"}))
        await asyncio.wait_for(second, 1)
        assert ws.send.await_count == 2
        assert "<excited>" in json.loads(ws.send.await_args_list[0].args[0])["text"]
        await incoming.put(json.dumps({"type": "complete"}))
        # Let the reader consume completion before flushing the turn.
        await asyncio.sleep(0)
        await proxy.send(json.dumps({"type": "flush"}))
        assert json.loads(await asyncio.wait_for(proxy.__anext__(), 1))["type"] == "end_of_stream"


@pytest.mark.asyncio
@pytest.mark.parametrize("fatal", [False, True])
async def test_provider_error_releases_waiting_synthesis(monkeypatch, fatal):
    incoming = asyncio.Queue()
    ws = SimpleNamespace(send=AsyncMock(), recv=incoming.get, close=AsyncMock())
    monkeypatch.setattr(gnani_tts_ws.websockets, "connect", AsyncMock(return_value=ws))
    monkeypatch.setattr(gnani_tts_ws, "_gnani_api_key", lambda: "synthetic-key")
    async with gnani_tts_ws.connect_gnani_tts_ws(model="timbre-v3.0") as proxy:
        payload = json.dumps({"type": "text", "data": {"text": "Approved details."}})
        await proxy.send(payload)
        second = asyncio.create_task(proxy.send(payload))
        await incoming.put(json.dumps({"type": "error", "message": "Synthesis unavailable", "fatal": fatal}))
        if fatal:
            with pytest.raises(RuntimeError, match="closed"):
                await asyncio.wait_for(second, 1)
            assert ws.send.await_count == 1
        else:
            await asyncio.wait_for(second, 1)
            assert ws.send.await_count == 2
        error = json.loads(await asyncio.wait_for(proxy.__anext__(), 1))
        assert error["recoverable"] is not fatal
