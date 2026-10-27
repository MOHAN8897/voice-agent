from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from server.providers import sarvam_llm
from server.services import sarvam_ws


def _mock_http(monkeypatch, payload, *, stream=True):
    requests = []
    original = httpx.AsyncClient

    def handle(request):
        requests.append(request)
        if stream:
            content = "\n\n".join("data: " + json.dumps(item) for item in payload)
            return httpx.Response(200, content=(content + "\n\ndata: [DONE]\n\n").encode())
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        sarvam_llm.httpx, "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setattr(sarvam_llm, "get_settings", lambda: SimpleNamespace(
        request_timeout_ms=1000, max_response_length=96,
    ))
    return requests


@pytest.mark.asyncio
async def test_v1_conversations_streams_selected_model_without_default_thinking(monkeypatch):
    requests = _mock_http(monkeypatch, [
        {"choices": [{"delta": {"reasoning_content": "Private thought", "content": "Hello."}}]},
        {"choices": [], "usage": {"prompt_tokens": 19, "completion_tokens": 3, "total_tokens": 22}},
    ])
    events = [event async for event in sarvam_llm.SarvamLLMAdapter(api_key="unit-key").stream_live_turn(
        model="sarvam-105b-conversations", api_mode="chat_completions_v1",
        input_messages=[{"role": "user", "content": "Hi"}],
    )]

    assert requests[0].url.path == "/v1/chat/completions"
    body = json.loads(requests[0].content)
    assert body["model"] == "sarvam-105b-conversations"
    assert body["reasoning_effort"] is None
    assert body["stream_options"] == {"include_usage": True}
    assert events[0]["delta"] == "Hello."
    assert events[-1]["usage"]["input_tokens"] == 19
    assert events[-1]["usage"]["output_tokens"] == 3
    assert "Private thought" not in json.dumps(events)


def test_sarvam_tools_wrap_internal_flat_declarations_and_preserve_chat_declarations():
    function = {"name": "DIAGNOSTIC_PING", "description": "Synthetic connection test",
                "parameters": {"type": "object", "properties": {}, "required": []}}
    assert sarvam_llm._chat_tools([{"type": "function", **function}]) == [
        {"type": "function", "function": function},
    ]
    assert sarvam_llm._chat_tools([{"type": "function", "function": function}]) == [
        {"type": "function", "function": function},
    ]
    with pytest.raises(ValueError, match="named function"):
        sarvam_llm._chat_tools([{"parameters": {}}])


async def test_incomplete_sse_keeps_terminal_usage_including_reasoning(monkeypatch):
    from server.providers.llm_protocol import IncompleteTurnError

    requests = _mock_http(monkeypatch, [
        {"choices": [{"delta": {"content": "Unfinished"}, "finish_reason": "length"}]},
        {"choices": [], "usage": {"prompt_tokens": 99, "completion_tokens": 80,
            "completion_tokens_details": {"reasoning_tokens": 70}}},
    ])
    with pytest.raises(IncompleteTurnError) as raised:
        async for _ in sarvam_llm.SarvamLLMAdapter(api_key="unit-key").stream_live_turn(
            model="sarvam-105b-conversations", api_mode="chat_completions_v1",
            input_messages=[{"role": "user", "content": "Question"}]):
            pass
    assert len(requests) == 1
    assert raised.value.finish_reason == "length"
    assert raised.value.partial_text == "Unfinished"
    assert raised.value.usage["output_tokens"] == 80
    assert raised.value.usage["reasoning_tokens"] == 70


@pytest.mark.asyncio
async def test_plain_phone_delivery_rejects_json_before_releasing_buffered_speech(monkeypatch):
    from server.providers.llm_protocol import IncompleteTurnError

    _mock_http(monkeypatch, [
        {"choices": [{"delta": {"content": '{"spoken_response":"Hello","end_call":{"decision":"close"}}'}}]},
    ])
    spoken = []
    with pytest.raises(IncompleteTurnError) as exc:
        async for event in sarvam_llm.SarvamLLMAdapter(api_key="unit-key").stream_live_turn(
            model="sarvam-105b-conversations", api_mode="chat_completions_v1",
            input_messages=[{"role": "user", "content": "Tell me the price"}],
            speech_only=True, buffer_response=True,
        ):
            if event.get("delta"):
                spoken.append(event["delta"])
    assert exc.value.finish_reason == "unexpected_speech_format"
    assert spoken == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode, model, message", [
    ("unary_rest", "sarvam-105b-conversations", "approved chat completion"),
    ("chat_completions_v1", "glm5.3", "unavailable on Chat Completions V1"),
])
async def test_v1_rejects_wrong_transport_and_model_before_http(monkeypatch, mode, model, message):
    requests = _mock_http(monkeypatch, [])
    with pytest.raises(ValueError, match=message):
        async for _ in sarvam_llm.SarvamLLMAdapter(api_key="unit-key").stream_live_turn(
            model=model, api_mode=mode, input_messages=[{"role": "user", "content": "Hi"}],
        ):
            pass
    assert not requests


