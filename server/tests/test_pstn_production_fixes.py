"""Production PSTN reliability fixes — streaming, STT gate, barge, generation."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.routes import telnyx as telnyx_routes
from server.services.pstn_turn_tts import PstnTurnTtsSession
from server.services.pstn_voice_core import (
    PHASE_SPEAKING,
    PHASE_THINKING,
    PstnVoiceLoop,
)
from server.services.telnyx_client import TelnyxCallRegistry, TelnyxStreamTokens, telnyx_call_registry


@pytest.fixture(autouse=True)
def _isolate_registry(monkeypatch):
    reg = TelnyxCallRegistry()
    monkeypatch.setattr(telnyx_routes, "telnyx_call_registry", reg)
    monkeypatch.setattr("server.services.telnyx_client.telnyx_call_registry", reg)
    # Fresh stream locks per test
    telnyx_routes._stream_op_locks.clear()
    return reg


@pytest.mark.asyncio
async def test_stream_url_configured_still_starts_on_answered(_isolate_registry):
    """TEST 1: dial-time stream_url must NOT skip ensure — start_streaming still runs."""
    reg = _isolate_registry
    cid = "cc-answer-1"
    reg.upsert(
        cid,
        {
            "stream_url": "wss://example/ws/telnyx-stream?token=abc",
            "stream_configured": True,
            "stream_started": False,
            "stream_connected": False,
        },
    )
    client = MagicMock()
    client.start_streaming = AsyncMock(return_value={})
    client.build_stream_ws_url = MagicMock(return_value="wss://example/ws")

    with patch.object(telnyx_routes, "TelnyxClient", return_value=client):
        await telnyx_routes._ensure_telnyx_streaming(cid, reason="answered")

    client.start_streaming.assert_awaited()
    row = reg.get(cid) or {}
    assert row.get("stream_start_requested") is True
    assert row.get("stream_api_ok") is True
    # Connected only after streaming.started / WS start — not after API alone.
    assert row.get("stream_connected") is not True


@pytest.mark.asyncio
async def test_streaming_failed_bounded_retry_no_duplicate(_isolate_registry):
    """TEST 2: streaming.failed retries bounded; concurrent ensures serialize."""
    reg = _isolate_registry
    cid = "cc-fail-1"
    reg.upsert(cid, {"stream_url": "wss://example/ws", "stream_connected": False})

    calls = {"n": 0}

    async def _fail(*_a, **_k):
        calls["n"] += 1
        from server.services.telnyx_client import TelnyxApiError

        raise TelnyxApiError("boom", status=500)

    client = MagicMock()
    client.start_streaming = AsyncMock(side_effect=_fail)
    client.build_stream_ws_url = MagicMock(return_value="wss://example/ws")

    with patch.object(telnyx_routes, "TelnyxClient", return_value=client):
        with patch.object(telnyx_routes.asyncio, "sleep", new=AsyncMock()):
            await telnyx_routes._ensure_telnyx_streaming(cid, reason="streaming_failed")
            # Second failure path increments retry and eventually terminals
            await telnyx_routes._ensure_telnyx_streaming(cid, reason="streaming_failed")
            await telnyx_routes._ensure_telnyx_streaming(cid, reason="streaming_failed")
            await telnyx_routes._ensure_telnyx_streaming(cid, reason="streaming_failed")

    row = reg.get(cid) or {}
    assert row.get("stream_failed") is True
    assert int(row.get("stream_retry_count") or 0) >= 1
    # 3 attempts per ensure × up to 3 failure retries, but terminal stops early
    assert calls["n"] <= 9
    assert calls["n"] >= 3


@pytest.mark.asyncio
async def test_quiet_caller_audio_forwarded_during_tts():
    """TEST 3: agent speaking + quiet 'yes' still reaches STT."""
    sent = []

    class _Stt:
        async def send(self, payload):
            sent.append(payload)

    loop = PstnVoiceLoop(session_id="s", call_id="c1", on_agent_wire=AsyncMock())
    loop._stt = _Stt()
    loop._tts_active = True
    loop._phase = PHASE_SPEAKING
    loop._set_tts_active(True)

    # Very quiet PCM16 frame (near-zero samples)
    pcm = b"\x01\x00" * 160
    with patch("server.services.audio_transcode.pcm16_rms", return_value=50):
        await loop.feed_user_pcm16(pcm)

    assert len(sent) == 1
    assert "audio_input" in sent[0]


@pytest.mark.asyncio
async def test_barge_actually_no_stops_tts():
    """TEST 4: 'actually no' commits barge and interrupts TTS."""
    loop = PstnVoiceLoop(session_id="s", call_id="c1", on_agent_wire=AsyncMock())
    loop.current_generation_id = "g1"
    loop._tts_active = True
    loop._phase = PHASE_SPEAKING
    loop._tts_started_at = __import__("time").monotonic() - 1.0
    loop._partial_started_at = __import__("time").monotonic() - 1.0
    loop._tts_heard_text = "Your villa is available"
    loop._last_tts_text = loop._tts_heard_text

    interrupted = {"ok": False}

    async def _fake_interrupt(**_k):
        interrupted["ok"] = True
        loop._interrupted_generation = "g1"

    loop.interrupt_tts = _fake_interrupt  # type: ignore[method-assign]
    assert loop._should_commit_barge("actually no")
    await loop._commit_barge("actually no")
    assert interrupted["ok"]
    assert loop._awaiting_barge_final is True
    assert loop._last_barge_partial == "actually no"


@pytest.mark.asyncio
async def test_barge_partial_timeout_promotes_fallback():
    """TEST 5: partial barge + timeout → fallback transcript usable."""
    loop = PstnVoiceLoop(session_id="s", call_id="c1", on_agent_wire=AsyncMock())
    loop._awaiting_barge_final = True
    loop._awaiting_barge_final_at = __import__("time").monotonic() - 10.0
    loop._last_barge_partial = "Actually I want to book"
    loop._phase = "interrupting"
    launched = []

    def _launch(text):
        launched.append(text)

    loop._launch_turn = _launch  # type: ignore[method-assign]

    # Drive timeout path via a tiny fake STT reader iteration
    class _FakeStt:
        def __aiter__(self):
            return self

        async def __anext__(self):
            # One empty/error-free cycle then stop
            if getattr(self, "_done", False):
                raise StopAsyncIteration
            self._done = True
            return '{"event":"ping"}'

    loop._stt = _FakeStt()
    await loop._stt_reader()
    assert launched
    assert "Actually I want" in launched[0]


def test_generated_tts_not_treated_as_heard():
    """TEST 6: queued/generated text is not heard until emit."""
    loop = PstnVoiceLoop(session_id="s", call_id="c1", on_agent_wire=AsyncMock())
    loop.current_generation_id = "g1"
    loop._tts_generated_text = "Your villa is available for eighty lakhs."
    loop._tts_queued_text = loop._tts_generated_text
    loop._tts_heard_text = ""
    loop._last_tts_text = ""
    # Echo against heard (empty) must not match generated sentence as heard echo source
    assert loop._tts_heard_text == ""
    assert "villa" in loop._tts_generated_text
    # Promote only on emit
    loop._promote_queued_tts_to_heard()
    assert "villa" in loop._tts_heard_text
    assert loop._last_tts_text == loop._tts_heard_text


@pytest.mark.asyncio
async def test_interrupted_tts_does_not_flush_stale_tail():
    """TEST 7: interrupted TTS never flushes stale audio."""
    emitted = []

    async def _wire(b: bytes):
        emitted.append(b)

    voice = PstnVoiceLoop(session_id="s", call_id="c1", on_agent_wire=_wire)
    voice.current_generation_id = "g1"
    session = PstnTurnTtsSession.__new__(PstnTurnTtsSession)
    session._voice = voice
    session._interrupted = True
    session._bound_generation = "g1"
    session._audio_buf = bytearray(b"\x00" * 80)
    session._use_mulaw_wire = False
    session._use_mp3 = False
    session._pcm_resampler = None
    await session._flush_audio_tail()
    assert emitted == []
    assert len(session._audio_buf) == 0


@pytest.mark.asyncio
async def test_stale_generation_drops_late_chunk():
    """TEST 8: old generation late TTS chunk is dropped."""
    emitted = []

    async def _wire(b: bytes):
        emitted.append(b)

    voice = PstnVoiceLoop(session_id="s", call_id="c1", on_agent_wire=_wire)
    voice.current_generation_id = "g-new"
    session = PstnTurnTtsSession.__new__(PstnTurnTtsSession)
    session._voice = voice
    session._interrupted = False
    session._bound_generation = "g-old"
    session._use_mulaw_wire = False
    session._use_mp3 = False
    session._first_chunk = False
    session._tts_rate = 8000
    session._frame_bytes = 320
    session._audio_buf = bytearray()
    session._pcm_resampler = None
    await session._emit_audio_chunk(b"\x00" * 320)
    assert emitted == []


@pytest.mark.asyncio
async def test_voice_busy_released_before_background(monkeypatch):
    """TEST 9: _turn_busy clears so next turn is not blocked by post work."""
    loop = PstnVoiceLoop(session_id="s", call_id="c-busy", on_agent_wire=AsyncMock())
    loop._turn_busy = False

    async def _fake_stream(**_kwargs):
        yield {"delta": "Hello there friend. "}
        yield {"done": True, "text": "Hello there friend.", "end_call": {}}

    class _Tts:
        has_sent_text = True
        had_error = False
        audio_emitted = True

        async def open(self, **_k):
            return None

        async def send_text(self, _t):
            return None

        async def finish(self):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(
        "server.call.live_turn_orchestrator.live_turn_orchestrator.handle_user_turn_stream",
        _fake_stream,
    )
    monkeypatch.setattr("server.services.pstn_turn_tts.PstnTurnTtsSession", lambda voice: _Tts())
    monkeypatch.setattr(loop, "_send_tts_text", AsyncMock())
    monkeypatch.setattr(loop, "_resolve_language", lambda: "en-IN")

    await loop._run_turn("hello")
    assert loop._turn_busy is False


def test_short_telugu_think_cancel():
    """TEST 10: short Telugu interruption can cancel thinking."""
    loop = PstnVoiceLoop(session_id="s", call_id="c1", on_agent_wire=AsyncMock())
    loop._phase = PHASE_THINKING
    loop._tts_active = False
    # First call arms hold timer
    assert loop._should_think_cancel("కాదు") is False
    assert loop._think_partial_started_at > 0
    loop._think_partial_started_at = __import__("time").monotonic() - 1.0
    assert loop._should_think_cancel("కాదు") is True


def test_multi_worker_stream_token_redis_roundtrip(monkeypatch):
    """TEST 11: stream token metadata recoverable via shared store simulation."""
    store: dict[str, str] = {}

    class _FakeRedis:
        def setex(self, key, _ttl, value):
            store[key] = value

        def get(self, key):
            return store.get(key)

        def delete(self, key):
            store.pop(key, None)

    tokens_a = TelnyxStreamTokens()
    tokens_b = TelnyxStreamTokens()
    monkeypatch.setattr(tokens_a, "_redis", lambda: _FakeRedis())
    monkeypatch.setattr(tokens_b, "_redis", lambda: _FakeRedis())

    tok = tokens_a.create(agent_id="agent-1", tier="gold", call_control_id="cc-9")
    # Simulate other worker with empty process memory
    tokens_b._tokens.clear()
    meta = tokens_b.peek(tok)
    assert meta is not None
    assert meta.get("agent_id") == "agent-1"
    assert meta.get("call_control_id") == "cc-9"


def test_emission_blocked_without_generation():
    loop = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    assert loop.emission_blocked() is True
    loop.current_generation_id = "gen-a"
    assert loop.emission_blocked() is False
    loop._interrupted_generation = "gen-a"
    assert loop.emission_blocked() is True


@pytest.mark.asyncio
async def test_ensure_skips_when_already_connected(_isolate_registry):
    reg = _isolate_registry
    cid = "cc-ok"
    reg.upsert(cid, {"stream_connected": True, "stream_url": "wss://x"})
    client = MagicMock()
    client.start_streaming = AsyncMock()
    with patch.object(telnyx_routes, "TelnyxClient", return_value=client):
        await telnyx_routes._ensure_telnyx_streaming(cid, reason="answered")
    client.start_streaming.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_skips_after_hangup(_isolate_registry):
    reg = _isolate_registry
    cid = "cc-ended"
    reg.upsert(cid, {"stream_url": "wss://x", "ended": True, "hangup_cause": "timeout"})
    client = MagicMock()
    client.start_streaming = AsyncMock()
    with patch.object(telnyx_routes, "TelnyxClient", return_value=client):
        await telnyx_routes._ensure_telnyx_streaming(cid, reason="streaming_failed")
    client.start_streaming.assert_not_awaited()


@pytest.mark.asyncio
async def test_streaming_stopped_unanswered_does_not_retry(_isolate_registry):
    """Unanswered dial → streaming.stopped must not call streaming_start (avoids 422)."""
    from starlette.requests import Request

    reg = _isolate_registry
    cid = "cc-timeout-1"
    reg.upsert(cid, {"stream_url": "wss://x", "stream_configured": True})

    body = {
        "data": {
            "event_type": "streaming.stopped",
            "payload": {
                "call_control_id": cid,
                "stream_url": "wss://x",
                "reason": "streaming.stopped",
            },
        }
    }
    raw = __import__("json").dumps(body).encode()

    scope = {"type": "http", "method": "POST", "headers": [], "path": "/api/telnyx/webhook"}

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    request = Request(scope, receive)
    client = MagicMock()
    client.start_streaming = AsyncMock()

    with patch.object(telnyx_routes, "TelnyxClient", return_value=client):
        with patch.object(
            telnyx_routes,
            "parse_verified_webhook_json",
            return_value=body,
        ):
            with patch.object(telnyx_routes, "get_settings") as gs:
                gs.return_value.app_environment = "development"
                gs.return_value.telnyx_public_key = ""
                await telnyx_routes.telnyx_webhook(request)

    client.start_streaming.assert_not_awaited()
    row = reg.get(cid) or {}
    assert row.get("stream_state") in {"stopped", "failed", "unknown"} or row.get("stream_failed") is False


@pytest.mark.asyncio
async def test_ensure_retries_transport_errors(_isolate_registry):
    """httpx transport blips must retry — not crash the ensure path before stream_failed."""
    reg = _isolate_registry
    cid = "cc-transport-1"
    reg.upsert(cid, {"stream_url": "wss://example/ws", "stream_connected": False})

    calls = {"n": 0}

    async def _flaky(*_a, **_k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("ReadError simulated")
        return {}

    client = MagicMock()
    client.start_streaming = AsyncMock(side_effect=_flaky)
    client.build_stream_ws_url = MagicMock(return_value="wss://example/ws")

    with patch.object(telnyx_routes, "TelnyxClient", return_value=client):
        with patch.object(telnyx_routes.asyncio, "sleep", new=AsyncMock()):
            await telnyx_routes._ensure_telnyx_streaming(cid, reason="answered")

    assert calls["n"] == 3
    row = reg.get(cid) or {}
    assert row.get("stream_api_ok") is True
    assert row.get("stream_state") == "api_ok_awaiting_connect"


@pytest.mark.asyncio
async def test_answered_recording_is_separate_from_stream_start(monkeypatch):
    called = {}

    async def _fake_start(cid):
        called["cid"] = cid

    monkeypatch.setattr("server.services.telnyx_recordings.start_call_recording", _fake_start)
    await telnyx_routes._start_answered_recording("cc-record-1")
    assert called["cid"] == "cc-record-1"


@pytest.mark.asyncio
async def test_telnyx_request_wraps_httpx_timeout(monkeypatch):
    """TelnyxClient._request maps transport timeouts to TelnyxApiError for retry loops."""
    import httpx
    from server.services.telnyx_client import TelnyxApiError, TelnyxClient

    class _BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, *a, **k):
            raise httpx.ConnectTimeout("connect timed out")

    monkeypatch.setattr(httpx, "AsyncClient", _BoomClient)
    client = TelnyxClient(cfg={"api_key": "k", "phone_number": "+10000000000", "connection_id": "c"})
    with pytest.raises(TelnyxApiError) as ei:
        await client._request("GET", "/balance")
    assert ei.value.status is None
    assert "timeout" in str(ei.value).lower()
