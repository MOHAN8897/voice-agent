"""Force an empty main answer, then exercise real same-model recovery and gates."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from run_live_validation import CASES, ROOT, context

from server.call import call_context
from server.call.call_ledger import call_ledger
from server.call.live_turn_orchestrator import LiveTurnOrchestrator
from server.call.speech_recovery import recover_empty_speech
from server.config.env import get_settings

OUT = Path(__file__).resolve().parent


async def main():
    rows = []
    for case, caller in [(CASES[1], "నేను బిజీగా ఉన్నాను. తర్వాత మాట్లాడదాం."), (CASES[0], "I am still enquiring. Could you repeat that?"), (CASES[2], "मुझे एक बात समझ नहीं आई, फिर से बताएँ।")]:
        ctx = context(case, (OUT / f"{case['name']}-compiled.txt").read_text(encoding="utf-8"), "empty-recovery")
        call_context.put(ctx)
        await call_ledger.init(ctx.call_id, {"call_id": ctx.call_id, "is_test": True, "pipeline": "composed_voice"})
        orchestrator = LiveTurnOrchestrator()
        recovered = []

        async def empty(**kwargs):
            yield {"done": True, "text": "", "empty_provider_response": True, "response_contract": "speech_text", "finish_reason": "empty_provider_response"}

        async def recovery(**kwargs):
            text = await recover_empty_speech(**kwargs)
            recovered.append(text)
            return text

        settings = get_settings().model_copy(update={"enable_call_archive": False})
        with patch.object(orchestrator, "_stream_llm", empty), patch.object(orchestrator, "_memory_blocks", AsyncMock(return_value=(None, None))), patch.object(orchestrator, "_after_assistant", AsyncMock()), patch("server.call.live_turn_orchestrator.get_settings", return_value=settings), patch("server.call.speech_recovery.recover_empty_speech", recovery):
            events = [event async for event in orchestrator.handle_user_turn_stream(transcript=caller, language_code=case["language"], session_id=ctx.session_id, call_id=ctx.call_id)]
            done = next(event for event in reversed(events) if event.get("done"))
            rows.append({"language": case["language"], "caller": caller, "recovery_model": ctx.resolved_stack.llm.model, "live_recovery": recovered, "reply": done.get("text"), "close": done.get("end_call"), "recovery_required": done.get("recovery_required")})
        ctx.status = "completed"
        call_context.drop_session_pointer(ctx.session_id, ctx.call_id)
    (OUT / "live-recovery.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [row["language"] for row in rows if not any(row["live_recovery"]) or not row["reply"] or row["close"].get("should_end")]
    print(json.dumps({"sessions": len(rows), "failed": failed}))
    if failed:
        raise SystemExit(1)


asyncio.run(main())