@pytest.mark.asyncio
async def test_v1_structured_completion_preserves_schema_and_explicit_api_mode(monkeypatch):
    requests = _mock_http(monkeypatch, {"choices": [{"message": {"content": '{"ok":true}'}}]}, stream=False)
    from server.providers.base import LLMConfig

    result = await sarvam_llm.SarvamLLMAdapter(api_key="unit-key").structured_completion(
        input_messages=[{"role": "user", "content": "Return a connectivity result."}],
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        config=LLMConfig(provider="sarvam", model="sarvam-105b-conversations", max_tokens=32),
        api_mode="chat_completions_v1",
    )
    assert result == {"ok": True}
    assert requests[0].url.path == "/v1/chat/completions"
    body = json.loads(requests[0].content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["max_tokens"] == 32
    assert body["reasoning_effort"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("modern", [True, False])
async def test_websocket_header_selection_handles_deferred_legacy_connection(monkeypatch, modern):
    captured = {}

    class Connection:
        async def __aenter__(self):
            assert "additional_headers" not in captured["extra"]
            return self

        async def __aexit__(self, *_args):
            pass

    if modern:
        def connect(uri, *, additional_headers=None, **kwargs):
            captured.update(uri=uri, headers=additional_headers, extra=kwargs)
            return Connection()
    else:
        def connect(uri, *, extra_headers=None, **kwargs):
            captured.update(uri=uri, headers=extra_headers, extra=kwargs)
            return Connection()

    monkeypatch.setattr(sarvam_ws.websockets, "connect", connect)
    async with sarvam_ws._connect("wss://example.invalid/ws", {"api-subscription-key": "unit-key"}):
        pass
    assert captured["headers"] == {"api-subscription-key": "unit-key"}
    assert captured["extra"]["max_size"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("use_tools", [False, True])
async def test_composed_orchestrator_pins_v1_and_records_each_provider_request(monkeypatch, use_tools):
    import importlib

    orchestrator_module = importlib.import_module("server.call.live_turn_orchestrator")
    import server.providers
    from server.providers.base import StageSelection
    from server.services.saas import composed_costing

    calls = []
    recorded = []

    class Adapter:
        provider_id = "sarvam"

        async def stream_live_turn(self, **kwargs):
            calls.append(kwargs)
            yield {"delta": "Hello."}
            yield {"done": True, "text": "Hello.", "usage": {"input_tokens": 19, "output_tokens": 3}}

        async def stream_structured_turn(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                yield {"done": True, "text": "", "usage": {"input_tokens": 21, "output_tokens": 6, "cached_tokens": 2},
                       "tool_calls": [{"id": "synthetic-tool", "function": {"name": "DIAGNOSTIC_PING", "arguments": "{}"}}]}
            else:
                yield {"done": True, "text": "Connection test passed.", "usage": {"input_tokens": 30, "output_tokens": 9}}

    registry = SimpleNamespace(
        get_llm=lambda _provider: Adapter(),
        is_provider_enabled=lambda *_args: True,
        is_model_allowed=lambda *_args: True,
    )
    monkeypatch.setattr(server.providers, "get_provider_registry", lambda: registry)
    monkeypatch.setattr(orchestrator_module, "get_settings", lambda: SimpleNamespace(use_provider_registry=True, composed_first_attempt_max_tokens=1280, composed_retry_max_tokens=2560))
    monkeypatch.setattr(composed_costing, "record_composed_stage_usage", lambda *args: recorded.append(args))
    orchestrator = orchestrator_module.LiveTurnOrchestrator()
    tools = [{"name": "DIAGNOSTIC_PING"}] if use_tools else []
    monkeypatch.setattr(orchestrator, "_load_composed_tenant_tools", AsyncMock(return_value=tools))
    monkeypatch.setattr(orchestrator, "_execute_composed_tools", AsyncMock(return_value=[]))
    ctx = SimpleNamespace(
        pipeline="composed_voice", callback_request_text="",
        resolved_stack=SimpleNamespace(llm=StageSelection(
            "sarvam", "sarvam-105b-conversations", {"api_mode": "chat_completions_v1"},
        )),
    )
    events = [event async for event in orchestrator._stream_llm(
        ctx=ctx, call_id="synthetic-call", transcript="Hello", input_messages=[{"role": "user", "content": "Hi"}],
    )]

    assert len(calls) == (2 if use_tools else 1)
    assert all(call["api_mode"] == "chat_completions_v1" for call in calls)
    assert all(call["model"] == "sarvam-105b-conversations" for call in calls)
    assert len(recorded) == len(calls)
    assert all(record[:2] == ("synthetic-call", "llm") for record in recorded)
    if use_tools:
        assert calls[1]["tools"] == tools
        assert calls[1]["tool_choice"] == "none"
        assert recorded[0][2] == {"input_tokens": 21, "output_tokens": 6, "cached_tokens": 2}
        assert recorded[1][2] == {"input_tokens": 30, "output_tokens": 9}
        assert events[-1]["text"] == "Connection test passed."
    else:
        assert recorded[0][2] == {"input_tokens": 19, "output_tokens": 3}
