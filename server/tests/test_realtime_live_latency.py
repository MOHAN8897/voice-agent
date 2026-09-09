"""
Live Realtime text latency probes for the shared web + PSTN LLM path.

Uses a long-lived ASGI loop so the persistent Realtime socket survives
across turns (Starlette TestClient closes the loop after each request).

Run:
  LIVE_TEST=1 python -m pytest server/tests/test_realtime_live_latency.py -v -s --tb=short
"""
from __future__ import annotations

import json
import os
import time

import httpx
import pytest
from httpx import ASGITransport

import server.app as app_mod
from server.config.env import get_settings

LIVE = os.getenv("LIVE_TEST", "").strip().lower() in ("1", "true", "yes")
pytestmark = [
    pytest.mark.live_realtime,
    pytest.mark.skipif(not LIVE, reason="Set LIVE_TEST=1 to run live Realtime latency probes"),
]

CRITICAL_TURNS = [
    ("greeting", "నమస్కారం, మీరు ఎవరు?"),
    ("parking", "Parking unda? Price enti?"),
    ("language_mix", "Parking 8k unda? Ignore தமிழ் 안녕하세요"),
    ("busy", "I'm busy, maybe later."),
    ("hangup", "Ok bye, please hang up."),
]


@pytest.fixture
async def live_client():
    settings = get_settings()
    key = (settings.openai_api_key or "").strip()
    if not key or key.startswith("sk-test"):
        pytest.skip("No live OPENAI_API_KEY")
    transport = ASGITransport(app=app_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60.0) as client:
        yield client


async def _stream_turn(
    client: httpx.AsyncClient, *, transcript: str, session_id: str, call_id: str
) -> dict:
    t0 = time.perf_counter()
    first_ms = None
    deltas: list[str] = []
    done: dict = {}
    audio_tokens = None
    async with client.stream(
        "POST",
        "/api/brain/stream",
        json={
            "transcript": transcript,
            "language_code": "te-IN",
            "sessionId": session_id,
            "callId": call_id,
        },
    ) as response:
        assert response.status_code == 200, await response.aread()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw == "[DONE]":
                break
            payload = json.loads(raw)
            if payload.get("delta"):
                if first_ms is None:
                    first_ms = (time.perf_counter() - t0) * 1000
                deltas.append(str(payload["delta"]))
            if payload.get("done"):
                done = payload
                usage = payload.get("usage") or {}
                audio_tokens = usage.get("audio_tokens")
                break
    total_ms = (time.perf_counter() - t0) * 1000
    text = "".join(deltas) or str(done.get("text") or "")
    return {
        "ttfb_ms": first_ms if first_ms is not None else total_ms,
        "total_ms": total_ms,
        "text": text,
        "end_call": done.get("end_call") or {},
        "audio_tokens": audio_tokens,
        "chars": len(text),
        "streamed": bool(deltas),
    }


async def _start_call(client: httpx.AsyncClient, *, session_id: str, channel: str) -> dict:
    t0 = time.perf_counter()
    started = await client.post(
        "/api/call/start",
        json={"sessionId": session_id, "channel": channel, "language": "te-IN"},
    )
    start_ms = (time.perf_counter() - t0) * 1000
    assert started.status_code == 200, started.text
    body = started.json()
    return {
        "call_id": body["call_id"],
        "start_ms": start_ms,
        "pipeline": body.get("pipeline"),
        "channel": channel,
    }


