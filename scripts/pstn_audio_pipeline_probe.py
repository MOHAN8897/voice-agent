"""Probe PSTN TTS → queue → 20ms pacer without a phone call.

Runs real configured TTS through the same Telnyx bridge outbound path used in
production (codec convert, bounded queue, backpressure, monotonic pacer) and
writes WAV files you can listen to.

Usage (repo root):
  python -m scripts.pstn_audio_pipeline_probe --session test-studio
  python -m scripts.pstn_audio_pipeline_probe --preset long --chunking production
  python -m scripts.pstn_audio_pipeline_probe --all-scenarios
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.services.pstn_prewarm import _PrewarmVoiceStub
from server.services.pstn_text_chunker import drain_complete_sentences, join_speakable_chunks
from server.services.pstn_turn_tts import PstnTurnTtsSession
from server.services.telnyx_pstn_bridge import (
    MAX_AUDIO_QUEUE_FRAMES,
    QUEUE_HIGH_WATERMARK,
    QUEUE_LOW_WATERMARK,
    TelnyxPstnBridge,
)

PRESETS: dict[str, str] = {
    "short": "Hi, this is Sharan from Priya Estates. How can I help you today?",
    "medium": (
        "Hi, this is Sharan from Priya Estates. I am calling about the property "
        "you enquired about last week. We have a few options in Gachibowli and "
        "Kondapur that match your budget. Would you like me to share the details?"
    ),
    "long": (
        "Hi, this is Sharan from Priya Estates. Thank you for taking my call today. "
        "I wanted to follow up on your enquiry about three-bedroom apartments near "
        "the financial district. We currently have two ready-to-move options and one "
        "under-construction project with flexible payment plans. The first option is "
        "a south-facing flat with covered parking and clubhouse access. The second "
        "is slightly larger with a better view, though the price is a little higher. "
        "If you have five minutes, I can walk you through the floor plans and the "
        "nearest schools and hospitals. Would that work for you?"
    ),
}

CHUNKING_MODES = ("full_turn", "production", "per_sentence")


class CaptureWebSocket:
    """Records Telnyx media JSON payloads the pacer would send."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_text(self, message: str) -> None:
        self.messages.append(message)


