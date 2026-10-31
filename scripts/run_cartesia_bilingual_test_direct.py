"""Cartesia bilingual PSTN test — L16 @ 16 kHz aligned with Telnyx."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.config.env import get_settings
from server.config.urls import ws_public_base
from server.services.dev_secrets_store import dev_secrets_store
from server.services.telnyx_client import TelnyxClient, telnyx_stream_tokens

AGENT_ID = "aead8ad2-389b-4482-a9a5-11bfcb37fe0d"
TO = "+918897908470"

CARTESIA_STACK = {
    "tts": {
        "provider": "cartesia",
        "model": "sonic-3.5",
        "config": {},
    }
}


async def main() -> None:
    get_settings.cache_clear()
    dev_secrets_store.reload()
    if not dev_secrets_store.effective_secret("cartesia_api_key"):
        print("ERROR: Cartesia API key missing in data/dev_secrets.json")
        sys.exit(1)

    client = TelnyxClient()
    token = telnyx_stream_tokens.create(
        agent_id=AGENT_ID,
        tier="medium",
        language="te-IN",
        direction="outbound",
    )
    stream_url = f"{ws_public_base().rstrip('/')}/ws/telnyx-stream?token={token}"
    print("stream_url:", stream_url)
    print("TTS: Cartesia sonic-3.5 | Wire: Telnyx L16 @ 16 kHz")
    print("Test: Telugu (Indian voice) -> English (US accent)")
    print()
    print(">>> ANSWER YOUR PHONE — STAY SILENT <<<")
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
            "stack_override": CARTESIA_STACK,
            "test_mode": "cartesia_bilingual",
            "skip_greeting": True,
        },
    )
    call_control_id = str(result.get("call_control_id") or "")
    print("call_control_id:", call_control_id)

    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=30) as api:
        await api.post("/api/dev/login", json={"username": "dev", "password": "devpass"})
        csrf = api.cookies.get("dev_csrf") or ""
        headers = {"X-CSRF-Token": csrf} if csrf else {}

        for i in range(50):
            await asyncio.sleep(2)
            flow = await api.get("/api/dev/telephony/media-flow", headers=headers)
            snap = flow.json().get("flow") or {}
            if not snap.get("active") and i < 10:
                print(f"  [{i * 2 + 2}s] waiting for stream...")
                continue
            stages = snap.get("stages") or {}
            metrics = snap.get("metrics") or {}
            negotiated = snap.get("negotiated") or {}
            outbound_frames = metrics.get("outbound_sent_frames") or 0
            print(
                f"  [{i * 2 + 2}s] codec={negotiated.get('codec')} "
                f"rate={negotiated.get('sample_rate')} "
                f"tts={'tts_audio' in stages} out={'outbound_sent' in stages} "
                f"frames={outbound_frames}"
            )
            if outbound_frames >= 80 and "cartesia_bilingual" in str(stages):
                pass
            if outbound_frames >= 150 and i >= 12:
                print()
                print("Cartesia bilingual test sent. Did you hear Telugu then English clearly?")
                return
        print("timed out — check API logs for cartesia_bilingual")


if __name__ == "__main__":
    asyncio.run(main())
