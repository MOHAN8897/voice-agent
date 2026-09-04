"""TEST 5 — TTS → Telnyx WebSocket → phone (agent audio outbound).

Places outbound call, triggers test-audio, validates media-flow telemetry.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000"
AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
TO = "+918897908470"
FRAME_BYTES = 640


async def main() -> int:
    parser = argparse.ArgumentParser(description="TEST 5 — agent TTS to Telnyx handset")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--to", default=TO)
    parser.add_argument("--wait-stream", type=int, default=60)
    parser.add_argument("--wait-audio", type=int, default=25)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=60.0) as client:
        login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        if login.status_code != 200:
            print("login failed", login.status_code)
            return 1
        csrf = client.cookies.get("dev_csrf") or ""
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        dial = await client.post(
            "/api/dev/telephony/outbound",
            json={"toE164": args.to, "agentId": AGENT_ID, "tier": "medium", "language": "te-IN"},
            headers=headers,
        )
        body = dial.json()
        print("dial", dial.status_code, "ok=", body.get("ok"))
        if dial.status_code != 200 or body.get("ok") is False:
            print("error:", body.get("error") or body)
            return 1

        print()
        print(">>> ANSWER YOUR PHONE <<<")
        print("You should hear:")
        print("  1) Agent opening greeting (Namaste / sahayam cheyagalanu)")
        print("  2) Then: Signal test one... two... three... + Telugu test phrase")
        print()

        external_id = ""
        for i in range(args.wait_stream // 2):
            await asyncio.sleep(2)
            flow_r = await client.get("/api/dev/telephony/media-flow", headers=headers)
            flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
            if flow.get("active"):
                external_id = str(flow.get("external_id") or "")
                neg = flow.get("negotiated") or {}
                print(
                    f"  [{(i + 1) * 2}s] stream active negotiated={neg.get('codec')}/{neg.get('sample_rate')} "
                    f"call_id={flow.get('call_id')}"
                )
                break
            print(f"  [{(i + 1) * 2}s] waiting for stream...")
        else:
            print("FAIL: no active stream")
            return 1

        # Opening greeting plays automatically; speak() lock serializes test phrase after it.
        print("waiting 6s for opening greeting to finish...")
        await asyncio.sleep(6)

        params = {"call_id": external_id} if external_id else None
        test = await client.post(
            "/api/dev/telephony/media-flow/test-audio",
            params=params,
            headers=headers,
        )
        body = test.json()
        detail = str(body.get("detail") or body).encode("ascii", "replace").decode("ascii")
        print("test-audio", test.status_code, detail[:200])
        print(f"waiting {args.wait_audio}s for test phrase playback...")
        await asyncio.sleep(args.wait_audio)

        flow_r = await client.get(
            "/api/dev/telephony/media-flow",
            params={"call_id": external_id} if external_id else None,
            headers=headers,
        )
        flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
        stages = flow.get("stages") or {}
        metrics = flow.get("metrics") or {}
        health = flow.get("health") or {}
        checks = health.get("checks") or {}
        failures = health.get("failures") or []

        outbound_events = [
            e
            for e in (flow.get("events") or [])
            if e.get("stage") == "outbound_sent" and e.get("status") != "failed"
        ]
        frame_bytes = [e.get("bytes") for e in outbound_events[-20:]]
        bad_frames = [b for b in frame_bytes if b and b != FRAME_BYTES]

        gates = {
            "negotiated_L16_16k": (flow.get("negotiated") or {}).get("codec") == "L16"
            and (flow.get("negotiated") or {}).get("sample_rate") == 16000,
            "tts_started": "tts_started" in stages,
            "tts_audio": "tts_audio" in stages,
            "outbound_sent": "outbound_sent" in stages,
            "outbound_frames_gt_0": int(metrics.get("outbound_sent_frames") or 0) > 0,
            "frames_640_bytes": not bad_frames,
            "health_telnyx_outbound": bool(checks.get("telnyx_outbound")),
            "no_outbound_failure": "OUTBOUND_TRANSMISSION_FAILURE" not in failures,
            "no_audio_backlog": "AUDIO_BACKLOG" not in failures,
        }

        print()
        print("TEST 5 gate:")
        for key, passed in gates.items():
            print(f"  {'PASS' if passed else 'FAIL'}: {key}")
        print("outbound_sent_frames:", metrics.get("outbound_sent_frames"))
        print("health_score:", health.get("score"))
        if bad_frames:
            print("bad frame sizes (last 20):", bad_frames[:5])
        overall = all(gates.values())
        print("overall:", "PASS" if overall else "PARTIAL/FAIL")
        print()
        print("Did you HEAR agent test audio on the phone? (confirm manually)")
        return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