class ProbeVoice(_PrewarmVoiceStub):
    """TTS sink that also feeds the Telnyx outbound bridge."""

    def __init__(self, bridge: TelnyxPstnBridge, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._bridge = bridge
        self.tts_wire_frames: list[bytes] = []

    async def _emit_agent_wire(self, wire: bytes) -> None:
        if wire:
            self.tts_wire_frames.append(wire)
            self.frames.append(wire)
            self._wire_frames_out += 1
        await self._bridge._send_agent_wire(wire)


@dataclass
class QueueProfile:
    name: str
    max_frames: int
    high: int
    low: int


@dataclass
class ProbeResult:
    scenario: str
    chunking: str
    queue_profile: str
    tts_chunks: int
    tts_wire_frames: int
    pacer_frames: int
    audio_seconds: float
    metrics: dict[str, int]
    queue_peak: int
    wav_tts: Path
    wav_pacer: Path
    healthy: bool
    notes: list[str] = field(default_factory=list)


def _chunk_text(text: str, mode: str) -> list[str]:
    if mode == "full_turn":
        return [text.strip()]
    if mode == "per_sentence":
        chunks: list[str] = []
        pending = text
        while pending.strip():
            sents, pending = drain_complete_sentences(pending)
            for s in sents:
                chunks.append(s)
        tail = pending.strip()
        if tail:
            chunks.append(tail)
        return chunks or [text.strip()]
    # production: simulate streaming token arrival (word batches)
    chunks = []
    pending = ""
    words = text.split()
    step = 3
    for i in range(0, len(words), step):
        pending = (pending + " " + " ".join(words[i : i + step])).strip()
        sents, pending = drain_complete_sentences(pending, allow_first_fast=True)
        if sents:
            chunks.append(join_speakable_chunks(sents))
    tail = pending.strip()
    if tail:
        chunks.append(tail)
    return chunks or [text.strip()]


def _apply_queue_profile(profile: QueueProfile) -> None:
    import server.services.telnyx_pstn_bridge as bridge_mod

    bridge_mod.MAX_AUDIO_QUEUE_FRAMES = profile.max_frames
    bridge_mod.QUEUE_HIGH_WATERMARK = profile.high
    bridge_mod.QUEUE_LOW_WATERMARK = profile.low


def _write_l16_wav(path: Path, frames: list[bytes], sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"".join(frames)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)


def _decode_pacer_frames(ws: CaptureWebSocket) -> list[bytes]:
    frames: list[bytes] = []
    for message in ws.messages:
        body = json.loads(message)
        if body.get("event") != "media":
            continue
        payload = base64.b64decode(body["media"]["payload"])
        if payload:
            frames.append(payload)
    return frames


async def _wait_for_playout(
    bridge: TelnyxPstnBridge,
    ws: CaptureWebSocket,
    *,
    expected_min_frames: int,
    timeout_s: float,
) -> None:
    deadline = time.monotonic() + timeout_s
    stable = 0
    while time.monotonic() < deadline:
        if (
            bridge._out_queue.empty()
            and not bridge._out_sending
            and len(ws.messages) >= max(1, expected_min_frames - 2)
        ):
            stable += 1
            if stable >= 5:
                return
        else:
            stable = 0
        await asyncio.sleep(0.02)
    raise TimeoutError(
        f"playout did not finish in {timeout_s}s "
        f"(queue={bridge._out_queue.qsize()} sent={len(ws.messages)} expected~={expected_min_frames})"
    )


async def run_probe(
    *,
    text: str,
    session_id: str,
    chunking: str,
    queue_profile: QueueProfile,
    out_dir: Path,
    scenario_name: str,
) -> ProbeResult:
    _apply_queue_profile(queue_profile)
    ws = CaptureWebSocket()
    bridge = TelnyxPstnBridge(ws)  # type: ignore[arg-type]
    bridge.call_id = "pstn-audio-probe"
    bridge.call_control_id = "probe-control"
    bridge._voice = ProbeVoice(
        bridge,
        session_id=session_id,
        call_id=bridge.call_id,
        sample_rate=16000,
        tts_output_codec="linear16",
        language="en-IN",
    )
    voice = bridge._voice
    from server.services.pstn_playback import TelnyxQueuePlayback

    def _drain_queue() -> int:
        n = 0
        while True:
            try:
                bridge._out_queue.get_nowait()
                n += 1
            except asyncio.QueueEmpty:
                return n

    bridge._playback = TelnyxQueuePlayback(
        queue_size=lambda: bridge._out_queue.qsize(),
        drain=_drain_queue,
        frame_ms=20.0,
        sending=lambda: bridge._out_sending,
        wait_for_capacity=bridge._wait_for_playout_capacity,
    )
    voice.playback = bridge._playback
    voice.current_turn_id = "probe-turn"
    voice.current_generation_id = "probe-gen"

    bridge._out_task = asyncio.create_task(bridge._out_worker())
    queue_peak = 0
    chunks = _chunk_text(text, chunking)
    session = PstnTurnTtsSession(voice)
    notes: list[str] = []
    try:
        await session.open()
        provider = session._merged.get("provider", "?")
        model = session._merged.get("model", "?")
        notes.append(f"TTS provider={provider} model={model}")
        for piece in chunks:
            if not piece.strip():
                continue
            wait = getattr(voice.playback, "wait_for_capacity", None)
            if callable(wait):
                ok = await wait(voice.current_generation_id)
                if not ok:
                    notes.append("TTS text pacing blocked (generation cancelled?)")
            await session.send_text(piece)
            queue_peak = max(queue_peak, bridge._out_queue.qsize())
        await session.finish()
        if session.had_error:
            raise RuntimeError(f"TTS error: {session._last_error or 'unknown'}")
        if not session.audio_emitted:
            raise RuntimeError("TTS returned no audio")
        expected_frames = max(len(voice.tts_wire_frames), 1)
        timeout = max(30.0, expected_frames * 0.02 + 5.0)
        await _wait_for_playout(bridge, ws, expected_min_frames=expected_frames, timeout_s=timeout)
        queue_peak = max(queue_peak, bridge._out_queue.qsize())
    finally:
        bridge._closed = True
        if bridge._out_task:
            bridge._out_task.cancel()
            try:
                await bridge._out_task
            except asyncio.CancelledError:
                pass
        await session.close()

    pacer_frames = _decode_pacer_frames(ws)
    metrics = dict(bridge._queue_metrics)
    tts_seconds = sum(len(f) for f in voice.tts_wire_frames) / 32000.0
    pacer_seconds = sum(len(f) for f in pacer_frames) / 32000.0
    notes_key = f"{scenario_name}__{chunking}__{queue_profile.name}"
    wav_tts = out_dir / f"{notes_key}__tts_wire.wav"
    wav_pacer = out_dir / f"{notes_key}__pacer_out.wav"
    _write_l16_wav(wav_tts, voice.tts_wire_frames)
    _write_l16_wav(wav_pacer, pacer_frames)

    healthy = (
        metrics.get("normal_speech_dropped_frames", 0) == 0
        and metrics.get("playout_underrun_count", 0) == 0
        and len(pacer_frames) > 0
    )
    if metrics.get("playout_underrun_count", 0) > 0:
        notes.append("UNDERRUNS detected — gaps/cuts likely in PSTN path")
    if metrics.get("producer_backpressure_wait_count", 0) > 0:
        notes.append(
            f"Backpressure waits={metrics['producer_backpressure_wait_count']} "
            f"({metrics.get('producer_backpressure_wait_ms', 0)} ms)"
        )
    if len(chunks) > 3:
        notes.append(f"Many TTS chunks ({len(chunks)}) — phrase-boundary gaps possible")
    frame_delta = abs(len(pacer_frames) - len(voice.tts_wire_frames))
    if frame_delta > 2:
        notes.append(f"Frame count mismatch tts={len(voice.tts_wire_frames)} pacer={len(pacer_frames)}")

    return ProbeResult(
        scenario=scenario_name,
        chunking=chunking,
        queue_profile=queue_profile.name,
        tts_chunks=len(chunks),
        tts_wire_frames=len(voice.tts_wire_frames),
        pacer_frames=len(pacer_frames),
        audio_seconds=round(pacer_seconds, 2),
        metrics=metrics,
        queue_peak=queue_peak,
        wav_tts=wav_tts,
        wav_pacer=wav_pacer,
        healthy=healthy,
        notes=notes,
    )


def _print_result(r: ProbeResult) -> None:
    status = "HEALTHY" if r.healthy else "INVESTIGATE"
    print(f"\n{'=' * 72}")
    print(f"SCENARIO: {r.scenario} | chunking={r.chunking} | queue={r.queue_profile}")
    print(f"RESULT: {status}")
    print(f"  TTS chunks: {r.tts_chunks}")
    print(f"  TTS wire frames: {r.tts_wire_frames} | Pacer frames: {r.pacer_frames}")
    print(f"  Audio duration: {r.audio_seconds}s | Queue peak: {r.queue_peak}")
    print(f"  normal_speech_dropped: {r.metrics.get('normal_speech_dropped_frames', 0)}")
    print(f"  underruns: {r.metrics.get('playout_underrun_count', 0)}")
    print(f"  backpressure waits: {r.metrics.get('producer_backpressure_wait_count', 0)} "
          f"({r.metrics.get('producer_backpressure_wait_ms', 0)} ms)")
    print(f"  barge discards: {r.metrics.get('barge_in_discarded_frames', 0)}")
    print(f"  Listen TTS wire:  {r.wav_tts}")
    print(f"  Listen pacer out: {r.wav_pacer}")
    for note in r.notes:
        print(f"  • {note}")


async def main_async(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    text = args.text or PRESETS[args.preset]
    profiles = [
        QueueProfile("current", MAX_AUDIO_QUEUE_FRAMES, QUEUE_HIGH_WATERMARK, QUEUE_LOW_WATERMARK),
        QueueProfile("smoother", 20, 15, 5),
        QueueProfile("low_latency", 15, 8, 3),
    ]
    if args.queue_profile != "all":
        profiles = [p for p in profiles if p.name == args.queue_profile]

    chunkings = [args.chunking] if args.chunking != "all" else list(CHUNKING_MODES)
    results: list[ProbeResult] = []

    if args.all_scenarios:
        scenarios = [(name, PRESETS[name]) for name in ("short", "medium", "long")]
    else:
        scenarios = [(args.preset, text)]

    for scenario_name, scenario_text in scenarios:
        for chunking in chunkings:
            for profile in profiles:
                print(f"\nRunning {scenario_name} / {chunking} / {profile.name} ...")
                try:
                    result = await run_probe(
                        text=scenario_text,
                        session_id=args.session,
                        chunking=chunking,
                        queue_profile=profile,
                        out_dir=out_dir,
                        scenario_name=scenario_name,
                    )
                    results.append(result)
                    _print_result(result)
                except Exception as exc:
                    print(f"FAILED {scenario_name}/{chunking}/{profile.name}: {exc}")

    summary_path = out_dir / "probe_summary.json"
    summary_path.write_text(
        json.dumps(
            [
                {
                    "scenario": r.scenario,
                    "chunking": r.chunking,
                    "queue": r.queue_profile,
                    "healthy": r.healthy,
                    "tts_chunks": r.tts_chunks,
                    "queue_peak": r.queue_peak,
                    "underruns": r.metrics.get("playout_underrun_count", 0),
                    "drops": r.metrics.get("normal_speech_dropped_frames", 0),
                    "backpressure_waits": r.metrics.get("producer_backpressure_wait_count", 0),
                    "wav_pacer": str(r.wav_pacer),
                    "notes": r.notes,
                }
                for r in results
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSummary written to {summary_path}")
    unhealthy = [r for r in results if not r.healthy]
    if unhealthy:
        print(f"\n{len(unhealthy)} scenario(s) need investigation — listen to pacer_out WAV files.")
        return 1
    print("\nAll probes healthy on server-side metrics. If phone still cracks, issue is likely Telnyx/carrier.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="test-studio", help="Test Studio session id for TTS config")
    parser.add_argument("--preset", choices=tuple(PRESETS), default="short")
    parser.add_argument("--text", default=None, help="Override preset text")
    parser.add_argument("--chunking", choices=(*CHUNKING_MODES, "all"), default="production")
    parser.add_argument(
        "--queue-profile",
        choices=("current", "smoother", "low_latency", "all"),
        default="current",
    )
    parser.add_argument("--all-scenarios", action="store_true", help="Run short+medium+long presets")
    parser.add_argument("--out-dir", default="data/pstn-audio-probe")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
