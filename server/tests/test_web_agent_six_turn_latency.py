"""
Live web-agent latency: connect, 6-turn average, barge-in, vs classic HTTP.

Run:
  LIVE_TEST=1 python -m pytest server/tests/test_web_agent_six_turn_latency.py -v -s --tb=short
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import time

import httpx
import pytest
from httpx import ASGITransport

import server.app as app_mod
from server.config.env import get_settings

LIVE = os.getenv("LIVE_TEST", "").strip().lower() in ("1", "true", "yes")
pytestmark = [
    pytest.mark.live_realtime,
    pytest.mark.skipif(not LIVE, reason="Set LIVE_TEST=1 to run live web-agent latency"),
]

SIX_TURNS = [
    ("t1_hello", "నమస్కారం"),
    ("t2_who", "మీరు ఎవరు? ఏం సంస్థ?"),
    ("t3_parking", "Parking unda?"),
    ("t4_price", "Price enti monthly?"),
    ("t5_hours", "What time do you close?"),
    ("t6_details", "Sare thanks. Inka details WhatsApp lo pampagala?"),
]


@pytest.fixture
async def live_client():
    settings = get_settings()
    key = (settings.openai_api_key or "").strip()
    if not key or key.startswith("sk-test"):
        pytest.skip("No live OPENAI_API_KEY")
    transport = ASGITransport(app=app_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=90.0) as client:
        yield client


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _print_turns(title: str, start_ms: float, ready_ms: float | None, turns: list[dict]) -> None:
    print(f"\n======== {title} ========")
    print(f"call_start_ms={start_ms:.0f}" + (f" realtime_ready_ms={ready_ms:.0f}" if ready_ms is not None else ""))
    print(f"{'turn':<14} {'ttfb_ms':>8} {'total_ms':>9} {'chars':>6} streamed")
    for row in turns:
        print(
            f"{row['name']:<14} {row['ttfb_ms']:8.0f} {row['total_ms']:9.0f} {row['chars']:6d} {row['streamed']}"
        )
    ttfbs = [r["ttfb_ms"] for r in turns]
    totals = [r["total_ms"] for r in turns]
    print(
        f"AVG ttfb={_avg(ttfbs):.0f}ms  AVG total={_avg(totals):.0f}ms  "
        f"median ttfb={statistics.median(ttfbs):.0f}ms  followup_avg_ttfb={_avg(ttfbs[1:]):.0f}ms"
    )


async def _stream_turn(
    client: httpx.AsyncClient,
    *,
    transcript: str,
    session_id: str,
    call_id: str,
) -> dict:
    t0 = time.perf_counter()
    first_ms = None
    deltas: list[str] = []
    done: dict = {}
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
                break
    total_ms = (time.perf_counter() - t0) * 1000
    text = "".join(deltas) or str(done.get("text") or "")
    return {
        "ttfb_ms": first_ms if first_ms is not None else total_ms,
        "total_ms": total_ms,
        "text": text,
        "chars": len(text),
        "streamed": bool(deltas),
        "end_call": done.get("end_call") or {},
        "audio_tokens": (done.get("usage") or {}).get("audio_tokens"),
    }


async def _start_call(
    client: httpx.AsyncClient,
    *,
    session_id: str,
    stack_override: dict | None = None,
) -> dict:
    t0 = time.perf_counter()
    body: dict = {"sessionId": session_id, "channel": "browser", "language": "te-IN"}
    if stack_override:
        body["stackOverride"] = stack_override
    started = await client.post("/api/call/start", json=body)
    start_ms = (time.perf_counter() - t0) * 1000
    assert started.status_code == 200, started.text
    payload = started.json()
    return {
        "call_id": payload["call_id"],
        "start_ms": start_ms,
        "pipeline": payload.get("pipeline"),
    }


async def _wait_realtime_ready(call_id: str, *, started_at: float) -> float:
    from server.realtime.manager import realtime_text_manager

    session = realtime_text_manager.get(call_id)
    assert session is not None, "Realtime session missing after call start"
    await session.start()
    return (time.perf_counter() - started_at) * 1000


async def _six_turns(client: httpx.AsyncClient, *, session_id: str, call_id: str) -> list[dict]:
    turns = []
    for name, transcript in SIX_TURNS:
        row = await _stream_turn(
            client, transcript=transcript, session_id=session_id, call_id=call_id
        )
        row["name"] = name
        turns.append(row)
        print(
            f"[PERF] {name} TTFB_MS={row['ttfb_ms']:.0f} TOTAL_MS={row['total_ms']:.0f} "
            f"chars={row['chars']} streamed={row['streamed']}"
        )
        assert row["chars"] > 3, f"{name} empty reply"
        assert row["ttfb_ms"] < 10000, f"{name} TTFB too slow: {row['ttfb_ms']:.0f}ms"
    return turns


async def _barge_mid_stream(
    client: httpx.AsyncClient, *, session_id: str, call_id: str
) -> dict:
    transcript = (
        "Please explain parking, monthly price, timings, and location clearly "
        "in a few spoken sentences."
    )
    t0 = time.perf_counter()
    first_ms = None
    interrupt_http_ms = None
    interrupt_ok = False
    chars_at_interrupt = 0
    deltas: list[str] = []
    done: dict = {}
    interrupt_task: asyncio.Task | None = None

    async def fire_interrupt() -> None:
        nonlocal interrupt_http_ms, interrupt_ok
        t_int = time.perf_counter()
        response = await client.post(
            "/api/session/interrupt",
            json={"callId": call_id, "sessionId": session_id, "heardText": "wait stop"},
        )
        interrupt_http_ms = (time.perf_counter() - t_int) * 1000
        interrupt_ok = response.status_code == 200 and bool(response.json().get("ok"))

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
                deltas.append(str(payload["delta"]))
                if first_ms is None:
                    first_ms = (time.perf_counter() - t0) * 1000
                    chars_at_interrupt = len("".join(deltas))
                    interrupt_task = asyncio.create_task(fire_interrupt())
            if payload.get("done"):
                done = payload
                break
    if interrupt_task is not None:
        await interrupt_task
    stream_end_ms = (time.perf_counter() - t0) * 1000
    text = "".join(deltas) or str(done.get("text") or "")
    cancel_after_first_ms = (stream_end_ms - first_ms) if first_ms is not None else stream_end_ms
    return {
        "ttfb_ms": first_ms if first_ms is not None else stream_end_ms,
        "interrupt_http_ms": interrupt_http_ms,
        "interrupt_ok": interrupt_ok,
        "stream_end_ms": stream_end_ms,
        "cancel_after_first_ms": cancel_after_first_ms,
        "chars_at_interrupt": chars_at_interrupt,
        "chars_final": len(text),
        "text": text,
    }


@pytest.mark.asyncio
async def test_web_agent_six_turns_connect_and_barge(live_client: httpx.AsyncClient):
    sid = f"web-six-{int(time.time())}"
    wall0 = time.perf_counter()
    started = await _start_call(live_client, session_id=sid)
    ready_ms = await _wait_realtime_ready(started["call_id"], started_at=wall0)
    print(
        f"\n[CONNECT] pipeline={started['pipeline']} start_ms={started['start_ms']:.0f} "
        f"realtime_ready_ms={ready_ms:.0f}"
    )
    assert started["pipeline"] == "realtime_text"
    assert started["start_ms"] < 2500
    assert ready_ms < 8000

    try:
        turns = await _six_turns(
            live_client, session_id=sid, call_id=started["call_id"]
        )
        ledger = await live_client.get(f"/api/call/{started['call_id']}/transcript")
        ledger_ttft = [
            int(line["brain_latency_ms"])
            for line in (ledger.json().get("lines") or [])
            if line.get("role") == "assistant" and line.get("brain_latency_ms") is not None
        ]
        _print_turns("REALTIME 6 TURNS", started["start_ms"], ready_ms, turns)
        if ledger_ttft:
            print(
                f"LEDGER first-token ms: {ledger_ttft}  "
                f"AVG={_avg([float(x) for x in ledger_ttft]):.0f}  "
                f"followup_AVG={_avg([float(x) for x in ledger_ttft[1:]]):.0f}"
            )
        ttfbs = [r["ttfb_ms"] for r in turns]
        assert _avg(ttfbs) < 5000
        for row in turns:
            if row["audio_tokens"] is not None:
                assert row["audio_tokens"] == 0

        barge = await _barge_mid_stream(
            live_client, session_id=sid, call_id=started["call_id"]
        )
        print(
            f"\n[BARGE] ttfb_ms={barge['ttfb_ms']:.0f} interrupt_http_ms={barge['interrupt_http_ms']} "
            f"ok={barge['interrupt_ok']} cancel_after_first_ms={barge['cancel_after_first_ms']:.0f} "
            f"chars_at_interrupt={barge['chars_at_interrupt']} chars_final={barge['chars_final']}"
        )
        assert barge["interrupt_ok"] is True
        assert barge["interrupt_http_ms"] is not None and barge["interrupt_http_ms"] < 1500
        assert barge["cancel_after_first_ms"] < 2500, (
            f"barge did not stop generation quickly: {barge['cancel_after_first_ms']:.0f}ms"
        )

        after = await _stream_turn(
            live_client,
            transcript="Parking unda? Short ga cheppu.",
            session_id=sid,
            call_id=started["call_id"],
        )
        print(
            f"[BARGE FOLLOWUP] TTFB_MS={after['ttfb_ms']:.0f} TOTAL_MS={after['total_ms']:.0f} "
            f"chars={after['chars']}"
        )
        assert after["chars"] > 3
        assert after["ttfb_ms"] < 8000

        # Stash on the test for the comparison test / final summary.
        test_web_agent_six_turns_connect_and_barge.realtime = {  # type: ignore[attr-defined]
            "start_ms": started["start_ms"],
            "ready_ms": ready_ms,
            "turns": turns,
            "avg_ttfb": _avg(ttfbs),
            "avg_total": _avg([r["total_ms"] for r in turns]),
            "followup_avg_ttfb": _avg(ttfbs[1:]),
            "ledger_ttft": ledger_ttft,
            "ledger_avg": _avg([float(x) for x in ledger_ttft]),
            "barge": barge,
            "after_barge_ttfb": after["ttfb_ms"],
        }
    finally:
        await live_client.post(
            "/api/call/end", json={"callId": started["call_id"], "reason": "user_stop"}
        )


@pytest.mark.asyncio
async def test_web_agent_classic_http_six_turns(live_client: httpx.AsyncClient):
    sid = f"web-classic-{int(time.time())}"
    started = await _start_call(
        live_client,
        session_id=sid,
        stack_override={"pipeline": "classic"},
    )
    print(f"\n[CONNECT CLASSIC] pipeline={started['pipeline']} start_ms={started['start_ms']:.0f}")
    assert started["pipeline"] == "classic"
    try:
        turns = await _six_turns(
            live_client, session_id=sid, call_id=started["call_id"]
        )
        ledger = await live_client.get(f"/api/call/{started['call_id']}/transcript")
        ledger_ttft = [
            int(line["brain_latency_ms"])
            for line in (ledger.json().get("lines") or [])
            if line.get("role") == "assistant" and line.get("brain_latency_ms") is not None
        ]
        _print_turns("CLASSIC HTTP 6 TURNS", started["start_ms"], None, turns)
        if ledger_ttft:
            print(
                f"LEDGER first-token ms: {ledger_ttft}  "
                f"AVG={_avg([float(x) for x in ledger_ttft]):.0f}  "
                f"followup_AVG={_avg([float(x) for x in ledger_ttft[1:]]):.0f}"
            )
        ttfbs = [r["ttfb_ms"] for r in turns]
        rt = getattr(test_web_agent_six_turns_connect_and_barge, "realtime", None)
        if rt:
            print("\n======== REALTIME vs CLASSIC ========")
            print(
                f"connect  realtime_start={rt['start_ms']:.0f}ms ready={rt['ready_ms']:.0f}ms  "
                f"classic_start={started['start_ms']:.0f}ms"
            )
            print(
                f"SSE avg TTFB  realtime={rt['avg_ttfb']:.0f}ms  classic={_avg(ttfbs):.0f}ms  "
                f"delta={rt['avg_ttfb'] - _avg(ttfbs):+.0f}ms (negative = realtime faster)"
            )
            rt_led = rt.get("ledger_avg") or 0
            cl_led = _avg([float(x) for x in ledger_ttft])
            print(
                f"LEDGER avg first-token  realtime={rt_led:.0f}ms  classic={cl_led:.0f}ms  "
                f"delta={rt_led - cl_led:+.0f}ms (negative = realtime faster)"
            )
            print(
                f"avg TOTAL realtime={rt['avg_total']:.0f}ms  classic={_avg([r['total_ms'] for r in turns]):.0f}ms"
            )
            print(
                f"followup avg TTFB  realtime={rt['followup_avg_ttfb']:.0f}ms  "
                f"classic={_avg(ttfbs[1:]):.0f}ms"
            )
        test_web_agent_classic_http_six_turns.classic = {  # type: ignore[attr-defined]
            "start_ms": started["start_ms"],
            "turns": turns,
            "avg_ttfb": _avg(ttfbs),
            "avg_total": _avg([r["total_ms"] for r in turns]),
            "followup_avg_ttfb": _avg(ttfbs[1:]),
        }
    finally:
        await live_client.post(
            "/api/call/end", json={"callId": started["call_id"], "reason": "user_stop"}
        )
