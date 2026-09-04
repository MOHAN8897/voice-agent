"""Verify Telnyx L16 @ 16 kHz ↔ Sarvam linear16 @ 16 kHz alignment."""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.audio_transcode import chunk_pcm16_frames
from server.services.sarvam_ws import connect_tts_ws
from server.services.telnyx_client import TELNYX_RTP_CODEC, TELNYX_RTP_SAMPLE_RATE
from server.services.tts_config import merge_pstn_tts_config

TELNYX_FRAME_BYTES = int(TELNYX_RTP_SAMPLE_RATE * 20 / 1000) * 2  # 640


async def main() -> None:
    cfg = merge_pstn_tts_config("diag", call_id=None, ws_model="bulbul:v3", wire_mode="rtp_l16")
    sarvam_payload = {k: v for k, v in cfg.items() if k not in {"provider", "model"}}
    print("Telnyx expects:", TELNYX_RTP_CODEC, f"@ {TELNYX_RTP_SAMPLE_RATE} Hz", f"({TELNYX_FRAME_BYTES} B / 20 ms)")
    print("Sarvam config:", json.dumps(sarvam_payload, indent=2))
    print()

    async with connect_tts_ws(model="bulbul:v3") as ws:
        await ws.send(json.dumps({"type": "config", "data": sarvam_payload}))
        await ws.send(json.dumps({"type": "text", "data": {"text": "Namaste! Nenu Priya, SKM Plants nundi matladutunnanu."}}))
        await ws.send(json.dumps({"type": "flush"}))
        pcm = bytearray()
        async for raw in ws:
            obj = json.loads(raw if isinstance(raw, str) else raw.decode())
            msg_type = obj.get("type") or obj.get("event") or ""
            if msg_type in ("event", "completion", "end", "done"):
                break
            data = obj.get("data")
            b64 = data.get("audio") if isinstance(data, dict) else obj.get("audio")
            if b64:
                pcm.extend(base64.b64decode(b64))

    frames = chunk_pcm16_frames(bytes(pcm), sample_rate=TELNYX_RTP_SAMPLE_RATE)
    bad = [len(f) for f in frames if len(f) != TELNYX_FRAME_BYTES]
    duration_s = len(pcm) / (TELNYX_RTP_SAMPLE_RATE * 2)
    print(f"Sarvam PCM16: {len(pcm)} bytes ({duration_s:.2f}s)")
    print(f"RTP frames: {len(frames)} (bad sizes: {bad[:5] or 'none'})")
    print(f"Alignment: {'OK' if not bad and frames else 'FAIL'}")

    out = ROOT / "data" / "diag_telnyx_l16.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TELNYX_RTP_SAMPLE_RATE)
        w.writeframes(bytes(pcm))
    print(f"Wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
