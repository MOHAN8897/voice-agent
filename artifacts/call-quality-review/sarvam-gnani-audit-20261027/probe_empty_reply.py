"""Root-cause probe for the silent Sarvam turns found by run_audit.py.

Rebuilds each failing turn's exact messages through the real orchestrator,
captures the request body it would send, then issues the same request twice at
the HTTP layer and records every SSE delta field the provider emits:

  * ``explicit_null`` — ``reasoning_effort: null`` (what the adapter sends today)
  * ``omitted``       — the key removed entirely (provider default thinking)

No product code is changed. Outputs ``probe_empty_reply.md``.

Usage:
    python artifacts/call-quality-review/sarvam-gnani-audit-20261027/probe_empty_reply.py
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
LLM_MODEL = "sarvam-105b-conversations"
LLM_MODE = "chat_completions_v1"

PROBE_TURNS = [
    ("S4_education_adversarial", "S4T10"),
    ("S3_service_telugu", "S3T6"),
    ("S1_sales_outbound", "S1T8"),
]


def _make_ctx(script_id: str, script: dict, brain: str, index: int) -> CallContext:
    stack = ResolvedStack(
        combination_id=f"probe-{index}",
        tier="standard",
        mode="frontend",
        stt=StageSelection("sarvam", "saaras:v3", {}),
        llm=StageSelection("sarvam", LLM_MODEL, {"api_mode": LLM_MODE}),
        tts=StageSelection("gnani", "timbre-v3.0", {"speaker": "Shivani"}),
        language=script["language"],
    )
    return CallContext(
        call_id=f"probe-{script_id}",
        tenant_id="audit-tenant",
        agent_id=f"probe-agent-{index}",
        session_id=f"probe-session-{index}",
        channel="browser",
        direction=script["direction"],
        environment="development",
        tier="standard",
        resolved_stack=stack,
        compiled_brain_version="audit-v1",
        compiled_brain_text=brain,
        started_at=datetime.now(timezone.utc),
        storage_path="",
        pipeline="composed_voice",
    )


class RawProbeAdapter(SarvamLLMAdapter):
    """Captures the exact composed request, then inspects raw SSE payloads."""

    def __init__(self) -> None:
        super().__init__()
        self.findings: list[dict] = []
        self.captured_roles: list[str] = []
        self.captured_chars = 0
        self.has_delivery_contract = False

    async def _stream(self, input_messages=None, schema=None, **kwargs):
        model = self._model(kwargs)
        url = self._url(model, kwargs)
        messages = _chat_messages(input_messages, kwargs.get("transcript"))
        body = self._request_body(
            model=model, messages=messages, kwargs=kwargs, stream=True, schema=schema
        )
        self.captured_roles = [m.get("role", "") for m in messages]
        self.captured_chars = sum(len(str(m.get("content") or "")) for m in messages)
        self.has_delivery_contract = any(
            "Speech delivery contract" in str(m.get("content") or "") for m in messages
        )
        headers = self._headers(kwargs)
        await self._probe(url, headers, dict(body), "explicit_null")
        omitted = {k: v for k, v in body.items() if k != "reasoning_effort"}
        await self._probe(url, headers, omitted, "omitted")
        # Let the orchestrator finish cleanly; the probe text is never used.
        yield {"delta": "PROBE_ONLY", "language_context": {}}
        yield {
            "done": True,
            "text": "PROBE_ONLY",
            "language_context": {},
            "usage": {},
            "finish_reason": "stop",
        }

    async def _probe(self, url: str, headers: dict, body: dict, label: str) -> None:
        finding: dict = {
            "variant": label,
            "sent_reasoning_effort": "absent" if "reasoning_effort" not in body else body.get("reasoning_effort"),
            "status": None,
            "delta_keys": {},
            "content_chars": 0,
            "reasoning_chars": 0,
            "reasoning_sample": "",
            "content_sample": "",
            "finish_reason": None,
            "usage": {},
            "payloads": 0,
            "done_marker": False,
            "error": "",
        }
        self.findings.append(finding)
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    finding["status"] = response.status_code
                    if response.status_code >= 400:
                        raw = await response.aread()
                        finding["error"] = raw[:300].decode("utf-8", "replace")
                        return
                    async for line in response.aiter_lines():
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            finding["done_marker"] = True
                            continue
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        finding["payloads"] += 1
                        if payload.get("usage"):
                            finding["usage"] = payload["usage"]
                        choices = payload.get("choices")
                        if not isinstance(choices, list) or not choices:
                            continue
                        choice = choices[0] if isinstance(choices[0], dict) else {}
                        if choice.get("finish_reason"):
                            finding["finish_reason"] = choice["finish_reason"]
                        delta = choice.get("delta")
                        if not isinstance(delta, dict):
                            continue
                        for key, value in delta.items():
                            if isinstance(value, str):
                                finding["delta_keys"][key] = finding["delta_keys"].get(key, 0) + len(value)
                            else:
                                finding["delta_keys"][key] = finding["delta_keys"].get(key, 0) + 1
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                        if isinstance(reasoning, str) and reasoning:
                            finding["reasoning_chars"] += len(reasoning)
                            if len(finding["reasoning_sample"]) < 200:
                                finding["reasoning_sample"] += reasoning
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            finding["content_chars"] += len(content)
                            if len(finding["content_sample"]) < 200:
                                finding["content_sample"] += content
        except Exception as exc:  # keep the probe running
            finding["error"] = f"{type(exc).__name__}: {exc}"[:300]


async def main() -> int:
    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    scripts = {s["id"]: s for s in results["scripts"]}

    sys.path.insert(0, str(HERE))
    from run_audit import SCRIPTS  # type: ignore  # same directory, real definitions

    orchestrator = LiveTurnOrchestrator()
    md = ["# Empty-reply root-cause probe", "", f"Generated: {datetime.now(timezone.utc).isoformat()}", ""]
    summary: list[str] = []

    for index, (script_id, turn_id) in enumerate(PROBE_TURNS):
        script = next(s for s in SCRIPTS if s["id"] == script_id)
        stored = scripts[script_id]["turns"]
        turn_index = next(i for i, t in enumerate(stored) if t["id"] == turn_id)
        history: list[dict] = []
        for row in stored[:turn_index]:
            history += [
                {"role": "user", "content": row["user"]},
                {"role": "assistant", "content": row["reply"]},
            ]
        user_text = stored[turn_index]["user"]

        brain, *_ = await compile_agent_from_brief(
            brief=script["brief"], language=script["language"], interpret_brief=False
        )
        ctx = _make_ctx(script_id, script, brain, index)
        call_context.put(ctx)
        system_prompt = composed_system_prompt(ctx)
        messages = build_live_input(
            compiled_brain_text=system_prompt, history=history, transcript=user_text
        )
        adapter = RawProbeAdapter()
        error = ""
        try:
            async for _ in orchestrator._stream_composed_speech(
                adapter=adapter,
                messages=messages,
                schema=None,
                stream_kwargs={
                    "model": LLM_MODEL,
                    "api_mode": LLM_MODE,
                    "max_output_tokens": 500,
                    "temperature": 0.3,
                },
                call_id=ctx.call_id,
                provider="sarvam",
                model=LLM_MODEL,
            ):
                pass
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]

        md += [
            f"## {script_id} / {turn_id}",
            "",
            f"- Caller: {user_text}",
            f"- Request messages: {adapter.captured_roles} · {adapter.captured_chars} chars · "
            f"delivery contract present: {adapter.has_delivery_contract}",
            f"- Orchestrator error: {error or 'none'}",
            "",
        ]
        for finding in adapter.findings:
            md += [
                f"### `{finding['variant']}` (reasoning_effort: {finding['sent_reasoning_effort']})",
                "",
                f"- HTTP {finding['status']} · payloads {finding['payloads']} · [DONE] {finding['done_marker']} "
                f"· finish_reason {finding['finish_reason']}",
                f"- delta key bytes: {finding['delta_keys']}",
                f"- content chars: {finding['content_chars']} · reasoning chars: {finding['reasoning_chars']}",
                f"- usage: {finding['usage']}",
                f"- content sample: {finding['content_sample']!r}",
                f"- reasoning sample: {finding['reasoning_sample']!r}",
                f"- error: {finding['error'] or 'none'}",
                "",
            ]
            summary.append(
                f"{script_id}/{turn_id} [{finding['variant']}] HTTP {finding['status']} "
                f"content={finding['content_chars']} reasoning={finding['reasoning_chars']} "
                f"delta_keys={sorted(finding['delta_keys'])} finish={finding['finish_reason']} "
                f"usage={finding['usage']}"
            )
            print(summary[-1])

    (HERE / "probe_empty_reply.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nWrote {HERE / 'probe_empty_reply.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
