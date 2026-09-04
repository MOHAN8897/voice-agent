"""TEST 2 — Telnyx inbound audio monitor."""
from __future__ import annotations

import asyncio
import sys

import httpx

BASE = "https://api-dev.hustlelabs.in"
AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
TO = "+918897908470"


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=60.0) as client:
        login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        if login.status_code != 200:
            print("login failed", login.status_code)
            return 1
        csrf = client.cookies.get("dev_csrf") or ""
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        dial = await client.post(
            "/api/dev/telephony/outbound",
            json={"toE164": TO, "agentId": AGENT_ID, "tier": "medium", "language": "te-IN"},
            headers=headers,
        )
        body = dial.json()
        print("dial", dial.status_code, "ok=", body.get("ok"), "control=", (body.get("call_control_id") or "")[:48])
        if dial.status_code != 200 or body.get("ok") is False:
            print("error:", body.get("error") or body)
            return 1

        print()
        print(">>> ANSWER YOUR PHONE and say clearly for 5-10 seconds: Testing one two three <<<")
        print()

        best: dict | None = None
        for i in range(45):
            await asyncio.sleep(2)
            flow_r = await client.get("/api/dev/telephony/media-flow", headers=headers)
            flow = (flow_r.json().get("flow") or {}) if flow_r.status_code == 200 else {}
            active = flow.get("active")
            neg = flow.get("negotiated") or {}
            metrics = flow.get("metrics") or {}
            stages = flow.get("stages") or {}
            inbound = stages.get("inbound_audio") or {}
            health = flow.get("health") or {}
            failures = health.get("failures") or flow.get("failures") or []
            in_frames = int(metrics.get("inbound_frames") or 0)
            codec = neg.get("codec")
            rate = neg.get("sample_rate")
            dbfs = inbound.get("level_dbfs")
            print(f"  [{(i + 1) * 2}s] active={active} negotiated={codec}/{rate} inbound_frames={in_frames} dbfs={dbfs}")
            if failures:
                print("    failures:", failures)
            if active and in_frames > 0:
                best = flow
                if in_frames >= 10:
                    break
            elif active and codec:
                best = flow

        print()
        if not best:
            print("FAIL: no active stream detected within 90s")
            return 1

        neg = best.get("negotiated") or {}
        health = best.get("health") or {}
        metrics = best.get("metrics") or {}
        stages = best.get("stages") or {}
        inbound = stages.get("inbound_audio") or {}
        fail_list = health.get("failures") or []

        gate = {
            "active": bool(best.get("active")),
            "codec_L16": neg.get("codec") == "L16",
            "rate_16000": neg.get("sample_rate") == 16000,
            "channels_1": neg.get("channels") == 1,
            "inbound_frames_gt_0": int(metrics.get("inbound_frames") or 0) > 0,
            "no_codec_mismatch": not any(
                "CODEC_MISMATCH" in str(f) or "SAMPLE_RATE_MISMATCH" in str(f) for f in fail_list
            ),
            "inbound_healthy": inbound.get("status") == "healthy",
        }
        print("TEST 2 gate:")
        for key, passed in gate.items():
            print(f"  {'PASS' if passed else 'FAIL'}: {key}")
        overall = all(gate.values())
        print("overall:", "PASS" if overall else "PARTIAL/FAIL")
        print("health_score:", health.get("score"))
        print("inbound_frames:", metrics.get("inbound_frames"))
        print("call_id:", best.get("call_id"))
        print("external_id:", (best.get("external_id") or "")[:60])
        return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
