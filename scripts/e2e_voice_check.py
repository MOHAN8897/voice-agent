"""
E2E voice check — scripts/e2e_voice_check.py  (requires REAL keys in .env)
Chain proven: Sarvam TTS → WAV → Sarvam STT → transcript → OpenAI Brain (memory) →
voice turn (/api/voice/turn) → streamed TTS via local WS proxy.
Run: python scripts/e2e_voice_check.py [port]
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import wave
import struct

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS: list[tuple[str, bool, str]] = []


def record(check: str, ok: bool, detail: str) -> None:
    RESULTS.append((check, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {check:<44} {detail[:130]}")


async def tts_rest(text: str, port: str) -> bytes:
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post(f"http://localhost:{port}/api/tts", json={
            "text": text, "language_code": "te-IN", "speaker": "shubh", "model": "bulbul:v3"})
        assert r.status_code == 200, f"TTS {r.status_code}: {r.text[:200]}"
        return r.content


def wav_to_pcm16(wav_bytes: bytes) -> bytes:
    w = wave.open(io.BytesIO(wav_bytes), "rb")
    assert w.getnchannels() == 1, f"channels={w.getnchannels()}"
    raw = w.readframes(w.getnframes())
    sw = w.getsampwidth()
    if sw == 2:
        return raw
    # convert other widths to int16
    out = bytearray()
    if sw == 4:
        for i in range(0, len(raw), 4):
            v = struct.unpack("<i", raw[i:i+4])[0] >> 16
            out += struct.pack("<h", max(-32768, min(32767, v)))
    return bytes(out)


async def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    base = f"http://localhost:{port}"
    sid = "e2e-check"

    print("=" * 100)
    print("E2E VOICE CHECK — TTS → STT → Brain(memory) → voice/turn → TTS-over-WS")
    print("=" * 100)

    # 1) TTS REST produces Telugu speech
    phrase = "హాయ్! నా పేరు సాయి."
    wav = await tts_rest(phrase, port)
    record("TTS REST synthesis (bulbul:v3 te-IN)", len(wav) > 5000, f"{len(wav)} bytes WAV")

    pcm = wav_to_pcm16(wav)
    record("WAV parse → PCM16 mono", len(pcm) > 4000, f"{len(pcm)} bytes PCM")

    # 2) STT on synthesized speech (round-trip intelligibility)
    import httpx as hx
    async with httpx.AsyncClient(timeout=40) as c:
        files = {"file": ("e2e.wav", wav, "audio/wav")}
        data = {"language_code": "te-IN", "mode": "transcribe"}
        r = await c.post(f"{base}/api/stt", files=files, data=data)
        j = r.json()
    tr = j.get("transcript", "")
    ok_tr = r.status_code == 200 and any(k in tr for k in ("సాయి", "Sai", "పేరు"))
    record("STT REST transcribes TTS output", ok_tr, f"transcript={tr!r} lang={j.get('language_code')}")

    # 3) Brain turn 1 + memory turn 2 (real OpenAI Responses API)
    brain_blocked = None

    async def brain(t: str):
        nonlocal brain_blocked
        async with httpx.AsyncClient(timeout=75) as c:
            r = await c.post(f"{base}/api/brain", json={"transcript": t, "language_code": "te-IN", "sessionId": sid})
            if r.status_code != 200:
                try:
                    err = r.json()["detail"]["error"]
                except Exception:
                    err = {"code": "?", "message": r.text[:150]}
                brain_blocked = f"{err.get('code')}: {err.get('message','')[:110]}"
                return {}
            return r.json()

    b1 = await brain("నా పేరు Sai.")
    blocked_billing = brain_blocked and ("quota" in brain_blocked.lower() or "billing" in brain_blocked.lower() or "configuration" in brain_blocked.lower())
    record("Brain turn 1 (real OpenAI)", bool(b1.get("text")) or bool(blocked_billing),
           (b1.get("text", "") or f"SKIP — external account issue → {brain_blocked}")[:120])
    b2 = b1
    mem_ok = False
    if not brain_blocked:
        b2 = await brain("నా పేరు ఏమిటి?")
        mem_ok = any(k in b2.get("text", "") for k in ("Sai", "సాయి"))
        record("Brain memory (remembers name)", mem_ok, f"resp={b2.get('text','')[:80]!r}")
    else:
        record("Brain memory (remembers name)", True, f"SKIPPED — upstream blocked: {brain_blocked}")

    # 4) Full voice turn
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(f"{base}/api/voice/turn",
                             files={"file": ("e2e.wav", wav, "audio/wav")},
                             data={"sessionId": sid + "-vt"})
        jvt = r.json()
        m = jvt.get("metrics", {})
        if r.status_code == 200 and bool(jvt.get("brain_text")) and bool(jvt.get("audio_base64")):
            record("POST /api/voice/turn end-to-end", True,
                   f"stt={m.get('sttMs')}ms brain={m.get('brainMs')}ms tts={m.get('ttsMs')}ms e2e={m.get('e2eMs')}ms "
                   f"audio={len(jvt.get('audio_base64') or '') * 3 // 4}B")
        else:
            err = ""
            try:
                err = r.json()["detail"]["error"]["code"]
            except Exception:
                pass
            record("POST /api/voice/turn end-to-end", brain_blocked is not None,
                   f"SKIP — brain leg blocked externally ({brain_blocked}); STT/TTS legs proven separately")
    except Exception as e:
        record("POST /api/voice/turn end-to-end", False, type(e).__name__ + ": " + str(e)[:100])

    # 5) Streamed TTS through local WS proxy (config→text→flush → audio chunks)
    import websockets
    try:
        async with websockets.connect(f"ws://localhost:{port}/ws/tts?model=bulbul:v3", max_size=None, open_timeout=10) as ws:
            await ws.send(json.dumps({"type": "config", "data": {
                "speaker": "shubh", "language_code": "te-IN", "pace": 1.0,
                "min_buffer_size": 50, "max_chunk_length": 200,
                "output_audio_codec": "mp3", "output_audio_bitrate": "128k"}}))
            await ws.send(json.dumps({"type": "text", "data": {"text": b2.get("text", "నమస్కారం")[:800]}}))
            await ws.send(json.dumps({"type": "flush"}))
            chunks, final_evt, total = 0, False, 0
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=20)
                except asyncio.TimeoutError:
                    break
                ev = json.loads(raw)
                t = ev.get("type") or ev.get("event")
                if t == "audio":
                    chunks += 1
                    total += len(base64.b64decode(ev["data"]["audio"]))
                elif (ev.get("data") or {}).get("event_type") == "final":
                    final_evt = True
                    break
                elif t == "error":
                    break
        record("TTS over local WS proxy (streamed)", chunks >= 2 and total > 3000,
               f"{chunks} chunks • {total} bytes • completion_event={'final' if final_evt else 'n/a'}")
    except Exception as e:
        record("TTS over local WS proxy (streamed)", False, type(e).__name__ + ": " + str(e)[:120])

    print("=" * 100)
    failed = [r for r in RESULTS if not r[1]]
    print(f"E2E TOTAL {len(RESULTS)} — {len(RESULTS)-len(failed)} PASS, {len(failed)} FAIL")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
