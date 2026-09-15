"""Prewarm outbound opening via OpenAI Realtime — capture PCM, defer playback until callee speaks."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from server.realtime.models import REALTIME_PCM_RATE
from server.services.audio_transcode import StreamingPcmResampler, pcm16_to_mulaw
from server.services.pstn_debug import log_pstn
from server.services.spoken_numbers import prepare_spoken_reply

PREWARM_GREETING_INSTRUCTION = (
    'Speak exactly the following opening line once, then stop. Do not add anything else:\n"{line}"'
)


def wire_frame_bytes(sample_rate: int, *, linear16: bool) -> int:
    if linear16:
        return int(sample_rate * 0.02) * 2
    return 160


def realtime_pcm24_to_wire_frames(
    pcm24: bytes,
    *,
    sample_rate: int,
    tts_output_codec: str,
) -> list[bytes]:
    """Convert Realtime 24 kHz PCM into 20 ms PSTN wire frames."""
    if not pcm24:
        return []
    linear16 = str(tts_output_codec or "").lower() in ("linear16", "l16", "pcm16")
    resampler = StreamingPcmResampler(REALTIME_PCM_RATE, sample_rate)
    pcm_out = resampler.feed(pcm24)
    try:
        pcm_out += resampler.flush()
    except Exception:
        pass
    if not pcm_out:
        return []
    if linear16:
        wire_pcm = pcm_out
    else:
        wire_pcm = pcm16_to_mulaw(pcm_out, sample_rate=sample_rate)
    frame = wire_frame_bytes(sample_rate, linear16=linear16)
    frames: list[bytes] = []
    for offset in range(0, len(wire_pcm), frame):
        chunk = wire_pcm[offset : offset + frame]
        if len(chunk) == frame:
            frames.append(chunk)
    return frames


async def synthesize_realtime_greeting_frames(
    adapter: Any,
    *,
    greeting_text: str,
    sample_rate: int,
    tts_output_codec: str,
    timeout_sec: float = 12.0,
    control_id: str = "",
) -> tuple[list[bytes], str, dict[str, Any] | None]:
    """Generate opening audio on a live Realtime session; returns wire frames, transcript, usage."""
    spoken = prepare_spoken_reply(greeting_text or "").strip()
    if not spoken:
        return [], "", None

    poll = getattr(adapter, "poll_event", None)
    if not callable(poll):
        log_pstn("prewarm.greeting.realtime.failed", control=control_id, error="adapter_missing_poll_event")
        return [], "", None

    pcm_buf = bytearray()
    transcript = spoken
    greeting_usage: dict[str, Any] | None = None
    try:
        await adapter.start_response(
            instructions=PREWARM_GREETING_INSTRUCTION.format(line=spoken.replace('"', "'"))
        )
    except Exception as exc:
        log_pstn("prewarm.greeting.realtime.failed", control=control_id, error=str(exc)[:200])
        return [], "", None

    deadline = time.monotonic() + timeout_sec
    done = False
    while not done:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log_pstn("prewarm.greeting.realtime.empty", control=control_id, reason="timeout")
            try:
                await adapter.cancel_response()
            except Exception:
                pass
            break
        try:
            event = await poll(timeout=min(remaining, 0.25))
        except asyncio.TimeoutError:
            continue
        if event is None:
            continue
        kind = str(event.get("type") or "")
        if kind == "_stream_end":
            break
        if kind == "audio_delta":
            pcm = event.get("pcm") or b""
            if pcm:
                pcm_buf.extend(pcm)
            continue
        if kind == "assistant_transcript":
            text = str(event.get("text") or "").strip()
            if text:
                transcript = text
            continue
        if kind == "error":
            log_pstn(
                "prewarm.greeting.realtime.failed",
                control=control_id,
                error=str(event.get("message") or "")[:200],
            )
            try:
                await adapter.cancel_response()
            except Exception:
                pass
            pcm_buf.clear()
            break
        if kind in ("response_done", "cancelled"):
            if kind == "cancelled" or event.get("failed"):
                log_pstn("prewarm.greeting.realtime.empty", control=control_id, reason=kind)
                pcm_buf.clear()
            elif isinstance(event.get("usage"), dict):
                greeting_usage = dict(event["usage"])
            done = True

    frames = realtime_pcm24_to_wire_frames(
        bytes(pcm_buf),
        sample_rate=sample_rate,
        tts_output_codec=tts_output_codec,
    )
    if not frames:
        log_pstn("prewarm.greeting.realtime.empty", control=control_id, reason="no_frames")
        return [], "", None

    deleter = getattr(adapter, "delete_synthetic_response_items", None)
    if callable(deleter):
        try:
            await deleter()
        except Exception as exc:
            log_pstn("prewarm.greeting.realtime.failed", control=control_id, error=f"delete:{exc}"[:200])
            return [], "", None

    discard = getattr(adapter, "discard_queued", None)
    if callable(discard):
        discard()

    return frames, transcript, greeting_usage
