"""Probe Sarvam TTS WS output format for PSTN configs."""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.config.env import get_settings
from server.services.sarvam_ws import connect_tts_ws
from server.services.tts_config import merge_pstn_tts_config


def _guess_format(data: bytes) -> str:
    if not data:
        return "empty"
    if data[:4] == b"RIFF":
        return "wav"
    if data[:3] == b"ID3" or (len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "mp3"
    # μ-law silence is often 0xFF or 0x7F; PCM16 has more even distribution
    unique = len(set(data[: min(64, len(data))]))
    if len(data) % 2 == 0 and unique > 20:
        return "likely_linear16"
    return "likely_mulaw_or_g711"


async def _run_case(label: str, cfg: dict) -> None:
    print(f"\n=== {label} ===")
    print("config:", json.dumps({k: cfg[k] for k in sorted(cfg) if k in {
        "output_audio_codec", "speech_sample_rate", "sample_rate", "speaker", "language_code"
    }}, indent=2))
    async with connect_tts_ws(model=cfg.get("model", "bulbul:v3")) as ws:
        await ws.send(json.dumps({"type": "config", "data": cfg}))
        await ws.send(json.dumps({"type": "text", "data": {"text": "Namaste, signal test."}}))
        await ws.send(json.dumps({"type": "flush"}))
        chunks: list[bytes] = []
        meta_rates: list[str] = []
        async for raw in ws:
            if isinstance(raw, bytes):
                raw = raw.decode(errors="ignore")
            obj = json.loads(raw)
            msg_type = obj.get("type") or obj.get("event") or ""
            data = obj.get("data")
            if isinstance(data, dict):
                if data.get("speech_sample_rate"):
                    meta_rates.append(str(data["speech_sample_rate"]))
                if data.get("sample_rate"):
                    meta_rates.append(str(data["sample_rate"]))
                audio_b64 = data.get("audio")
            else:
                audio_b64 = obj.get("audio")
            if msg_type in ("event", "completion", "end", "done"):
                break
            if not audio_b64:
                continue
            audio = base64.b64decode(audio_b64)
            chunks.append(audio)
            if len(chunks) >= 3:
                break
    total = b"".join(chunks)
    print(f"chunks={len(chunks)} total_bytes={len(total)} meta_rates={meta_rates or ['none']}")
    print(f"guess={_guess_format(total)} first16={total[:16].hex()}")


async def main() -> None:
    get_settings.cache_clear()
    mulaw_cfg = merge_pstn_tts_config("diag", call_id=None, ws_model="bulbul:v3")
    lin8_cfg = dict(mulaw_cfg)
    lin8_cfg["output_audio_codec"] = "linear16"
    lin8_cfg["speech_sample_rate"] = "8000"
    lin16_cfg = dict(mulaw_cfg)
    lin16_cfg["output_audio_codec"] = "linear16"
    lin16_cfg["speech_sample_rate"] = "16000"
    await _run_case("mulaw@8k (current PSTN)", mulaw_cfg)
    await _run_case("linear16@8k", lin8_cfg)
    await _run_case("linear16@16k", lin16_cfg)


if __name__ == "__main__":
    asyncio.run(main())
