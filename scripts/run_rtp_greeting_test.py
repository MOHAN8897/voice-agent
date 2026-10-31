"""Agent outbound call — RTP/PCMU mode, barge-in off. Stay silent 15s for greeting."""
from __future__ import annotations

import asyncio
import json

import httpx

AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
TO = "+918897908470"


async def main() -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=60.0) as client:
        login = await client.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        print("login", login.status_code)
        csrf = client.cookies.get("dev_csrf") or ""
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        dial = await client.post(
            "/api/dev/telephony/outbound",
            json={
                "toE164": TO,
                "agentId": AGENT_ID,
                "tier": "medium",
                "language": "te-IN",
            },
            headers=headers,
        )
        print("dial", dial.status_code, dial.text[:500])
        if dial.status_code != 200 or not dial.json().get("ok"):
            return

        print()
        print(">>> ANSWER YOUR PHONE — DO NOT SPEAK FOR 15 SECONDS <<<")
        print("Waiting for stream + greeting (RTP/PCMU, barge-in OFF)...")
        print()

        for i in range(45):
            await asyncio.sleep(2)
            flow = await client.get("/api/dev/telephony/media-flow")
            snap = flow.json().get("flow") or {}
            if not snap.get("active") and i < 5:
                print(f"  [{i * 2 + 2}s] waiting for stream...")
                continue

            stages = snap.get("stages") or {}
            metrics = snap.get("metrics") or {}
            events = snap.get("events") or []
            outbound = metrics.get("outbound_sent_frames") or 0
            tts = "tts_audio" in stages
            out = "outbound_sent" in stages
            negotiated = snap.get("negotiated") or {}

            print(
                f"  [{i * 2 + 2}s] codec={negotiated.get('codec')} "
                f"tts={tts} outbound={out} frames={outbound}"
            )

            if i == 7:
                print("  (you should be hearing greeting now if RTP path works)")

            if out and outbound >= 10 and i >= 7:
                print()
                print("Outbound RTP frames sent:", outbound)
                print("Did you HEAR the agent greeting? (check your phone)")
                recent = [
                    e
                    for e in events
                    if e.get("stage") in ("tts_audio", "outbound_sent", "greeting")
                ][-5:]
                for e in recent:
                    print(
                        f"  {e.get('stage')}: bytes={e.get('bytes')} "
                        f"codec={e.get('codec')}"
                    )
                return

        print("timed out — check API logs for [PSTN] stream.start / media.out.first")


if __name__ == "__main__":
    asyncio.run(main())
