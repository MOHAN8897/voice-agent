"""Record the marketing voice samples with the live speech model.

The landing page used to demo itself with `window.speechSynthesis` plus a hard-coded
array of replies. That is the browser's built-in voice, not the product's: it sounds
flat, it is unavailable on some platforms, and it proves nothing about the pipeline the
page is selling. These clips are rendered by the same live speech model that answers a
real call (`gemini-3.8-live`), so what a visitor hears is the product.

One line per business vertical, because the pitch is "your industry, not a generic
assistant". Each clip is fetched only when the visitor presses play.

    .venv\\Scripts\\python.exe -m scripts.record_marketing_voice_samples
    # or
    .venv\\Scripts\\python.exe scripts/record_marketing_voice_samples.py

Re-running only records what is missing; pass --force to re-record everything, and
--only <id> to redo a single clip. Output is a WAV next to the other hero audio plus a
generated manifest the UI imports (`voxly-ai/src/data/voiceSamples.js`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Windows consoles default to cp1252 and a stray non-ASCII arrow in a progress line
# would abort a long recording run at the last step.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from server.realtime.models import DEFAULT_GEMINI_LIVE_MODEL  # noqa: E402
from server.realtime.providers.gemini_voice import (  # noqa: E402
    GEMINI_LIVE_OUTPUT_RATE,
    GeminiLiveVoiceAdapter,
)

AUDIO_DIR = REPO_ROOT / "voxly-ai" / "public" / "audio" / "voxly" / "samples"
MANIFEST = REPO_ROOT / "voxly-ai" / "src" / "data" / "voiceSamples.js"

PHONE_STYLE = (
    "You are a warm, professional phone receptionist for a busy business. Speak once, "
    "conversationally, at a natural phone pace. No stage directions, no emoji, no "
    "announcing that you are an AI, and do not repeat yourself."
)


@dataclass
class Sample:
    id: str
    vertical: str
    industry: str
    label: str
    voice: str
    text: str
    persona: str
    ref: str = field(default="", repr=False)

    @property
    def filename(self) -> str:
        return f"{self.id}.wav"


SAMPLES: tuple[Sample, ...] = (
    Sample(
        id="healthcare-clinic",
        vertical="Healthcare",
        industry="Healthcare & Clinics",
        label="Clinic receptionist",
        voice="Kore",
        persona="receptionist for a multi-specialty clinic that books and reschedules appointments",
        text=(
            "Thank you for calling Sunshine Family Clinic. I can help you book, reschedule, "
            "or cancel an appointment. Which doctor would you like to see, and what day works "
            "best for you?"
        ),
    ),
    Sample(
        id="real-estate",
        vertical="Real Estate",
        industry="Real Estate",
        label="Property enquiry",
        voice="Fenrir",
        persona="sales assistant for a residential property team showing homes this weekend",
        text=(
            "Thanks for calling Harbour Point Realty. We have three homes available for viewing "
            "this weekend, including a four bedroom near the marina. Are you looking to buy or "
            "rent, and what is your ideal area?"
        ),
    ),
    Sample(
        id="car-dealership",
        vertical="Automotive",
        industry="Car Dealership",
        label="Test drive booking",
        voice="Puck",
        persona="front-desk agent for a used car dealership that books test drives",
        text=(
            "Hi, you've reached Metro Motors. I can book a test drive for you today. Which model "
            "interests you, and what time suits you this afternoon? Bring your licence and we'll "
            "have the car ready."
        ),
    ),
    Sample(
        id="restaurant",
        vertical="Restaurant",
        industry="Restaurants & QSR",
        label="Table reservation",
        voice="Aoede",
        persona="host for a busy neighbourhood restaurant taking table bookings",
        text=(
            "Good evening, and welcome to Saffron House. I have a table for two at seven thirty, "
            "or four at eight. Would you prefer the dining room or the terrace?"
        ),
    ),
    Sample(
        id="it-support",
        vertical="IT & SaaS",
        industry="IT & Software",
        label="Tier-one support",
        voice="Orus",
        persona="tier-one support agent for a software company resolving a login issue",
        text=(
            "Thanks for calling Northwind Software support. I can see an account lock on your "
            "workspace. I'll send a reset link to your email now and stay on the line until "
            "you're back in."
        ),
    ),
    Sample(
        id="education",
        vertical="Education",
        industry="Education & Institutes",
        label="Admissions enquiry",
        voice="Leda",
        persona="admissions counsellor for an engineering institute",
        text=(
            "Hello, and welcome to Northbridge Institute. Our admissions open next month. Are you "
            "looking for a bachelor's or a diploma programme, and which subject interests you?"
        ),
    ),
    Sample(
        id="logistics",
        vertical="Logistics",
        industry="Logistics & Courier",
        label="Shipment tracking",
        voice="Zephyr",
        persona="shipment tracking agent for a courier company",
        text=(
            "Thanks for calling SwiftParcel. Give me your tracking number and I'll check it while "
            "we talk. It looks like your parcel is out for delivery and should arrive before six "
            "this evening."
        ),
    ),
    Sample(
        id="home-services",
        vertical="Home Services",
        industry="Home Services",
        label="Service booking",
        voice="Charon",
        persona="dispatcher for an air conditioning repair company",
        text=(
            "You've reached CoolAir service. Is the unit cooling but not cooling enough, or is it "
            "completely stopped? I can offer you tomorrow between nine and twelve, or Thursday "
            "morning."
        ),
    ),
    Sample(
        id="banking",
        vertical="Banking",
        industry="Banking & Fintech",
        label="Card and account help",
        voice="Kore",
        persona="retail banking agent handling a blocked card",
        text=(
            "Thank you for calling Meridian Bank. I can unblock your card straight away. For "
            "security, could you confirm the last four digits of the number on the front of the "
            "card?"
        ),
    ),
    Sample(
        id="travel",
        vertical="Travel",
        industry="Travel & Hospitality",
        label="Itinerary change",
        voice="Aoede",
        persona="travel agent rescheduling a flight",
        text=(
            "Good morning, this is Skyward Travel. I have your booking with us. The flight moves "
            "by ninety minutes, so I can put you on the earlier departure instead. Does that work?"
        ),
    ),
)


def _wav_path(sample: Sample) -> Path:
    return AUDIO_DIR / sample.filename


def _write_wav(path: Path, pcm: bytes, sample_rate: int) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm)
    return len(pcm) / 2 / sample_rate


async def record_one(sample: Sample, *, force: bool, timeout_s: float) -> dict:
    target = _wav_path(sample)
    if target.exists() and not force:
        print(f"  = {sample.id} (exists, {target.stat().st_size // 1024} KB)")
        return _manifest_entry(sample, target)

    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set — cannot record live voice samples")

    instructions = f"{PHONE_STYLE}\n\nYour role: {sample.persona}."
    adapter = GeminiLiveVoiceAdapter(api_key=key)
    chunks: list[bytes] = []
    try:
        await asyncio.wait_for(
            adapter.connect(
                model=DEFAULT_GEMINI_LIVE_MODEL,
                instructions=instructions,
                voice=sample.voice,
                include_tools=False,
                turn_detection="server_vad",
                max_output_tokens=320,
            ),
            timeout=timeout_s,
        )
        await adapter.wait_ready(timeout=timeout_s)
        adapter.opening_history_clean = False
        # Tell the model the script is already "spoken" as a phone call, then ask for
        # exactly one turn. Nothing is streamed in, so the model never has to wait on
        # input audio or start its own opener.
        await adapter.start_response(
            instructions=(
                "This is a recorded voice sample for a product website. Say the following line "
                "once, exactly as a receptionist would say it on a live call. Do not add any "
                "other content.\n\n" + sample.text
            )
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            event = await adapter.poll_event(timeout=5.0)
            if not event:
                continue
            kind = event.get("type")
            if kind == "audio_delta":
                pcm = event.get("pcm")
                if pcm:
                    chunks.append(bytes(pcm))
            elif kind == "error":
                raise RuntimeError(f"live session error: {event.get('message')}")
            elif kind == "response_done" and not event.get("usage_only"):
                break
            elif kind == "_stream_end":
                break
        # Let the tail flush so the last syllable is not clipped.
        await asyncio.sleep(0.4)
    finally:
        try:
            await adapter.close()
        except Exception:
            pass

    pcm = b"".join(chunks)
    # Under a second of audio means the turn produced no speech — a failed capture, not
    # a very short line. Writing it would ship a click.
    if len(pcm) < GEMINI_LIVE_OUTPUT_RATE * 2:
        raise RuntimeError(f"no audio returned for {sample.id} ({len(pcm)} bytes)")
    seconds = _write_wav(target, pcm, GEMINI_LIVE_OUTPUT_RATE)
    print(f"  + {sample.id}: {seconds:.1f}s, {target.stat().st_size // 1024} KB")
    return _manifest_entry(sample, target)


def _manifest_entry(sample: Sample, path: Path) -> dict:
    with wave.open(str(path), "rb") as clip:
        seconds = clip.getnframes() / float(clip.getframerate())
    return {
        "id": sample.id,
        "vertical": sample.vertical,
        "industry": sample.industry,
        "label": sample.label,
        "text": sample.text,
        "url": f"/audio/voxly/samples/{sample.filename}",
        "durationSeconds": round(seconds, 2),
        "model": DEFAULT_GEMINI_LIVE_MODEL,
        "voice": sample.voice,
    }


def write_manifest(entries: list[dict]) -> None:
    body = json.dumps(entries, indent=2, ensure_ascii=False)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        "// GENERATED FILE — do not edit by hand.\n"
        "// Rendered by scripts/record_marketing_voice_samples.py using the live speech\n"
        "// model, so the samples the marketing page plays are the product's own voice.\n"
        f"export const VOICE_SAMPLES = {body};\n\n"
        "export default VOICE_SAMPLES;\n",
        encoding="utf-8",
    )
    print(f"  manifest -> {MANIFEST.relative_to(REPO_ROOT)} ({len(entries)} samples)")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-record clips that already exist")
    parser.add_argument("--only", action="append", default=[], help="record just these sample ids")
    parser.add_argument("--timeout", type=float, default=90.0, help="per-sample timeout in seconds")
    args = parser.parse_args()

    targets = [s for s in SAMPLES if not args.only or s.id in args.only]
    if args.only and len(targets) != len(args.only):
        unknown = sorted(set(args.only) - {s.id for s in targets})
        print(f"unknown sample id(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    print(f"recording {len(targets)} sample(s) with {DEFAULT_GEMINI_LIVE_MODEL}")
    entries: list[dict] = []
    failures: list[tuple[str, str]] = []
    for sample in targets:
        try:
            entries.append(await record_one(sample, force=args.force, timeout_s=args.timeout))
        except Exception as exc:
            failures.append((sample.id, f"{type(exc).__name__}: {exc}"))
            print(f"  ! {sample.id}: {type(exc).__name__}: {exc}")

    if entries:
        known = {e["id"] for e in entries}
        for sample in SAMPLES:
            if sample.id not in known and _wav_path(sample).exists():
                entries.append(_manifest_entry(sample, _wav_path(sample)))
        order = {s.id: i for i, s in enumerate(SAMPLES)}
        entries.sort(key=lambda e: order.get(e["id"], 999))
        write_manifest(entries)

    if failures:
        print("\nfailed:", file=sys.stderr)
        for sid, err in failures:
            print(f"  {sid}: {err}", file=sys.stderr)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))