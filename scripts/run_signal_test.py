"""Place Telnyx outbound call and trigger agent audio signal test."""
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
        for i in range(40):
            await asyncio.sleep(2)
            flow = await client.get("/api/dev/telephony/media-flow")
            snapshot = flow.json().get("flow") or {}
            if snapshot.get("active") and snapshot.get("call_id"):
                external_id = snapshot.get("external_id") or ""
                print(
                    "stream active",
                    snapshot.get("call_id"),
                    "negotiated",
                    snapshot.get("negotiated"),
                )
                external_id = snapshot.get("external_id") or ""
                speak = await client.post(
                    "/api/dev/telephony/media-flow/test-telnyx-speak",
                    params={"call_id": external_id} if external_id else None,
                    headers=headers,
                )
                print("telnyx-speak", speak.status_code, speak.text[:400])
                await asyncio.sleep(6)
                test = await client.post(
                    "/api/dev/telephony/media-flow/test-audio",
                    params={"call_id": external_id} if external_id else None,
                    headers=headers,
                )
                print("test-audio", test.status_code, test.text[:400])
                await asyncio.sleep(10)
                flow2 = await client.get("/api/dev/telephony/media-flow")
                snap2 = flow2.json().get("flow") or {}
                events = [
                    e
                    for e in (snap2.get("events") or [])
                    if e.get("stage")
                    in ("stt_final", "llm_started", "tts_started", "tts_audio", "outbound_sent")
                ]
                print("text pipeline events:")
                for event in events[-10:]:
                    detail = (event.get("detail") or "").encode("ascii", "replace").decode("ascii")
                    print(
                        f"  {event.get('stage')}: {detail} "
                        f"bytes={event.get('bytes') or 0}"
                    )
                metrics = snap2.get("metrics") or {}
                print(
                    "outbound_sent_frames",
                    metrics.get("outbound_sent_frames"),
                    "health",
                    snap2.get("health"),
                )
                return
            print(f"waiting stream... {i + 1}")
        print("no active stream after 60s")


if __name__ == "__main__":
    asyncio.run(main())
