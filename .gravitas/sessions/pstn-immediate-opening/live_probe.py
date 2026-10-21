"""Generic Gemini-only connectivity probe: no phone call or customer data."""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter
from server.services.pstn_realtime_greeting_prewarm import synthesize_realtime_greeting_frames


async def main():
    adapter = GeminiLiveVoiceAdapter()
    result = {"phone_call_placed": False}
    try:
        async with asyncio.timeout(55):
            started = time.monotonic()
            await adapter.connect(
                model="gemini-3.8-live", voice="Zephyr", include_tools=False,
                instructions=build_gemini_audio_session_instructions(
                    "Help with appointment enquiries. After consent, ask the preferred appointment day.",
                    language="en-IN", direction="outbound",
                    opening_greeting="Hello, this is your appointment assistant.",
                ),
            )
            original_session = adapter._session
            frames, _, _ = await synthesize_realtime_greeting_frames(
                adapter, greeting_text="Hello, this is your appointment assistant.",
                sample_rate=16000, tts_output_codec="linear16", language="en-IN", preserve_history=True,
            )
            result.update(cached_frames=len(frames), prepared_in_seconds=round(time.monotonic() - started, 2))
            await adapter.set_auto_response(False)
            await adapter.note_opening_delivered()
            await adapter.set_auto_response(True)
            await adapter.start_response(instructions="The caller replied: Yes, I have a moment. Continue with the next appointment question.")
            audio_bytes = 0
            second_text = ""
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                event = await adapter.poll_event(timeout=0.5)
                if not event:
                    continue
                if event.get("type") == "audio_delta":
                    audio_bytes += len(event.get("pcm") or b"")
                if event.get("type") in {"assistant_transcript_delta", "assistant_transcript"}:
                    second_text += event.get("text") or ""
                if event.get("type") == "response_done" and audio_bytes:
                    break
            result.update(same_live_session=adapter._session is original_session,
                          reply_audio_bytes=audio_bytes,
                          full_opening_repeated="this is your appointment assistant" in second_text.lower())
            result["passed"] = bool(frames and audio_bytes and result["same_live_session"] and not result["full_opening_repeated"])
    except Exception as exc:
        result.update(passed=False, error_type=type(exc).__name__)
    finally:
        await adapter.close()
    Path(__file__).with_name("live-probe-result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


asyncio.run(main())
