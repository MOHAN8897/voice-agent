"""Second live Gnani probe: determinism, <whispers>, and mid-sentence <slow>."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import math
import os
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from server.services import sarvam_stt_service  # noqa: E402
from server.services.gnani_tts_ws import connect_gnani_tts_ws  # noqa: E402

HERE = Path(__file__).resolve().parent
MODEL, VOICE, LANGUAGE, RATE = "timbre-v3.0", "Shivani", "en-IN", 16000

CASES = [
    ("A_neutral_run2", "Great news, your trial class is free."),
    ("B_excited_run2", "<excited> Great news, your trial class is free."),
    ("H_control_secret", "I have something to tell you."),
    ("I_whispers", "<whispers> I have something to tell you."),
    ("J_control_price", "The course costs eight thousand rupees."),
    ("K_slow_mid", "The course costs <slow> eight thousand rupees."),
]


def _wav(pcm: bytes) -> bytes:
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
    return header + b"data" + struct.pack("<I", len(pcm)) + pcm


def _rms(pcm: bytes) -> float:
    usable = len(pcm) - (len(pcm) % 2)
    if not usable:
        return 0.0
    samples = struct.unpack(f"<{usable // 2}h", pcm[:usable])
    return math.sqrt(sum(s * s for s in samples) / len(samples))


async def _synthesize(conn, text: str) -> bytes:
    await conn.send(json.dumps({"type": "text", "data": {"text": text}}))
    await conn.send(json.dumps({"type": "flush", "data": {}}))
    audio = bytearray()

    async def _drain():
        async for message in conn:
            payload = json.loads(message)
            if payload.get("type") == "audio":
                audio.extend(base64.b64decode(payload["data"]["audio"]))
            elif payload.get("type") in {"end_of_stream", "error"}:
                return

    await asyncio.wait_for(_drain(), timeout=45)
    return bytes(audio)


async def main() -> int:
    rows = []
    async with connect_gnani_tts_ws(MODEL) as conn:
        await conn.send(json.dumps({"type": "config", "data": {
            "language_code": LANGUAGE, "speaker": VOICE, "sample_rate": RATE,
        }}))
        for name, text in CASES:
            pcm = await _synthesize(conn, text)
            transcript = ""
            if pcm:
                try:
                    stt = await sarvam_stt_service.transcribe(_wav(pcm), language_code=LANGUAGE)
                    transcript = stt.get("transcript") or ""
                except Exception as exc:
                    transcript = f"STT_ERR {type(exc).__name__}"
            row = {
                "case": name, "text": text, "bytes": len(pcm),
                "duration_s": round(len(pcm) / 2 / RATE, 3),
                "rms": round(_rms(pcm), 1),
                "sha256": hashlib.sha256(pcm).hexdigest()[:16],
                "transcript": transcript,
            }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))

    by = {r["case"]: r for r in rows}
    ratios = {}
    for tagged, control in (("I_whispers", "H_control_secret"), ("K_slow_mid", "J_control_price")):
        if by.get(tagged) and by.get(control):
            ratios[f"{tagged}_vs_{control}"] = {
                "duration": round(by[tagged]["duration_s"] / by[control]["duration_s"], 3),
                "rms": round(by[tagged]["rms"] / by[control]["rms"], 3),
            }
    print("ratios:", ratios)
    (HERE / "probe_gnani_tags_ws2.json").write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "rows": rows,
                    "ratios": ratios}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
