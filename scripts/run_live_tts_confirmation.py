"""Live TTS confirmation call — long English script, prewarm vs live comparison.

Places an outbound agent call, then plays two long LIVE English TTS segments after
the pre-buffered opening greeting. Stay silent on the phone.

Usage:
  python scripts/run_live_tts_confirmation.py
  python scripts/run_live_tts_confirmation.py --to +918897908470

Listen and rate each phase:
  A) Opening greeting (prepared while ringing — prewarm buffer)
  B) Live segment one (generated during the call)
  C) Live segment two (generated during the call — longer stress)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000"
AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
DEFAULT_TO = "+918897908470"

LIVE_SEGMENT_ONE = (
    "This is live test segment one. I am speaking entirely in English to check whether "
    "real-time text to speech sounds clear on your phone. The opening greeting you heard "
    "earlier was prepared while the phone was ringing, before you answered. This paragraph "
    "is being generated live during the call through the same WebSocket audio path. "
    "Please listen for digital glitches, choppy packet boundaries, or robotic cutting "
    "between words and sentences."
)

LIVE_SEGMENT_TWO = (
    "This is live test segment two. I will keep speaking for a little longer so we can "
    "stress the outbound audio queue and the twenty millisecond pacing system. If this "
    "segment sounds worse than the greeting, the issue is likely live streaming underruns "
    "rather than Telnyx or your mobile carrier. Signal test alpha. Signal test bravo. "
    "Signal test charlie. Signal test delta. We are testing continuous English speech "
    "without any Telugu mixed in, so you can compare the buffered greeting against two "
    "back-to-back live synthesis passes. Thank you for listening."
)


def _metrics(flow: dict) -> dict:
    m = flow.get("metrics") or {}
    return {
        "outbound_sent_frames": m.get("outbound_sent_frames"),
        "text_queued_count": m.get("text_queued_count"),
        "underruns": m.get("playout_underrun_count"),
        "speech_drops": m.get("normal_speech_dropped_frames"),
        "backpressure_waits": m.get("producer_backpressure_wait_count"),
        "backpressure_ms": m.get("producer_backpressure_wait_ms"),
        "outbound_pkt_s": m.get("outbound_packets_per_sec"),
        "queue_p95": m.get("queue_depth_p95"),
        "negotiated": flow.get("negotiated"),
    }


async def _flow(client: httpx.AsyncClient, headers: dict, call_id: str | None) -> dict:
    params = {"call_id": call_id} if call_id else None
    r = await client.get("/api/dev/telephony/media-flow", params=params, headers=headers)
    if r.status_code != 200:
        return {}
    return r.json().get("flow") or {}


async def _live_speak(
    client: httpx.AsyncClient,
    headers: dict,
    *,
    call_id: str,
    text: str,
    label: str,
) -> dict:
    r = await client.post(
        "/api/dev/telephony/media-flow/test-live-speak",
        json={"text": text, "callId": call_id, "languageCode": "en-IN"},
        headers=headers,
    )
    body = r.json()
    print(f"\n--- {label} ---")
    print("live-speak", r.status_code, "chars=", body.get("chars"), "preview:", (body.get("preview") or "")[:80])
    if not body.get("ok"):
        print("ERROR:", body.get("error") or body)
        return body
    # ~14 chars/sec English TTS rough estimate + buffer
    wait_s = max(20, min(90, len(text) // 10 + 15))
    print(f"playing ~{wait_s}s — stay silent, listen for glitches...")
    await asyncio.sleep(wait_s)
    flow = await _flow(client, headers, call_id)
    snap = _metrics(flow)
    print("metrics:", json.dumps(snap, indent=2))
    return snap


async def main() -> int:
    parser = argparse.ArgumentParser(description="Long English live TTS confirmation call")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--to", default=DEFAULT_TO)
    parser.add_argument("--greeting-wait", type=int, default=14, help="Seconds for prewarm greeting")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=90.0) as client:
        login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        if login.status_code != 200:
            print("login failed", login.status_code)
            return 1
        csrf = client.cookies.get("dev_csrf") or ""
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        dial = await client.post(
            "/api/dev/telephony/outbound",
            json={"toE164": args.to, "agentId": AGENT_ID, "tier": "medium", "language": "en-IN"},
            headers=headers,
        )
        body = dial.json()
        print("dial", dial.status_code, "ok=", body.get("ok"))
        if dial.status_code != 200 or body.get("ok") is False:
            print("error:", body.get("error") or body)
            return 1

        print()
        print("=" * 72)
        print("LIVE TTS CONFIRMATION CALL — ENGLISH")
        print("=" * 72)
        print()
        print(">>> ANSWER YOUR PHONE AND STAY COMPLETELY SILENT <<<")
        print()
        print("You will hear THREE phases. Note which sound clear vs glitchy:")
        print()
        print("  PHASE A — Opening greeting (PREWARM / buffered while ringing)")
        print("  PHASE B — Live segment one  (real-time TTS during call)")
        print("  PHASE C — Live segment two  (longer live TTS stress test)")
        print()
        print("If A is clear but B and C are glitchy -> confirms live TTS underrun diagnosis.")
        print()

        external_id = ""
        call_id = ""
        for i in range(45):
            await asyncio.sleep(2)
            flow = await _flow(client, headers, None)
            if flow.get("active"):
                external_id = str(flow.get("external_id") or "")
                call_id = str(flow.get("call_id") or "")
                neg = flow.get("negotiated") or {}
                print(
                    f"  [{(i + 1) * 2}s] stream active "
                    f"codec={neg.get('codec')}/{neg.get('sample_rate')} call_id={call_id}"
                )
                break
            print(f"  [{(i + 1) * 2}s] waiting for stream...")
        else:
            print("FAIL: no active stream — did you answer?")
            return 1

        print(f"\nPHASE A: listening to prewarm greeting ({args.greeting_wait}s)...")
        await asyncio.sleep(args.greeting_wait)
        snap_a = _metrics(await _flow(client, headers, call_id or external_id))
        print("after greeting:", json.dumps(snap_a, indent=2))

        snap_b = await _live_speak(
            client,
            headers,
            call_id=external_id or call_id,
            text=LIVE_SEGMENT_ONE,
            label="PHASE B — LIVE SEGMENT ONE",
        )
        await asyncio.sleep(3)

        snap_c = await _live_speak(
            client,
            headers,
            call_id=external_id or call_id,
            text=LIVE_SEGMENT_TWO,
            label="PHASE C — LIVE SEGMENT TWO",
        )

        print()
        print("=" * 72)
        print("CONFIRMATION SUMMARY")
        print("=" * 72)
        print(json.dumps({"phase_a_after_greeting": snap_a, "phase_b": snap_b, "phase_c": snap_c}, indent=2))
        print()
        print("Please report:")
        print("  Phase A (greeting):  clear / glitchy")
        print("  Phase B (live one):  clear / glitchy")
        print("  Phase C (live two):  clear / glitchy")
        print()
        underruns = (snap_c or {}).get("underruns") or 0
        if underruns:
            print(f"Server logged {underruns} playout underrun(s) — gaps likely on phone.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
