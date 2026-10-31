"""Dump every raw SSE payload for the silent S4T10 turn, one request only."""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "artifacts/call-quality-review/sarvam-gnani-audit-20261027"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from server.agent.instruction_builder import build_live_input  # noqa: E402
from server.brain.agent_script_compiler import compile_agent_from_brief  # noqa: E402
from server.call import call_context  # noqa: E402
from server.call.call_context import CallContext  # noqa: E402
from server.call.live_turn_orchestrator import LiveTurnOrchestrator  # noqa: E402
from server.providers.base import ResolvedStack, StageSelection  # noqa: E402
from server.providers.sarvam_llm import SarvamLLMAdapter, _chat_messages  # noqa: E402
from server.services.composed_voice_session import composed_system_prompt  # noqa: E402

HERE = ROOT / "artifacts/call-quality-review/sarvam-gnani-audit-20261027"
MODEL = "sarvam-105b-conversations"
MODE = "chat_completions_v1"
payloads: list[dict] = []


class CaptureAdapter(SarvamLLMAdapter):
    async def _stream(self, input_messages=None, schema=None, **kwargs):
        model = self._model(kwargs)
        url = self._url(model, kwargs)
        messages = _chat_messages(input_messages, kwargs.get("transcript"))
        body = self._request_body(model=model, messages=messages, kwargs=kwargs, stream=True, schema=schema)
        payloads.append(body)
        yield {"delta": "X", "language_context": {}}
        yield {"done": True, "text": "X", "language_context": {}, "usage": {}, "finish_reason": "stop"}


async def main() -> int:
    from run_audit import SCRIPTS

    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    script = next(s for s in SCRIPTS if s["id"] == "S4_education_adversarial")
    stored = next(s for s in results["scripts"] if s["id"] == script["id"])["turns"]
    history: list[dict] = []
    for row in stored:
        if row["id"] == "S4T10":
            break
        history += [{"role": "user", "content": row["user"]}, {"role": "assistant", "content": row["reply"]}]
    user_text = next(t["user"] for t in stored if t["id"] == "S4T10")

    brain, *_ = await compile_agent_from_brief(brief=script["brief"], language=script["language"], interpret_brief=False)
    ctx = CallContext(
        call_id="dump-S4T10", tenant_id="audit", agent_id="dump", session_id="dump",
        channel="browser", direction="outbound", environment="development", tier="standard",
        resolved_stack=ResolvedStack(
            combination_id="dump", tier="standard", mode="frontend",
            stt=StageSelection("sarvam", "saaras:v3", {}),
            llm=StageSelection("sarvam", MODEL, {"api_mode": MODE}),
            tts=StageSelection("gnani", "timbre-v3.0", {"speaker": "Shivani"}),
            language=script["language"],
        ),
        compiled_brain_version="audit", compiled_brain_text=brain,
        started_at=datetime.now(timezone.utc), storage_path="", pipeline="composed_voice",
    )
    call_context.put(ctx)
    messages = build_live_input(
        compiled_brain_text=composed_system_prompt(ctx), history=history, transcript=user_text
    )
    async for _ in LiveTurnOrchestrator()._stream_composed_speech(
        adapter=CaptureAdapter(), messages=messages, schema=None,
        stream_kwargs={"model": MODEL, "api_mode": MODE, "max_output_tokens": 500, "temperature": 0.3},
        call_id=ctx.call_id, provider="sarvam", model=MODEL,
    ):
        pass

    adapter=SarvamLLMAdapter()
    rows=[]
    body=payloads[0]
    body.pop('stream_options',None)
    body['stream']=False
    async with httpx.AsyncClient(timeout=adapter._timeout()) as client:
        for trial in range(3):
            response=await client.post(adapter._url(MODEL,{'model':MODEL,'api_mode':MODE}),headers=adapter._headers({'session_id':'transport-probe'}),json=body)
            response.raise_for_status()
            data=response.json(); choice=(data.get('choices') or [{}])[0]; text=(choice.get('message') or {}).get('content') or ''
            rows.append({'trial':trial,'model':MODEL,'transport':'json','chars':len(text.strip()),'finish':choice.get('finish_reason'),'usage':data.get('usage'),'text':text})
    target=ROOT/'artifacts/call-quality-review/conversation-rules-crm-20261027/nonstream-probe.json'
    target.write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps([{'trial':r['trial'],'chars':r['chars'],'finish':r['finish']} for r in rows]))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
