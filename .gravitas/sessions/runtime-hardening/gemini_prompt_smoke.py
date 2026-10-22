"""Bounded, synthetic primary Gemini check; no carrier or customer data."""
import asyncio
import json
import logging
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
logging.disable(logging.CRITICAL)


async def main():
    from server.brain.agent_script_compiler import compile_agent_from_brief
    from server.realtime.gemini_audio_session import build_gemini_audio_session_instructions
    from server.realtime.models import live_gemini_model
    from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter
    from server.utils.logger import logger
    logger.disabled = True
    compiled, result, *_ = await compile_agent_from_brief(
        brief="Create an inbound Telugu support agent named Meera for Example Support. Inspection costs INR 500. Do not invent availability or claim a booking without a tool.",
        language="te-IN", direction="inbound", interpret_brief=True,
    )
    model = live_gemini_model(None)
    report = {"provider": "gemini", "model": model, "generation_mode": result.optimizer_model, "turns": []}
    adapter = GeminiLiveVoiceAdapter()
    try:
        async with asyncio.timeout(30):
            await adapter.connect(model=model, voice="Puck", include_tools=False,
                instructions=build_gemini_audio_session_instructions(compiled, language="te-IN", direction="inbound"))
            await adapter.wait_ready(timeout=12)
        report["connected"] = True
        for caller_text in ("Hello. Inspection cost entha?", "Okay, aa cost malli cheppandi."):
            start = time.monotonic()
            await adapter.start_response(instructions=caller_text)
            frames = 0
            complete = False
            async with asyncio.timeout(30):
                while True:
                    event = await adapter.poll_event(timeout=1)
                    if not event:
                        continue
                    if event.get("type") == "audio_delta":
                        frames += 1
                    if event.get("type") == "error":
                        raise RuntimeError("Provider returned an error")
                    if event.get("type") == "response_done" and not event.get("usage_only"):
                        complete = True
                        break
            report["turns"].append({"audio_frames": frames, "turn_complete": complete, "elapsed_ms": round((time.monotonic()-start)*1000)})
        report["passed"] = all(turn["audio_frames"] > 0 and turn["turn_complete"] for turn in report["turns"])
    except Exception as exc:
        report["passed"] = False
        report["error_type"] = type(exc).__name__
    finally:
        await adapter.close()
    (Path(__file__).parent / "gemini-smoke-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
