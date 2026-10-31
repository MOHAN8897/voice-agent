"""TEST 4 — TTS → local 16 kHz PCM (no Telnyx WebSocket).

Validates merge_pstn_tts_config, frame chunkers, and live Sarvam/Cartesia TTS when API keys exist.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.audio_transcode import chunk_pcm16_frames
from server.services.telnyx_client import TELNYX_RTP_CODEC, TELNYX_RTP_SAMPLE_RATE
from server.services.telnyx_pstn_bridge import _chunk_l16_rtp
from server.services.tts_config import merge_pstn_tts_config

TELNYX_FRAME_BYTES = int(TELNYX_RTP_SAMPLE_RATE * 20 / 1000) * 2
TEST_PHRASE = "Namaste! Nenu Priya, SKM Plants nundi matladutunnanu."


def _gate_results() -> dict[str, bool]:
    return {}


def gate_config_sarvam() -> tuple[bool, dict]:
    cfg = merge_pstn_tts_config("test-4", call_id=None, ws_model="bulbul:v3", wire_mode="rtp_l16")
    ok = (
        cfg.get("output_audio_codec") == "linear16"
        and cfg.get("speech_sample_rate") == "16000"
        and cfg.get("provider") == "sarvam"
    )
    return ok, cfg


def gate_config_cartesia() -> tuple[bool, dict | None]:
    from server.services.tts_config import _cartesia_available

    if not _cartesia_available():
        return True, None  # skipped — not required when Cartesia off
    voice = "4418bb06-8329-49a1-bb11-53bb64ca0547"
    cfg = merge_pstn_tts_config(
        "test-4",
        {"speaker": voice},
        call_id=None,
        ws_model="sonic-3.5",
        wire_mode="rtp_l16",
    )
    ok = (
        cfg.get("provider") == "cartesia"
        and cfg.get("output_audio_codec") == "linear16"
        and cfg.get("speech_sample_rate") == "16000"
        and cfg.get("sample_rate") == 16000
    )
    return ok, cfg


def gate_offline_chunkers() -> bool:
    pcm = b"\x00\x01" * (TELNYX_FRAME_BYTES // 2 + 100)
    a = chunk_pcm16_frames(pcm, sample_rate=TELNYX_RTP_SAMPLE_RATE)
    b = _chunk_l16_rtp(pcm, sample_rate=TELNYX_RTP_SAMPLE_RATE)
    if a != b:
        return False
    return all(len(f) == TELNYX_FRAME_BYTES for f in a)


def _validate_pcm_frames(pcm: bytes, label: str) -> bool:
    frames = chunk_pcm16_frames(pcm, sample_rate=TELNYX_RTP_SAMPLE_RATE)
    bad = [len(f) for f in frames if len(f) != TELNYX_FRAME_BYTES]
    duration_s = len(pcm) / (TELNYX_RTP_SAMPLE_RATE * 2)
    print(f"{label} PCM16: {len(pcm)} bytes ({duration_s:.2f}s)")
    print(f"{label} RTP frames: {len(frames)} (bad sizes: {bad[:5] or 'none'})")
    ok = bool(frames) and not bad
    print(f"{label} alignment: {'OK' if ok else 'FAIL'}")
    return ok


def _write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TELNYX_RTP_SAMPLE_RATE)
        w.writeframes(pcm)


async def _sarvam_live_tts(cfg: dict) -> tuple[bool, bytes]:
    from server.config.env import get_settings
    from server.services.sarvam_ws import connect_tts_ws

    if not (get_settings().sarvam_api_key or "").strip():
        print("Sarvam live TTS: SKIP (no SARVAM_API_KEY)")
        return True, b""

    payload = {k: v for k, v in cfg.items() if k not in {"provider", "model"}}
    pcm = bytearray()
    async with connect_tts_ws(model="bulbul:v3") as ws:
        await ws.send(json.dumps({"type": "config", "data": payload}))
        await ws.send(json.dumps({"type": "text", "data": {"text": TEST_PHRASE}}))
        await ws.send(json.dumps({"type": "flush"}))
        async for raw in ws:
            obj = json.loads(raw if isinstance(raw, str) else raw.decode())
            msg_type = obj.get("type") or obj.get("event") or ""
            if msg_type in ("event", "completion", "end", "done", "end_of_stream"):
                break
            data = obj.get("data")
            b64 = data.get("audio") if isinstance(data, dict) else obj.get("audio")
            if b64:
                pcm.extend(base64.b64decode(b64))

    if not pcm:
        print("Sarvam live TTS: FAIL (no audio bytes)")
        return False, b""

    ok = _validate_pcm_frames(bytes(pcm), "Sarvam")
    _write_wav(ROOT / "data" / "diag_telnyx_l16_sarvam.wav", bytes(pcm))
    print(f"Wrote {ROOT / 'data' / 'diag_telnyx_l16_sarvam.wav'}")
    return ok, bytes(pcm)


async def _cartesia_live_tts(cfg: dict) -> tuple[bool, bytes]:
    from server.services.cartesia_tts_ws import connect_cartesia_tts_ws
    from server.services.tts_config import _cartesia_available

    if not _cartesia_available():
        print("Cartesia live TTS: SKIP (disabled or no CARTESIA_API_KEY)")
        return True, b""

    pcm = bytearray()
    async with connect_cartesia_tts_ws(model=cfg.get("model") or "sonic-3.5") as ws:
        await ws.send(json.dumps({"type": "config", "data": {k: v for k, v in cfg.items() if k != "provider"}}))
        await ws.send(json.dumps({"type": "text", "data": {"text": TEST_PHRASE}}))
        await ws.send(json.dumps({"type": "flush"}))
        async for raw in ws:
            obj = json.loads(raw if isinstance(raw, str) else raw.decode())
            msg_type = obj.get("type") or ""
            if msg_type == "end_of_stream":
                break
            if msg_type == "error":
                print("Cartesia live TTS: FAIL", obj.get("message"))
                return False, b""
            data = obj.get("data")
            b64 = data.get("audio") if isinstance(data, dict) else None
            if b64:
                pcm.extend(base64.b64decode(b64))

    if not pcm:
        print("Cartesia live TTS: FAIL (no audio bytes)")
        return False, b""

    ok = _validate_pcm_frames(bytes(pcm), "Cartesia")
    _write_wav(ROOT / "data" / "diag_telnyx_l16_cartesia.wav", bytes(pcm))
    print(f"Wrote {ROOT / 'data' / 'diag_telnyx_l16_cartesia.wav'}")
    return ok, bytes(pcm)


async def main() -> int:
    parser = argparse.ArgumentParser(description="TEST 4 — local PSTN TTS @ 16 kHz L16")
    parser.add_argument("--skip-live", action="store_true", help="Offline gates only (no TTS API calls)")
    args = parser.parse_args()

    print("Telnyx wire:", TELNYX_RTP_CODEC, f"@ {TELNYX_RTP_SAMPLE_RATE} Hz", f"({TELNYX_FRAME_BYTES} B / 20 ms)")
    print()

    gates: dict[str, bool] = {}

    sarvam_cfg_ok, sarvam_cfg = gate_config_sarvam()
    gates["config_sarvam_l16_16k"] = sarvam_cfg_ok
    print("Sarvam PSTN config:", json.dumps({k: sarvam_cfg[k] for k in ("provider", "output_audio_codec", "speech_sample_rate") if k in sarvam_cfg}))

    cartesia_cfg_ok, cartesia_cfg = gate_config_cartesia()
    gates["config_cartesia_l16_16k"] = cartesia_cfg_ok
    if cartesia_cfg:
        print(
            "Cartesia PSTN config:",
            json.dumps({k: cartesia_cfg[k] for k in ("provider", "output_audio_codec", "speech_sample_rate", "sample_rate") if k in cartesia_cfg}),
        )
    else:
        print("Cartesia PSTN config: SKIP (not enabled)")

    gates["offline_chunkers_640b"] = gate_offline_chunkers()
    print("Offline chunkers (640 B):", "OK" if gates["offline_chunkers_640b"] else "FAIL")
    print()

    if not args.skip_live:
        sarvam_ok, _ = await _sarvam_live_tts(sarvam_cfg)
        gates["sarvam_live_tts"] = sarvam_ok
        print()
        if cartesia_cfg:
            cartesia_ok, _ = await _cartesia_live_tts(cartesia_cfg)
            gates["cartesia_live_tts"] = cartesia_ok
        else:
            gates["cartesia_live_tts"] = True
    else:
        gates["sarvam_live_tts"] = True
        gates["cartesia_live_tts"] = True
        print("Live TTS: skipped (--skip-live)")

    print()
    print("TEST 4 gate:")
    for key, passed in gates.items():
        print(f"  {'PASS' if passed else 'FAIL'}: {key}")
    overall = all(gates.values())
    print("overall:", "PASS" if overall else "FAIL")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
