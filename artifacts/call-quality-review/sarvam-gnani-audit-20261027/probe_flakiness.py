"""Measure the Sarvam stop-with-no-content rate and test a non-empty instruction.

Eight identical requests for the real S4T10 context (base), then eight with one
extra sentence requiring a spoken line. Same model, temperature and token cap.
"""
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
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

HERE = Path(__file__).resolve().parent
MODEL = "sarvam-105b-conversations"
MODE = "chat_completions_v1"
TRIALS = 8
USER_TEXT = "I'm busy, call me later."
EXTRA = " Always produce one short spoken sentence in the selected language; never return empty text."


async def _one(messages: list[dict], label: str, index: int) -> dict:
    adapter = SarvamLLMAdapter()
    body = {
        "model": MODEL, "messages": messages, "max_tokens": 1280, "stream": True,
        "temperature": 0.3, "reasoning_effort": None, "stream_options": {"include_usage": True},
    }
    content, finish, usage = "", None, {}
    async with httpx.AsyncClient(timeout=adapter._timeout()) as client:
        async with client.stream(
            "POST", adapter._url(MODEL, {"model": MODEL, "api_mode": MODE}),
            headers=adapter._headers({"call_id": f"flaky-{label}-{index}"}), json=body,
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                payload = json.loads(data)
                if payload.get("usage"):
                    usage = payload["usage"]
                for choice in payload.get("choices") or []:
                    finish = choice.get("finish_reason") or finish
                    delta = choice.get("delta") or {}
                    if isinstance(delta.get("content"), str):
                        content += delta["content"]
    return {
        "variant": label, "trial": index, "chars": len(content.strip()),
        "finish": finish, "output_tokens": usage.get("completion_tokens"),
        "text": content.strip()[:160],
    }


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

    brain, *_ = await compile_agent_from_brief(brief=script["brief"], language=script["language"], interpret_brief=False)
    ctx = CallContext(
        call_id="flaky-B", tenant_id="audit", agent_id="flaky", session_id="flaky",
        channel="browser", direction="outbound", environment="development", tier="standard",
        resolved_stack=ResolvedStack(
            combination_id="flaky", tier="standard", mode="frontend",
            stt=StageSelection("sarvam", "saaras:v3", {}),
            llm=StageSelection("sarvam", MODEL, {"api_mode": MODE}),
            tts=StageSelection("gnani", "timbre-v3.0", {"speaker": "Shivani"}),
            language=script["language"],
        ),
        compiled_brain_version="audit", compiled_brain_text=brain,
        started_at=datetime.now(timezone.utc), storage_path="", pipeline="composed_voice",
    )
    call_context.put(ctx)
    captured: dict = {}

    class Capture(SarvamLLMAdapter):
        async def _stream(self, input_messages=None, schema=None, **kwargs):
            captured["messages"] = _chat_messages(input_messages, kwargs.get("transcript"))
            yield {"delta": "X", "language_context": {}}
            yield {"done": True, "text": "X", "language_context": {}, "usage": {}, "finish_reason": "stop"}

    messages = build_live_input(
        compiled_brain_text=composed_system_prompt(ctx), history=history, transcript=USER_TEXT
    )
    async for _ in LiveTurnOrchestrator()._stream_composed_speech(
        adapter=Capture(), messages=messages, schema=None,
        stream_kwargs={"model": MODEL, "api_mode": MODE, "max_output_tokens": 500, "temperature": 0.3},
        call_id=ctx.call_id, provider="sarvam", model=MODEL,
    ):
        pass
    base = captured["messages"]
    strengthened = list(base)
    for index in range(len(strengthened) - 1, -1, -1):
        if strengthened[index].get("role") == "system":
            strengthened[index] = {
                "role": "system",
                "content": str(strengthened[index]["content"]) + EXTRA,
            }
            break

    rows: list[dict] = []
    for label, msgs in (("base", base), ("non_empty_rule", strengthened)):
        for index in range(TRIALS):
            row = await _one(msgs, label, index)
            rows.append(row)
            print(f"{label} #{index}: chars={row['chars']} tokens={row['output_tokens']} text={row['text']!r}")

    summary = {}
    for label in ("base", "non_empty_rule"):
        subset = [r for r in rows if r["variant"] == label]
        empty = sum(1 for r in subset if r["chars"] == 0)
        summary[label] = {"trials": len(subset), "empty": empty, "empty_rate": round(empty / len(subset), 3)}
        print(f"SUMMARY {label}: {empty}/{len(subset)} empty")
    (HERE / "probe_flakiness.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