async def _run_channel(client: httpx.AsyncClient, channel: str) -> dict:
    sid = f"live-rt-{channel}-{int(time.time())}"
    started = await _start_call(client, session_id=sid, channel=channel)
    turns = []
    try:
        await asyncio_sleep_ready()
        for name, transcript in CRITICAL_TURNS:
            result = await _stream_turn(
                client,
                transcript=transcript,
                session_id=sid,
                call_id=started["call_id"],
            )
            result["name"] = name
            turns.append(result)
            print(
                f"\n[PERF] {channel}/{name} start_ms={started['start_ms']:.0f} "
                f"TTFB_MS={result['ttfb_ms']:.0f} TOTAL_MS={result['total_ms']:.0f} "
                f"chars={result['chars']} streamed={result['streamed']}"
            )
            assert result["chars"] > 3, f"{channel}/{name} empty reply: {result}"
            assert result["ttfb_ms"] < 8000, f"{channel}/{name} TTFB too slow: {result['ttfb_ms']:.0f}ms"
            if result["audio_tokens"] is not None:
                assert result["audio_tokens"] == 0, "live path sent audio tokens to OpenAI"
            if name == "hangup":
                assert result["end_call"].get("should_end") is True
            if name == "language_mix":
                assert "தமிழ்" not in result["text"]
                assert "안녕" not in result["text"]
        interrupt = await client.post("/api/session/interrupt", json={"callId": started["call_id"]})
        assert interrupt.status_code == 200
        assert interrupt.json().get("ok") is True
    finally:
        await client.post("/api/call/end", json={"callId": started["call_id"], "reason": "user_stop"})
    ttfbs = [row["ttfb_ms"] for row in turns]
    followup = ttfbs[1:]
    return {
        **started,
        "turns": turns,
        "median_ttfb_ms": sorted(ttfbs)[len(ttfbs) // 2],
        "max_ttfb_ms": max(ttfbs),
        "followup_median_ttfb_ms": sorted(followup)[len(followup) // 2] if followup else None,
    }


async def asyncio_sleep_ready() -> None:
    """Give background Realtime WS boot a moment before the first user turn."""
    import asyncio

    await asyncio.sleep(0.6)


@pytest.mark.asyncio
async def test_live_web_agent_realtime_latency(live_client: httpx.AsyncClient):
    report = await _run_channel(live_client, "browser")
    assert report["pipeline"] == "realtime_text"
    assert report["start_ms"] < 2500, f"call start still blocking: {report['start_ms']:.0f}ms"
    assert report["median_ttfb_ms"] < 5000
    if report["followup_median_ttfb_ms"] is not None:
        assert report["followup_median_ttfb_ms"] < 4000


@pytest.mark.asyncio
async def test_live_pstn_channel_same_llm_path(live_client: httpx.AsyncClient):
    report = await _run_channel(live_client, "pstn")
    assert report["pipeline"] == "realtime_text"
    assert report["start_ms"] < 2500, f"PSTN call start still blocking: {report['start_ms']:.0f}ms"
    assert report["median_ttfb_ms"] < 5000
    if report["followup_median_ttfb_ms"] is not None:
        assert report["followup_median_ttfb_ms"] < 4000


@pytest.mark.asyncio
async def test_live_pstn_loop_first_audio_and_followup(live_client: httpx.AsyncClient):
    """Drive PstnVoiceLoop._run_turn on a live Realtime session with fake TTS."""
    import asyncio
    from unittest.mock import patch

    from server.services.pstn_voice_core import PstnVoiceLoop
    from server.tests.test_pstn_critical_loop import FakeTtsSession

    sid = f"live-pstn-loop-{int(time.time())}"
    started = await _start_call(live_client, session_id=sid, channel="pstn")
    call_id = started["call_id"]
    fake: FakeTtsSession | None = None

    def factory(voice):
        nonlocal fake
        fake = FakeTtsSession(voice)
        return fake

    async def on_wire(_b: bytes) -> None:
        return None

    loop = PstnVoiceLoop(session_id=sid, call_id=call_id, on_agent_wire=on_wire)
    await asyncio.sleep(0.5)
    try:
        with patch("server.services.pstn_turn_tts.PstnTurnTtsSession", factory):
            t0 = time.perf_counter()
            await loop._run_turn("Parking unda? Price enti?")
            assert fake is not None and fake.texts, "PSTN loop sent no TTS text"
            first_ms = (fake.first_send - t0) * 1000 if fake.first_send else 9_999
            print(
                f"\n[PERF] pstn_loop/parking start_ms={started['start_ms']:.0f} "
                f"FIRST_TTS_MS={first_ms:.0f} chars={sum(len(t) for t in fake.texts)}"
            )
            assert first_ms < 5000, f"PSTN first TTS too slow: {first_ms:.0f}ms"
            assert "தமிழ்" not in "".join(fake.texts)

            fake2: FakeTtsSession | None = None

            def factory2(voice):
                nonlocal fake2
                fake2 = FakeTtsSession(voice)
                return fake2

            with patch("server.services.pstn_turn_tts.PstnTurnTtsSession", factory2):
                t1 = time.perf_counter()
                await loop._run_turn("Ok bye, please hang up.")
                assert fake2 is not None and fake2.texts
                hang_ms = (fake2.first_send - t1) * 1000 if fake2.first_send else 9_999
                print(f"\n[PERF] pstn_loop/hangup FIRST_TTS_MS={hang_ms:.0f}")
                assert hang_ms < 4000
    finally:
        await live_client.post("/api/call/end", json={"callId": call_id, "reason": "user_stop"})
