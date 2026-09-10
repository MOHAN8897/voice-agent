"""Synthesize a short PSTN greeting without dialing a phone or changing settings.

Run from the repo root: python -m scripts.check_pstn_tts --session test-studio
Uses the session's selected voice and configured provider fallback.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import wave
from pathlib import Path

from server.services.pstn_prewarm import _PrewarmVoiceStub
from server.services.pstn_turn_tts import PstnTurnTtsSession


async def check(session_id: str) -> None:
    voice = _PrewarmVoiceStub(
        session_id=session_id, call_id="pstn-tts-diagnostic", sample_rate=16000,
        tts_output_codec="linear16", language="te-IN",
    )
    providers = []
    for text in ("నమస్కారం, మీకు ఎలా సహాయం చేయగలను?", "దయచేసి మీకు కావలసిన వివరాలు చెప్పండి."):
        session = PstnTurnTtsSession(voice)
        try:
            await session.open()
            await session.send_text(text)
            await session.finish()
            if session.had_error or not session.audio_emitted:
                raise RuntimeError("TTS returned no usable speech")
            providers.append(session._merged["provider"])
        finally:
            await session.close()
    if not voice.frames or any(len(frame) != 640 for frame in voice.frames):
        raise RuntimeError("Invalid 16 kHz / 20 ms PSTN audio framing")
    pcm = b"".join(voice.frames)
    out = Path("data/pstn-tts-diagnostic.wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    print(json.dumps({"ok": True, "providers": providers, "frames": len(voice.frames),
                      "audio_seconds": len(pcm) / 32000, "audio_file": str(out)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="test-studio")
    args = parser.parse_args()
    asyncio.run(asyncio.wait_for(check(args.session), timeout=50))
