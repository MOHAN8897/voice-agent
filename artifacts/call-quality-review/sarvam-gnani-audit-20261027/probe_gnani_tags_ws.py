"""Live Gnani TTS v3 tag probe over the production WebSocket adapter.

The public docs only describe audio tags for SSE streaming; our composed PSTN
path sends them over the WebSocket. This probe synthesises the same sentence
with and without cues, measures duration/energy, and transcribes the audio with
Sarvam STT to prove whether a cue is spoken literally.

Usage:
    python artifacts/call-quality-review/sarvam-gnani-audit-20261027/probe_gnani_tags_ws.py
"""
from __future__ import annotations

import asyncio
import base64
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
MODEL = "timbre-v3.0"
VOICE = "Shivani"
LANGUAGE = "en-IN"
SAMPLE_RATE = 16000

CASES = [
    ("A_neutral", "Great news, your trial class is free."),
    ("B_excited", "<excited> Great news, your trial class is free."),
    ("C_control_spoken_tag", "excited Great news, your trial class is free."),
    ("D_pauses", "<pauses> Let me check that for you."),
    ("E_control_plain", "Let me check that for you."),
    ("F_slow", "<slow> The intermediate course costs eight thousand rupees."),
    ("G_control_fast", "The intermediate course costs eight thousand rupees."),
]


def _wav(pcm: bytes, sample_rate: int) -> bytes:
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    return header + b"data" + struct.pack("<I", len(pcm)) + pcm


def _rms(pcm: bytes) -> float:
    usable = len(pcm) - (len(pcm) % 2)
    if not usable:
        return 0.0
    samples = struct.unpack(f"<{usable // 2}h", pcm[:usable])
    return math.sqrt(sum(s * s for s in samples) / len(samples))


async def _synthesize(conn, text: str) -> dict:
    await conn.send(json.dumps({"type": "text", "data": {"text": text}}))
    await conn.send(json.dumps({"type": "flush", "data": {}}))
    audio = bytearray()
    errors: list[str] = []
    async def _drain():
        async for message in conn:
            payload = json.loads(message)
            mtype = payload.get("type")
            if mtype == "audio":
                try:
                    audio.extend(base64.b64decode(payload["data"]["audio"]))
                except Exception:
                    pass
            elif mtype == "error":
                errors.append(str(payload.get("message") or payload))
                return
            elif mtype == "end_of_stream":
                return
    try:
        await asyncio.wait_for(_drain(), timeout=45)
    except asyncio.TimeoutError:
        errors.append("timeout waiting for end_of_stream")
    return {"pcm": bytes(audio), "errors": errors}


async def main() -> int:
    rows: list[dict] = []
    async with connect_gnani_tts_ws(MODEL) as conn:
        await conn.send(json.dumps({"type": "config", "data": {
            "language_code": LANGUAGE, "speaker": VOICE, "sample_rate": SAMPLE_RATE,
        }}))
        for name, text in CASES:
            result = await _synthesize(conn, text)
            pcm = result["pcm"]
            duration = len(pcm) / 2 / SAMPLE_RATE
            transcript = ""
            stt_error = ""
            if pcm:
                try:
                    stt = await sarvam_stt_service.transcribe(
                        _wav(pcm, SAMPLE_RATE), language_code=LANGUAGE, mode="transcribe"
                    )
                    transcript = stt.get("transcript") or ""
                except Exception as exc:
                    stt_error = f"{type(exc).__name__}: {exc}"[:200]
            row = {
                "case": name, "text": text, "bytes": len(pcm),
                "duration_s": round(duration, 3), "rms": round(_rms(pcm), 1),
                "transcript": transcript, "stt_error": stt_error, "errors": result["errors"],
            }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))

    by_case = {row["case"]: row for row in rows}
    comparisons = {}
    for tagged, control in (("B_excited", "A_neutral"), ("D_pauses", "E_control_plain"),
                            ("F_slow", "G_control_fast"), ("B_excited", "C_control_spoken_tag")):
        t, c = by_case.get(tagged), by_case.get(control)
        if t and c and t["duration_s"] and c["duration_s"]:
            comparisons[f"{tagged}_vs_{control}"] = round(t["duration_s"] / c["duration_s"], 3)

    (HERE / "probe_gnani_tags_ws.json").write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                    "model": MODEL, "voice": VOICE, "language": LANGUAGE,
                    "rows": rows, "duration_ratios": comparisons},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("ratios:", comparisons)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
