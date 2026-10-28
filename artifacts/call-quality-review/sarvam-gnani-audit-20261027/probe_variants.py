"""Isolate why Sarvam V1 returns stop-with-zero-content on defer/opt-out turns.

Variant A: bare system prompt ("reply in one short sentence") + the same caller
utterance. Variant B: the real composed messages plus one extra line that
requires a spoken acknowledgement. One request each.
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
USER_TEXT = "I'm busy, call me later."


async def _call(messages: list[dict], label: str, extra: dict | None = None) -> dict:
    adapter = SarvamLLMAdapter()
    body = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 1280,
        "stream": True,
        "temperature": 0.3,
        "reasoning_effort": None,
        "stream_options": {"include_usage": True},
    }
    body.update(extra or {})
    content, finish, usage, chunks = "", None, {}, 0
    async with httpx.AsyncClient(timeout=adapter._timeout()) as client:
        async with client.stream(
            "POST", adapter._url(MODEL, {"model": MODEL, "api_mode": MODE}),
            headers=adapter._headers({"call_id": f"variant-{label}"}), json=body,
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
                    chunks += 1
                    if isinstance(delta.get("content"), str):
                        content += delta["content"]
    print(f"{label}: chars={len(content)} finish={finish} usage={usage} chunks={chunks}")
    print(f"  text={content[:300]!r}")
    return {"label": label, "chars": len(content), "finish": finish, "usage": usage, "text": content}


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

    findings = []
    findings.append(await _call(
        [
            {"role": "system", "content": "You are a polite phone agent. Reply in one short sentence."},
            {"role": "user", "content": USER_TEXT},
        ],
        "A_bare_prompt",
    ))

    brain, *_ = await compile_agent_from_brief(brief=script["brief"], language=script["language"], interpret_brief=False)
    ctx = CallContext(
        call_id="variant-B", tenant_id="audit", agent_id="variant", session_id="variant",
        channel="browser", direction="outbound", environment="development", tier="standard",
        resolved_stack=ResolvedStack(
            combination_id="variant", tier="standard", mode="frontend",
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
            async for chunk in SarvamLLMAdapter._stream(self, input_messages, schema, **kwargs):
                yield chunk

    messages = build_live_input(
        compiled_brain_text=composed_system_prompt(ctx), history=history, transcript=USER_TEXT
    )
    try:
        async for _ in LiveTurnOrchestrator()._stream_composed_speech(
            adapter=Capture(), messages=messages, schema=None,
            stream_kwargs={"model": MODEL, "api_mode": MODE, "max_output_tokens": 500, "temperature": 0.3},
            call_id=ctx.call_id, provider="sarvam", model=MODEL,
        ):
            pass
    except Exception:
        pass
    real_messages = captured.get("messages") or []
    findings.append(await _call(real_messages, "B_real_prompt"))

    patched = list(real_messages)
    for index in range(len(patched) - 1, -1, -1):
        if patched[index].get("role") == "system":
            patched[index] = {
                "role": "system",
                "content": str(patched[index]["content"])
                + " Always say one short spoken line acknowledging the caller before you stop.",
            }
            break
    findings.append(await _call(patched, "C_real_prompt_plus_ack"))

    (HERE / "probe_variants.json").write_text(
        json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
