"""Prewarm outbound opening via Realtime — capture PCM, defer playback until callee speaks."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from server.realtime.models import REALTIME_PCM_RATE
from server.services.audio_transcode import StreamingPcmResampler, pcm16_to_mulaw
from server.services.pstn_debug import log_pstn
from server.services.spoken_numbers import prepare_spoken_reply

PREWARM_GREETING_INSTRUCTION = (
    'Speak aloud in audio exactly the following opening line once. '
    "Then wait silently for the caller. Do not hang up. Do not use tools:\n\"{line}\""
)

GEMINI_GREETING_SIDE_SESSION_INSTRUCTIONS = (
    "You are a voice actor for a phone greeting. "
    "Speak the requested opening line once in audio, then stop. "
    "Do not ask questions, do not use tools, do not hang up."
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
    transcript_parts: list[str] = []
    while not done:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log_pstn("prewarm.greeting.realtime.empty", control=control_id, reason="timeout")
            try:
                await adapter.cancel_response()
            except Exception:
                pass
            pcm_buf.clear()  # Partial greetings must not be marked fully delivered.
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
        if kind == "assistant_transcript_delta":
            transcript_parts.append(str(event.get("delta") or ""))
            transcript = "".join(transcript_parts).strip() or spoken
            continue
        if kind == "function_call":
            # Gemini Live may emit call_action before audio; acknowledge and keep polling.
            submit = getattr(adapter, "submit_function_output", None)
            if callable(submit) and str(event.get("name") or "") in ("call_action", "end_call"):
                import json

                try:
                    await submit(
                        call_id=str(event.get("call_id") or ""),
                        output=json.dumps({"ok": True, "deferred": True}),
                        name=str(event.get("name") or "call_action"),
                    )
                except Exception:
                    pass
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
            if isinstance(event.get("usage"), dict) and event["usage"]:
                greeting_usage = dict(event["usage"])
            if event.get("usage_only"):
                continue
            if kind == "cancelled" or event.get("failed"):
                log_pstn("prewarm.greeting.realtime.empty", control=control_id, reason=kind)
                pcm_buf.clear()
                done = True
            elif isinstance(event.get("usage"), dict) and event["usage"]:
                greeting_usage = dict(event["usage"])
            if pcm_buf:
                done = True
            # Empty response_done (e.g. Gemini tool-only turn) — wait for audio on next events.

    # Gemini can deliver its usage trailer after turn_complete. Collect it
    # before the throwaway session is closed, without generating another turn.
    if pcm_buf and not greeting_usage and getattr(adapter, "opening_history_clean", None) is not None:
        trailer_deadline = time.monotonic() + 0.75
        while time.monotonic() < trailer_deadline:
            event = await poll(timeout=min(0.25, trailer_deadline - time.monotonic()))
            if event and isinstance(event.get("usage"), dict) and event["usage"]:
                greeting_usage = dict(event["usage"])
                break
            if event and event.get("type") == "_stream_end":
                break

    frames = realtime_pcm24_to_wire_frames(
        bytes(pcm_buf),
        sample_rate=sample_rate,
        tts_output_codec=tts_output_codec,
    )
    if not frames:
        log_pstn("prewarm.greeting.realtime.empty", control=control_id, reason="no_frames")
        return [], "", greeting_usage

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


async def synthesize_gemini_greeting_on_side_session(
    *,
    greeting_text: str,
    sample_rate: int,
    tts_output_codec: str,
    model: str,
    voice: str | None = None,
    turn_detection: str | None = None,
    max_output_tokens: int | None = None,
    timeout_sec: float = 12.0,
    control_id: str = "",
    adapter_factory: Callable[[], Any] | None = None,
) -> tuple[list[bytes], str, dict[str, Any] | None]:
    """Capture greeting PCM on a throwaway Gemini Live session.

    Gemini cannot delete conversation items the way OpenAI Realtime can, so the
    adopted PSTN session must never receive the prewarm 'speak this line' turn.
    """
    spoken = prepare_spoken_reply(greeting_text or "").strip()
    if not spoken:
        return [], "", None

    if adapter_factory is not None:
        adapter = adapter_factory()
    else:
        from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter

        adapter = GeminiLiveVoiceAdapter()
    try:
        await adapter.connect(
            model=model,
            instructions=GEMINI_GREETING_SIDE_SESSION_INSTRUCTIONS,
            voice=voice,
            turn_detection=turn_detection,
            max_output_tokens=max_output_tokens,
            include_tools=False,
        )
        wait_ready = getattr(adapter, "wait_ready", None)
        if callable(wait_ready):
            await wait_ready()
        frames, transcript, usage = await synthesize_realtime_greeting_frames(
            adapter,
            greeting_text=spoken,
            sample_rate=sample_rate,
            tts_output_codec=tts_output_codec,
            timeout_sec=timeout_sec,
            control_id=control_id,
        )
        if frames:
            log_pstn(
                "prewarm.greeting.realtime.side_session",
                control=control_id,
                provider="gemini",
                frames=len(frames),
                chars=len(transcript or spoken),
            )
        return frames, transcript, usage
    except Exception as exc:
        log_pstn(
            "prewarm.greeting.realtime.failed",
            control=control_id,
            provider="gemini",
            error=f"side_session:{exc}"[:200],
        )
        return [], "", None
    finally:
        closer = getattr(adapter, "close", None)
        if callable(closer):
            try:
                await closer()
            except Exception:
                pass
