"""Live TTS check per provider x language: does it synthesize, and how does it say numbers?

Each sentence is synthesized twice: as the model writes it (digits) and after the
current pre-TTS rewrite (prepare_spoken_reply). The audio is transcribed back with
Sarvam STT so a reviewer can hear, in text, what the caller would actually hear.

  python -m server.eval.conversation_sim.tts_smoke --providers all --langs all
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

from server.eval.conversation_sim.environment import ARTIFACTS, write_json

SENTENCES = {
    "te-IN": "Split AC servicing కి ₹599 అవుతుంది, technician రేపు 10:30 AM కి వస్తారు.",
    "hi-IN": "Split AC servicing का चार्ज ₹599 है, technician कल 10:30 AM आएंगे.",
    "ta-IN": "Split AC servicing-க்கு ₹599 ஆகும், technician நாளைக்கு 10:30 AM வருவாங்க.",
    "kn-IN": "Split AC servicing ಗೆ ₹599 ಆಗುತ್ತೆ, technician ನಾಳೆ 10:30 AM ಗೆ ಬರ್ತಾರೆ.",
    "en-IN": "Split AC servicing is ₹599, and the technician can come tomorrow at 10:30 AM.",
    "gu-IN": "Split AC servicing નો ચાર્જ ₹599 છે, technician કાલે 10:30 AM આવશે.",
    "ml-IN": "Split AC servicing-ന് ₹599 ആകും, technician നാളെ 10:30 AM വരും.",
}
PROVIDERS = {
    "sarvam": ("bulbul:v3", "shubh"),
    "gemini": ("gemini-3.8-flash-tts", "Kore"),
    "cartesia": ("sonic-3.5", ""),
    "gnani": ("timbre-v3.0", "Shivani"),
}


def _duration(audio: bytes) -> float | None:
    try:
        with wave.open(io.BytesIO(audio)) as w:
            frames, rate, width, channels = w.getnframes(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        if frames >= 0x7FFFFFFF // max(width * channels, 1):
            # Streamed WAV headers carry a placeholder length; measure the payload.
            frames = (len(audio) - 44) // (width * channels)
        return round(frames / float(rate), 2)
    except Exception:
        return None


async def one(provider: str, language: str, text: str) -> dict:
    from server.providers import get_provider_registry
    from server.providers.base import STTConfig, TTSConfig

    registry = get_provider_registry()
    from server.providers.voice_inventory import default_voice

    model, preferred = PROVIDERS[provider]
    # The same language-aware catalog choice the runtime makes when no voice is pinned.
    speaker = default_voice(provider, model, language, preferred=preferred or None)
    row: dict = {"provider": provider, "model": model, "voice": speaker, "language": language, "text": text}
    started = time.monotonic()
    try:
        audio = await asyncio.wait_for(registry.get_tts(provider).synthesize_rest(
            text, TTSConfig(provider=provider, model=model, language=language, speaker=speaker)), timeout=60)
        row.update(bytes=len(audio), seconds=_duration(audio), latency_s=round(time.monotonic() - started, 2))
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        return row
    if not audio:
        row["error"] = "empty_audio"
        return row
    try:
        heard = await asyncio.wait_for(registry.get_stt("sarvam").transcribe_rest(
            audio, STTConfig(provider="sarvam", model="saaras:v3", language=language, mode="rest")), timeout=60)
        row["heard"] = heard.text
    except Exception as exc:
        row["stt_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return row


async def run(args) -> int:
    from server.db import connection
    from server.services.spoken_numbers import prepare_spoken_reply
    from server.config.env import get_settings
    from server.services.dev_secrets_store import dev_secrets_store

    if args.sarvam_key_source == "env":
        from server.eval.conversation_sim.environment import use_env_sarvam_key
        use_env_sarvam_key()
    settings = get_settings()
    for key in ("sarvam_api_key", "gemini_api_key", "cartesia_api_key", "gnani_api_key"):
        value = dev_secrets_store.effective_secret(key)
        if value and hasattr(settings, key):
            setattr(settings, key, value)
    await connection.init_db()
    providers = list(PROVIDERS) if args.providers == "all" else args.providers.split(",")
    languages = list(SENTENCES) if args.langs == "all" else args.langs.split(",")
    jobs = []
    for provider in providers:
        model = PROVIDERS[provider][0]
        for lang in languages:
            raw = SENTENCES[lang]
            jobs.append((provider, lang, "raw_digits", raw))
            prepared = prepare_spoken_reply(raw, provider=provider, model=model)
            if prepared != raw:
                jobs.append((provider, lang, "pipeline_prepared", prepared))
    # Providers rate-limit concurrent synthesis (Gnani allows one request at a time),
    # so each provider runs sequentially while different providers run side by side.
    async def provider_lane(name):
        lane = []
        for provider, lang, variant, text in jobs:
            if provider != name:
                continue
            row = await one(provider, lang, text)
            if "429" in str(row.get("error")):
                await asyncio.sleep(8)
                row = await one(provider, lang, text)
            row["variant"] = variant
            print(json.dumps(row, ensure_ascii=False), flush=True)
            lane.append(row)
        return lane

    rows = [row for lane in await asyncio.gather(*(provider_lane(p) for p in providers)) for row in lane]
    out = Path(args.out) if args.out else ARTIFACTS / f"tts-smoke-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    write_json(out / "tts_smoke.json", rows)
    lines = ["# TTS smoke", "", "| Provider | Lang | Variant | Audio s | Heard back (Sarvam STT) | Error |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['provider']} | {r['language']} | {r['variant']} | {r.get('seconds')} | "
                     f"{(r.get('heard') or '').replace('|', '/')} | {r.get('error') or r.get('stt_error') or ''} |")
    (out / "tts_smoke.md").write_text("\n".join(lines), encoding="utf-8")
    await connection.close_db()
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", default="all")
    parser.add_argument("--langs", default="all")
    parser.add_argument("--out")
    parser.add_argument("--sarvam-key-source", choices=("runtime", "env"), default="runtime")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
