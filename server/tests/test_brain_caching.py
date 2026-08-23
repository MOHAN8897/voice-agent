from unittest.mock import AsyncMock, patch

import pytest

from server.agent.instruction_builder import build_brain_request_input
from server.services.prompt_cache_key import caching_enabled, compute_cache_key


def test_compute_cache_key_stable():
    k1 = compute_cache_key("same prompt", 1500)
    k2 = compute_cache_key("same prompt", 1500)
    k3 = compute_cache_key("other prompt", 1500)
    assert k1 == k2
    assert k1 != k3
    assert "telugu-voice:v5:cfg-" in k1


def test_caching_enabled_gpt56():
    assert caching_enabled("gpt-5.6-luna", 1500) is True
    assert caching_enabled("gpt-5.6-luna", 1023) is False
    assert caching_enabled("gpt-5.5", 1500) is False


def test_brain_request_cache_block():
    msgs = build_brain_request_input(
        brain_prompt="brain",
        history=[],
        transcript="hi",
        enable_cache=True,
    )
    assert "prompt_cache_breakpoint" in msgs[0]["content"][0]


@pytest.mark.asyncio
async def test_generate_response_applies_cache_kwargs(monkeypatch):
    from server.services import openai_brain_service as svc

    captured = {}

    class FakeResponse:
        output_text = "సరే"
        output = []
        usage = type("U", (), {
            "input_tokens": 1500,
            "output_tokens": 10,
            "total_tokens": 1510,
            "input_tokens_details": type("D", (), {"cached_tokens": 1400, "cache_write_tokens": 0})(),
        })()
        id = "resp_test"

    async def fake_create(*args, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    fake_responses = type("R", (), {"create": fake_create})()
    fake_client = type("C", (), {"responses": fake_responses})()
    monkeypatch.setattr(svc, "_get_client", lambda: fake_client)

    with patch.object(svc.conversation_manager, "get_context_for_brain", return_value=[]), patch.object(
        svc.conversation_manager, "add_turn", return_value=None
    ), patch.object(
        svc.instruction_store, "get_brain_prompt", return_value="x" * 5000
    ):
        result = await svc.generate_response(
            transcript="hello",
            session_id="cache-test",
            openai_model="gpt-5.6-luna",
        )

    assert "instructions" not in captured
    assert captured.get("prompt_cache_key")
    assert captured.get("prompt_cache_options", {}).get("mode") == "explicit"
    assert captured["input"][0]["role"] == "developer"
    assert result["usage"]["cached_tokens"] == 1400
