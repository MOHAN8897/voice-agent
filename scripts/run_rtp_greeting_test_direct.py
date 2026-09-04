"""Agent RTP greeting test — uses fresh tunnel URL (bypasses stale get_settings cache)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.config.env import get_settings
from server.config.urls import ws_public_base
from server.services.telnyx_client import TelnyxClient, telnyx_stream_tokens

AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
TO = "+918897908470"


async def main() -> None:
    get_settings.cache_clear()
    client = TelnyxClient()
    token = telnyx_stream_tokens.create(
        agent_id=AGENT_ID,
        tier="medium",
        language="te-IN",
        direction="outbound",
    )
    stream_url = f"{ws_public_base().rstrip('/')}/ws/telnyx-stream?token={token}"
    print("stream_url:", stream_url)
    print("mode: RTP/L16 16kHz (Telnyx) <-> Sarvam linear16 16kHz, barge-in OFF")
    print()
    print(">>> ANSWER YOUR PHONE — STAY SILENT 15 SECONDS <<<")
    print()

    result = await client.create_outbound_call(
        to_e164=TO,
        stream_url=stream_url,
        bidirectional_mode="rtp",
        target_legs="self",
        client_state={
            "agent_id": AGENT_ID,
            "tier": "medium",
            "language": "te-IN",
            "direction": "outbound",
        },
    )
    call_control_id = str(result.get("call_control_id") or "")
    print("call_control_id:", call_control_id)

    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=30) as api:
        await api.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        csrf = api.cookies.get("dev_csrf") or ""
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        for i in range(40):
            await asyncio.sleep(2)
            flow = await api.get("/api/dev/telephony/media-flow", headers=headers)
            snap = flow.json().get("flow") or {}
            if not snap.get("active") and i < 8:
                print(f"  [{i * 2 + 2}s] waiting for stream...")
                continue
            stages = snap.get("stages") or {}
            metrics = snap.get("metrics") or {}
            negotiated = snap.get("negotiated") or {}
            outbound_frames = metrics.get("outbound_sent_frames") or 0
            print(
                f"  [{i * 2 + 2}s] codec={negotiated.get('codec')} "
                f"tts={'tts_audio' in stages} out={'outbound_sent' in stages} "
                f"frames={outbound_frames}"
            )
            if "outbound_sent" in stages and outbound_frames >= 5 and i >= 6:
                print()
                print("Outbound RTP sent. Did you HEAR the Telugu greeting?")
                return
        print("timed out — check API terminal for [PSTN] media.out.first")


if __name__ == "__main__":
    asyncio.run(main())
