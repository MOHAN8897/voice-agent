"""Structured JSON parse + Luna reasoning for OpenAI HTTP completions."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import server.app as app_mod  # noqa: F401 — init provider registry before adapter imports
from server.providers.base import LLMConfig
from server.providers.openai_llm import (
    OpenAILLMAdapter,
    extract_responses_text,
    parse_structured_json,
)


def test_parse_truncated_agent_script_json():
    """Exact Luna truncation that produced Test Studio 500s."""
    payload = parse_structured_json('{"agent_script": "')
    assert payload["agent_script"] == ""


def test_parse_markdown_fenced_json():
    payload = parse_structured_json(
        '```json\n{"agent_script": "hello", "agent_name": "Ravi"}\n```'
    )
    assert payload["agent_script"] == "hello"
    assert payload["agent_name"] == "Ravi"


def test_parse_truncated_mid_string_keeps_prefix():
    payload = parse_structured_json('{"agent_script": "AGENT IDENTITY\\nRavi from Sai')
    assert payload["agent_script"].startswith("AGENT IDENTITY")
    assert "Ravi" in payload["agent_script"]


def test_extract_text_from_incomplete_output_items():
    response = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(text='{"ok": true}')],
            )
        ],
    )
    assert extract_responses_text(response) == '{"ok": true}'


@pytest.mark.asyncio
async def test_structured_completion_applies_luna_reasoning():
    captured: dict = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text='{"agent_name": "Ravi"}', output=[])

    class FakeClient:
        responses = FakeResponses()

    with patch("server.utils.http_clients.get_openai_client", return_value=FakeClient()):
        adapter = OpenAILLMAdapter()
        payload = await adapter.structured_completion(
            input_messages=[{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            schema={
                "type": "object",
                "properties": {"agent_name": {"type": "string"}},
                "required": ["agent_name"],
                "additionalProperties": False,
            },
            config=LLMConfig(provider="openai", model="gpt-5.6-luna"),
            schema_name="agent_calling_script",
            max_output_tokens=4000,
        )
    assert payload == {"agent_name": "Ravi"}
    assert captured["max_output_tokens"] == 4000
    assert captured["reasoning"] == {"effort": "none"}
    assert "temperature" not in captured
