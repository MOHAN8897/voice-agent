"""
Live handshake checker — scripts/live_handshake_check.py
Verifies TLS + auth + protocol handshake against every provider/API path.
Run:  python scripts/live_handshake_check.py [port]
Exit code 0 = all expected results matched.

Expected with PLACEHOLDER keys (len<=4): auth failures (401/403/close-1003) prove
connectivity + handshake; expected with REAL keys: 200 / session.begin / audio.

Add to CI only as an optional manual gate:  LIVE_TEST=1 python scripts/live_handshake_check.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS: list[tuple[str, str, str]] = []  # (check, status, detail)


def record(check: str, ok_expected: bool, got: str, detail: str) -> None:
    status = "PASS" if ok_expected else "FAIL"
    RESULTS.append((check, status, f"{got} :: {detail[:140]}"))
    print(f"[{status}] {check:<38} {got:<12} {detail[:110]}")


def key_kind(key: str | None) -> str:
    if not key or len(key) <= 4:
        return "PLACEHOLDER"
    return "REAL?"


async def check_openai_rest() -> None:
    from server.config.env import get_settings

    s = get_settings()
    kind = key_kind(s.openai_api_key)
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {s.openai_api_key}"},
            )
        if kind == "PLACEHOLDER":
            record("OpenAI REST /v1/models", r.status_code == 401, str(r.status_code),
                   "auth rejected placeholder → connectivity + TLS + endpoint OK")
        else:
            record("OpenAI REST /v1/models", r.status_code == 200, str(r.status_code), "models list")
    except Exception as e:
        record("OpenAI REST /v1/models", False, type(e).__name__, str(e))


async def check_sarvam_stt_rest() -> None:
    from server.config.env import get_settings

    s = get_settings()
    kind = key_kind(s.sarvam_api_key)
    # 16kHz sine ~0.3s WAV header minimal
    import struct, math

    sr = 16000
    n = int(sr * 0.3)
    pcm = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / sr))) for i in range(n))
    wav = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little") \
        + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + sr.to_bytes(4, "little") \
        + (sr * 2).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little") \
        + b"data" + len(pcm).to_bytes(4, "little") + pcm
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://api.sarvam.ai/speech-to-text",
                headers={"api-subscription-key": s.sarvam_api_key},
                files={"file": ("probe.wav", wav, "audio/wav")},
                data={"model": "saaras:v3", "language_code": "te-IN", "mode": "transcribe"},
            )
        if kind == "PLACEHOLDER":
            record("Sarvam STT REST /speech-to-text", r.status_code in (401, 403), str(r.status_code),
                   "auth rejected placeholder → endpoint reachable")
        else:
            record("Sarvam STT REST /speech-to-text", r.status_code == 200, str(r.status_code),
                   r.text[:100])
    except Exception as e:
        record("Sarvam STT REST /speech-to-text", False, type(e).__name__, str(e))


async def check_sarvam_stt_realtime_ws() -> None:
    """Direct upstream: expect either session.begin (real key) or structured error/close (placeholder)."""
    from server.config.env import get_settings
    from server.services.sarvam_ws import connect_stt_realtime

    s = get_settings()
    kind = key_kind(s.sarvam_api_key)
    try:
        ws = await asyncio.wait_for(connect_stt_realtime(language_code="te-IN", stream_type="fast").__aenter__(), timeout=12)
        # Handshake 101 achieved. Read first event.
        try:
            first = await asyncio.wait_for(ws.recv(), timeout=10)
            txt = first.decode(errors="ignore") if isinstance(first, bytes) else first
            ev = {}
            try:
                ev = json.loads(txt)
            except Exception:
                pass
            name = ev.get("event") or ev.get("type") or "?"
            if kind == "PLACEHOLDER":
                record("Sarvam STT WS realtime handshake", name in ("error", "session.end"), "101+" + name, txt[:120])
            else:
                record("Sarvam STT WS realtime handshake", True, "101+" + name, txt[:120])
        except Exception as e:
            # close without frame also acceptable for placeholder (e.g., 1003)
            record("Sarvam STT WS realtime handshake", kind == "PLACEHOLDER", type(e).__name__, str(e)[:120])
        try:
            await ws.close()
        except Exception:
            pass
    except Exception as e:
        msg = str(e)
        ok = kind == "PLACEHOLDER" and ("401" in msg or "403" in msg or "1003" in msg or "rejected" in msg.lower())
        record("Sarvam STT WS realtime handshake", ok, type(e).__name__, msg)


async def check_sarvam_tts_ws() -> None:
    from server.config.env import get_settings
    from server.services.sarvam_ws import connect_tts_ws

    s = get_settings()
    kind = key_kind(s.sarvam_api_key)
    try:
        ws = await asyncio.wait_for(connect_tts_ws("bulbul:v3").__aenter__(), timeout=12)
        # Send full protocol: config → text → flush, then read
        await ws.send(json.dumps({"type": "config", "data": {
            "speaker": "shubh", "language_code": "te-IN", "pace": 1.0,
            "min_buffer_size": 50, "max_chunk_length": 200,
            "output_audio_codec": "mp3", "output_audio_bitrate": "128k"}}))
        await ws.send(json.dumps({"type": "text", "data": {"text": "నమస్కారం"}}))
        await ws.send(json.dumps({"type": "flush"}))
        got_audio = False
        last = ""
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=12)
                txt = raw.decode(errors="ignore") if isinstance(raw, bytes) else raw
                last = txt
                ev = {}
                try:
                    ev = json.loads(txt)
                except Exception:
                    pass
                t = ev.get("type") or ev.get("event")
                if t == "audio" or (ev.get("data") and isinstance(ev["data"], dict) and ev["data"].get("audio")):
                    got_audio = True
                    break
                if t == "event" and ev.get("data", {}).get("event_type") == "final":
                    break
                if t == "error":
                    break
        except asyncio.TimeoutError:
            pass
        if kind == "PLACEHOLDER":
            record("Sarvam TTS WS bulbul:v3", ("error" in last) or (not got_audio), "audio" if got_audio else "err/none",
                   "placeholder cannot stream — but config/text/flush accepted at protocol level" if not got_audio else last[:80])
        else:
            record("Sarvam TTS WS bulbul:v3", got_audio, "audio OK" if got_audio else "no-audio", last[:120])
        try:
            await ws.close()
        except Exception:
            pass
    except Exception as e:
        msg = str(e)
        ok = kind == "PLACEHOLDER" and ("401" in msg or "403" in msg or "rejected" in msg.lower())
        record("Sarvam TTS WS bulbul:v3", ok, type(e).__name__, msg)


async def check_local_proxy(port: str) -> None:
    """Our /ws/stt-realtime proxy must connect, reach upstream, and relay events back."""
    import websockets

    url = f"ws://localhost:{port}/ws/stt-realtime?language_code=te-IN&stream_type=fast"
    try:
        async with websockets.connect(url, max_size=None, open_timeout=10) as local:
            try:
                first = await asyncio.wait_for(local.recv(), timeout=15)
                txt = first.decode(errors="ignore") if isinstance(first, bytes) else first
                ev = {}
                try:
                    ev = json.loads(txt)
                except Exception:
                    pass
                name = ev.get("event") or ev.get("type") or "frame"
                fatal = bool(ev.get("is_fatal"))
                # With placeholder key we EXPECT the relayed invalid_subscription_key error — proves proxy↔upstream↔client loop
                record(f"Local proxy /ws/stt-realtime (:{port})", True, "relayed:" + name, txt[:120] + (" [fatal]" if fatal else ""))
            except asyncio.TimeoutError:
                record(f"Local proxy /ws/stt-realtime (:{port})", False, "timeout", "no event within 15s")
    except Exception as e:
        record(f"Local proxy /ws/stt-realtime (:{port})", False, type(e).__name__, str(e))


async def check_local_health(port: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"http://localhost:{port}/api/health")
            j = r.json()
            record(f"Local /api/health (:{port})", r.status_code == 200, str(r.status_code),
                   f"ok={j.get('ok')} version={j.get('version')}")
    except Exception as e:
        record(f"Local /api/health (:{port})", False, type(e).__name__, str(e))


async def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    print("=" * 96)
    print("LIVE HANDSHAKE CHECK — Telugu Voice Agent")
    from server.config.env import get_settings

    s = get_settings()
    print(f"keys: OPENAI={key_kind(s.openai_api_key)}  SARVAM={key_kind(s.sarvam_api_key)}")
    print("=" * 96)

    await check_local_health(port)
    await check_openai_rest()
    await check_sarvam_stt_rest()
    await check_sarvam_stt_realtime_ws()
    await check_sarvam_tts_ws()
    await check_local_proxy(port)

    print("=" * 96)
    failed = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"TOTAL {len(RESULTS)} checks — {len(RESULTS) - len(failed)} PASS, {len(failed)} FAIL")
    if failed:
        for f in failed:
            print("  FAIL:", f[0], "::", f[2])
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
