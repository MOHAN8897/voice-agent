"""Generate the pre-recorded technical-failure clips shipped with the server.

The runtime fallback must not depend on TTS: it plays one of these clips when the
configured speech service fails mid-call. Clips are laid out as::

    server/static/audio/fallback/{variant}/{gender}/{language}.wav

``variant`` is ``callback_promise`` ("we will call you again", only played after
a callback task is committed), ``call_back`` ("please call us back") or
``disclosure`` (recording notice, played first when it was never delivered).
Regenerate after changing the wording or adding a language:

    python -m scripts.generate_fallback_audio --force

Requires SARVAM_API_KEY. The clips are ordinary project assets; no key is written.
Translations live in ``server/services/pstn_technical_fallback.py`` so the
recorded audio and the transcript ledger can never drift apart.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import time
import wave
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "server" / "static" / "audio" / "fallback"

SARVAM_URL = "https://api.sarvam.ai/text-to-speech"
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2
CHANNELS = 1

#: bulbul:v3 speakers; keep one voice per gender for the whole library.
VOICES: dict[str, str] = {"male": "shubh", "female": "ritu"}


def fallback_texts() -> dict[str, dict[str, str]]:
    from server.services.pstn_technical_fallback import CLIP_VARIANTS, FALLBACK_TEXT

    return {variant: FALLBACK_TEXT[variant] for variant in CLIP_VARIANTS}


def _synthesize(text: str, language: str, speaker: str, api_key: str) -> bytes:
    body = {
        "text": text,
        "target_language_code": language,
        "speaker": speaker,
        "model": "bulbul:v3",
        "output_audio_codec": "wav",
        "speech_sample_rate": SAMPLE_RATE,
    }
    with httpx.Client(timeout=45.0, follow_redirects=False) as client:
        response = client.post(
            SARVAM_URL,
            content=json.dumps(body).encode("utf-8"),
            headers={"api-subscription-key": api_key, "Content-Type": "application/json"},
        )
    response.raise_for_status()
    payload = response.json()
    audios = payload.get("audios") or []
    if not audios:
        raise RuntimeError(f"TTS returned no audio for {language}: {str(payload)[:200]}")
    return base64.b64decode(audios[0])


def _normalize_wav(raw: bytes) -> bytes:
    """Force mono 8 kHz 16-bit PCM so any carrier wire format can be derived."""
    with wave.open(io.BytesIO(raw), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())
    if (
        params.nchannels == CHANNELS
        and params.sampwidth == SAMPLE_WIDTH
        and params.framerate == SAMPLE_RATE
    ):
        return raw
    if params.sampwidth != SAMPLE_WIDTH:
        raise RuntimeError(f"unexpected sample width {params.sampwidth}; expected 16-bit")
    if params.nchannels != CHANNELS:
        raise RuntimeError(f"unexpected channel count {params.nchannels}; expected mono")
    from server.services.audio_transcode import pcm_resample

    resampled = pcm_resample(frames, params.framerate, SAMPLE_RATE)
    out = io.BytesIO()
    with wave.open(out, "wb") as target:
        target.setnchannels(CHANNELS)
        target.setsampwidth(SAMPLE_WIDTH)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(resampled)
    return out.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite existing clips")
    parser.add_argument("--language", action="append", help="limit to one or more language codes")
    parser.add_argument("--variant", action="append", help="limit to one or more clip variants")
    parser.add_argument("--gender", action="append", help="limit to one or more voices")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("SARVAM_API_KEY", "").strip()
    if not api_key:
        print("SARVAM_API_KEY is not configured")
        return 2

    texts = fallback_texts()
    variants = args.variant or list(texts)
    genders = args.gender or list(VOICES)
    unknown_variant = [variant for variant in variants if variant not in texts]
    unknown_gender = [gender for gender in genders if gender not in VOICES]
    if unknown_variant or unknown_gender:
        print(f"unknown variant/gender: {unknown_variant or unknown_gender}")
        return 2

    failures = 0
    for variant in variants:
        for gender in genders:
            directory = OUTPUT_DIR / variant / gender
            directory.mkdir(parents=True, exist_ok=True)
            languages = args.language or list(texts[variant])
            for language in languages:
                text = texts[variant].get(language)
                if not text:
                    print(f"{variant}/{gender}/{language}: no prepared translation")
                    failures += 1
                    continue
                target = directory / f"{language}.wav"
                if target.exists() and not args.force:
                    print(f"{variant}/{gender}/{language}: exists ({target.name})")
                    continue
                for attempt in range(3):
                    try:
                        audio = _normalize_wav(
                            _synthesize(text, language, VOICES[gender], api_key)
                        )
                        target.write_bytes(audio)
                        print(f"{variant}/{gender}/{language}: wrote {target.name} ({len(audio)} bytes)")
                        break
                    except (httpx.HTTPError, TimeoutError, ValueError, RuntimeError) as exc:
                        if attempt == 2:
                            failures += 1
                            print(f"{variant}/{gender}/{language}: failed ({type(exc).__name__}: {str(exc)[:160]})")
                        else:
                            time.sleep(1.5 * (attempt + 1))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
