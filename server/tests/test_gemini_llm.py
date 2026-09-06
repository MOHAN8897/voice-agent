"""Gemini live-turn adapter — same memory layout and cache prefix as OpenAI."""
from __future__ import annotations

import json

import httpx
import pytest

from server.agent.instruction_builder import build_live_input
from server.call.live_turn_schema import LIVE_TURN_JSON_SCHEMA
from server.providers.gemini_llm import GeminiLLMAdapter, gemini_usage_from_metadata, thinking_config_for
from server.providers.openai_messages import openai_input_to_gemini, to_chat_messages


def test_to_chat_messages_keeps_developer_brain():
    msgs = to_chat_messages(
        [
            {"role": "developer", "content": [{"type": "input_text", "text": "BRAIN"}]},
            {"role": "user", "content": "hi"},
        ]
    )
    assert msgs[0] == {"role": "system", "content": "BRAIN"}
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_gemini_keeps_brain_in_system_instruction():
    msgs = build_live_input(
        compiled_brain_text="STABLE BRAIN",
        history=[],
        transcript="hi",
        enable_cache=True,
        memory_projection="name: Ravi",
        rolling_summary="Caller is Ravi",
    )
    system, contents = openai_input_to_gemini(msgs)
    assert system == "STABLE BRAIN"
    joined = json.dumps(contents)
    assert "name: Ravi" in joined
    assert "Caller is Ravi" in joined
    assert "STABLE BRAIN" not in joined
    assert all(c["role"] in ("user", "model") for c in contents)


def test_thinking_config_for_voice_latency():
    assert thinking_config_for("gemini-3.5-flash-lite") == {"thinkingLevel": "MINIMAL"}
    assert thinking_config_for("gemini-3.7-flash") == {"thinkingLevel": "LOW"}
    assert thinking_config_for("gemini-3.8-flash") == {"thinkingLevel": "LOW"}
    assert thinking_config_for("gemini-2.5-flash") is None


def test_gemini_usage_maps_cached_tokens():
    usage = gemini_usage_from_metadata(
        {
            "promptTokenCount": 2500,
            "candidatesTokenCount": 12,
            "totalTokenCount": 2512,
            "cachedContentTokenCount": 2000,
        }
    )
    assert usage["input_tokens"] == 2500
    assert usage["output_tokens"] == 12
    assert usage["cached_tokens"] == 2000


@pytest.mark.asyncio
async def test_openai_adapter_drops_model_kwarg(monkeypatch):
    import inspect

    from server.providers.openai_llm import OpenAILLMAdapter
    from server.services import openai_brain_service as svc

    captured: dict = {}
    original_sig = inspect.signature(svc.generate_response_stream)

    async def fake_stream(**kwargs):
        captured.update(kwargs)
        yield {"delta": "hi"}
        yield {"done": True, "text": "hi"}

    fake_stream.__signature__ = original_sig  # type: ignore[attr-defined]
    monkeypatch.setattr(svc, "generate_response_stream", fake_stream)

    chunks = []
    async for event in OpenAILLMAdapter().stream_live_turn(
        input_messages=[{"role": "user", "content": "hi"}],
        schema=None,
        model="gpt-5.6-luna",
        openai_model="gpt-5.6-luna",
        transcript="hi",
        session_id="openai-kw",
        bogus="drop-me",
    ):
        chunks.append(event)
    assert "model" not in captured
    assert "bogus" not in captured
    assert captured["openai_model"] == "gpt-5.6-luna"
    assert captured["transcript"] == "hi"
    assert captured["input_messages"][0]["content"] == "hi"
    assert any(c.get("delta") == "hi" for c in chunks)


@pytest.mark.asyncio
async def test_gemini_stream_structured_turn_and_memory(monkeypatch):
    monkeypatch.setattr("server.providers.gemini_llm._api_key", lambda: "gem-test")
    msgs = build_live_input(
        compiled_brain_text="STABLE BRAIN",
        history=[],
        transcript="hi",
        enable_cache=True,
        memory_projection="name: Ravi",
        rolling_summary="Caller is Ravi",
    )
    captured: dict = {}
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"spoken_response": "ok", "memory_update": '
                                '{"operations": [{"op": "set_fact", "key": "name", "value": "Ravi"}]}, '
                                '"end_call": {"should_end": false, "reason": "none", "farewell": ""}}'
                            )
                        }
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 2500,
            "candidatesTokenCount": 8,
            "totalTokenCount": 2508,
            "cachedContentTokenCount": 2000,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, text=f"data: {json.dumps(payload)}\n\n")

    orig_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return orig_client(*args, **kwargs)

    monkeypatch.setattr("server.providers.gemini_llm.httpx.AsyncClient", factory)

    events = []
    async for event in GeminiLLMAdapter().stream_structured_turn(
        input_messages=msgs,
        schema=LIVE_TURN_JSON_SCHEMA,
        transcript="hi",
        session_id="gemini-mem-test",
        language_code="te-IN",
        model="gemini-3.5-flash-lite",
    ):
        events.append(event)

    body = captured["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "STABLE BRAIN"
    contents_blob = json.dumps(body["contents"])
    assert "name: Ravi" in contents_blob
    assert "Caller is Ravi" in contents_blob
    assert "STABLE BRAIN" not in contents_blob
    assert "streamGenerateContent" in captured["url"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "MINIMAL"
    done = events[-1]
    assert done["done"] is True
    assert done["text"] == "ok"
    assert done["memory_update"]["operations"][0]["value"] == "Ravi"
    assert done["usage"]["cached_tokens"] == 2000
