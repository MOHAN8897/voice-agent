"""Record multilingual voice samples using Gemini 3.8 Live (gemini-3.8-live).

Generates high-fidelity WAV samples for core voices across:
- Telugu (te-IN)
- Hindi (hi-IN)
- Tamil (ta-IN)
- Kannada (kn-IN)
- English (en-IN / en-US)

Files are written to both:
- dialtact-app/public/audio/dialtact/samples/
- web/public/audio/dialtact/samples/

Naming convention:
- {voice_id}_{lang}.wav (e.g. aoede_te.wav, puck_te.wav, kore_hi.wav, etc.)
- Aliases for OpenAI slugs (marin_te.wav, cedar_te.wav, etc.) are mirrored.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fix Windows console encoding
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from server.realtime.models import DEFAULT_GEMINI_LIVE_MODEL
from server.realtime.providers.gemini_voice import (
    GEMINI_LIVE_OUTPUT_RATE,
    GeminiLiveVoiceAdapter,
)

DIALTACT_SAMPLES_DIR = REPO_ROOT / "dialtact-app" / "public" / "audio" / "dialtact" / "samples"
WEB_SAMPLES_DIR = REPO_ROOT / "web" / "public" / "audio" / "dialtact" / "samples"

# Core Gemini Live voices to generate samples for:
CORE_VOICES = (
    ("Aoede", "female", "Warm & conversational", "support"),
    ("Kore", "female", "Firm & professional", "operations"),
    ("Leda", "female", "Youthful & cheerful", "support"),
    ("Zephyr", "female", "Bright & clear", "sales"),
    ("Puck", "male", "Upbeat & engaging", "sales"),
    ("Charon", "male", "Informative & steady", "operations"),
    ("Fenrir", "male", "Excitable & dynamic", "sales"),
    ("Orus", "male", "Firm & grounded", "operations"),
)

# OpenAi slugs mapped to Gemini core voices:
OPENAI_ALIASES = {
    "marin": "aoede",
    "cedar": "charon",
    "alloy": "kore",
    "ash": "orus",
    "ballad": "puck",
    "coral": "aoede",
    "echo": "fenrir",
    "sage": "kore",
    "shimmer": "leda",
    "verse": "puck",
}

LANGUAGES = {
    "te": {
        "code": "te-IN",
        "name": "Telugu",
        "prompt": "You are a warm, professional voice assistant speaking in natural Telugu. Say exactly this sentence once without any introductory words or English: 'నమస్కారం! నేను మీ వాయిస్ అసిస్టెంట్‌ని. మీకు ఈరోజు ఎలా సహాయం చేయగలను?'",
    },
    "hi": {
        "code": "hi-IN",
        "name": "Hindi",
        "prompt": "You are a warm, professional voice assistant speaking in natural Hindi. Say exactly this sentence once without any introductory words or English: 'नमस्ते! मैं आपका वॉइस असिस्टेंट हूँ। आज मैं आपकी क्या मदद कर सकता हूँ?'",
    },
    "ta": {
        "code": "ta-IN",
        "name": "Tamil",
        "prompt": "You are a warm, professional voice assistant speaking in natural Tamil. Say exactly this sentence once without any introductory words or English: 'வணக்கம்! நான் உங்கள் வாய்ஸ் அசிஸ்டண்ட். இன்று உங்களுக்கு எப்படி உதவலாம்?'",
    },
    "kn": {
        "code": "kn-IN",
        "name": "Kannada",
        "prompt": "You are a warm, professional voice assistant speaking in natural Kannada. Say exactly this sentence once without any introductory words or English: 'ನಮಸ್ಕಾರ! ನಾನು ನಿಮ್ಮ ಧ್ವನಿ ಸಹಾಯಕ. ಇಂದು ನಾನು మీకు ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?'",
    },
    "en": {
        "code": "en-IN",
        "name": "English",
        "prompt": "You are a warm, professional voice assistant speaking in clear, natural English. Say exactly this sentence once without any introductory words: 'Hello! I am your voice assistant. How can I help you today?'",
    },
}


def _write_wav(path: Path, pcm: bytes, sample_rate: int) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm)
    return len(pcm) / 2 / sample_rate


async def record_sample(
    voice: str,
    lang_key: str,
    api_key: str,
    *,
    force: bool = False,
    timeout_s: float = 20.0,
    max_retries: int = 3,
) -> bool:
    filename = f"{voice.lower()}_{lang_key}.wav"
    target_dialtact = DIALTACT_SAMPLES_DIR / filename
    target_web = WEB_SAMPLES_DIR / filename

    if target_dialtact.exists() and target_dialtact.stat().st_size > 4000 and not force:
        print(f"  = [EXISTS] {filename} ({target_dialtact.stat().st_size // 1024} KB)")
        if not target_web.exists() or target_web.stat().st_size != target_dialtact.stat().st_size:
            shutil.copy2(target_dialtact, target_web)
        return True

    lang_info = LANGUAGES[lang_key]
    prompt_instruction = lang_info["prompt"]

    for attempt in range(1, max_retries + 1):
        adapter = GeminiLiveVoiceAdapter(api_key=api_key)
        chunks: list[bytes] = []
        try:
            await asyncio.wait_for(
                adapter.connect(
                    model=DEFAULT_GEMINI_LIVE_MODEL,
                    instructions=f"You are a native {lang_info['name']} voice assistant. Speak conversationally and authentically.",
                    voice=voice,
                    include_tools=False,
                    turn_detection="server_vad",
                    max_output_tokens=320,
                ),
                timeout=timeout_s,
            )
            await adapter.wait_ready(timeout=timeout_s)
            adapter.opening_history_clean = False
            await adapter.start_response(instructions=prompt_instruction)

            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_s
            while loop.time() < deadline:
                event = await adapter.poll_event(timeout=4.0)
                if not event:
                    continue
                kind = event.get("type")
                if kind == "audio_delta":
                    pcm = event.get("pcm")
                    if pcm:
                        chunks.append(bytes(pcm))
                elif kind == "error":
                    print(f"    ! Live session error ({voice}, {lang_key}): {event.get('message')}")
                    break
                elif kind == "response_done" and not event.get("usage_only"):
                    break
                elif kind == "_stream_end":
                    break
            await asyncio.sleep(0.3)
        except Exception as exc:
            print(f"    ! Attempt {attempt} failed ({voice}, {lang_key}): {exc}")
            if attempt < max_retries:
                await asyncio.sleep(1.5 * attempt)
                continue
        finally:
            try:
                await adapter.close()
            except Exception:
                pass

        pcm = b"".join(chunks)
        # Verify valid audio (> 1 second of speech)
        if len(pcm) >= GEMINI_LIVE_OUTPUT_RATE * 2:
            seconds = _write_wav(target_dialtact, pcm, GEMINI_LIVE_OUTPUT_RATE)
            shutil.copy2(target_dialtact, target_web)
            print(f"  + [RECORDED] {filename} ({seconds:.2f}s, {target_dialtact.stat().st_size // 1024} KB)")
            return True
        else:
            print(f"    ! Incomplete audio ({len(pcm)} bytes) on attempt {attempt}")
            if attempt < max_retries:
                await asyncio.sleep(1.5 * attempt)

    return False


def copy_aliases():
    """Copy or create OpenAI alias samples (marin_te.wav -> aoede_te.wav, etc.)."""
    for lang_key in LANGUAGES:
        for alias, base_voice in OPENAI_ALIASES.items():
            src_name = f"{base_voice}_{lang_key}.wav"
            dst_name = f"{alias}_{lang_key}.wav"
            src_path = DIALTACT_SAMPLES_DIR / src_name
            dst_dialtact = DIALTACT_SAMPLES_DIR / dst_name
            dst_web = WEB_SAMPLES_DIR / dst_name
            if src_path.exists():
                shutil.copy2(src_path, dst_dialtact)
                shutil.copy2(src_path, dst_web)
                print(f"  ~ [ALIAS] {dst_name} -> {src_name}")


async def main():
    parser = argparse.ArgumentParser(description="Record multilingual voice samples using Gemini 3.8 Live.")
    parser.add_argument("--force", action="store_true", help="Force re-recording of existing samples")
    parser.add_argument("--voice", type=str, default="", help="Record only specific voice (e.g. Aoede)")
    parser.add_argument("--lang", type=str, default="", help="Record only specific language (e.g. te)")
    args = parser.parse_args()

    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        print("ERROR: GEMINI_API_KEY is not set.")
        sys.exit(1)

    DIALTACT_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    WEB_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    target_voices = [v for v in CORE_VOICES if not args.voice or v[0].lower() == args.voice.lower()]
    target_langs = [l for l in LANGUAGES if not args.lang or l == args.lang.lower()]

    print(f"Recording {len(target_voices)} voices across {len(target_langs)} languages with Gemini 3.8 Live...")

    success_count = 0
    total_count = len(target_voices) * len(target_langs)

    for voice_meta in target_voices:
        voice_name = voice_meta[0]
        for lang_key in target_langs:
            ok = await record_sample(voice_name, lang_key, key, force=args.force)
            if ok:
                success_count += 1
            # Brief delay between websocket connections
            await asyncio.sleep(0.5)

    print(f"\nRecording completed: {success_count}/{total_count} files ready.")
    print("Generating OpenAI alias files...")
    copy_aliases()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
