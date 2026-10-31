"""Static prompt bytes precede the per-turn clock so the provider's prefix cache holds."""
from __future__ import annotations

import json

import pytest

from server.call.live_turn_orchestrator import live_turn_orchestrator


class _NativeAdapter:
    uses_plain_live_speech = True

    async def stream_live_turn(self, **_kwargs):  # pragma: no cover - replaced below
        yield {"done": True, "text": ""}


async def _sent_messages(monkeypatch, clock: str) -> list[dict]:
    seen: dict = {}

    async def fake_turn(*, messages, **_kwargs):
        seen["messages"] = messages
        yield {"done": True, "text": "సరే."}

    monkeypatch.setattr(live_turn_orchestrator, "_stream_composed_turn", fake_turn)
    messages = [
        {"role": "developer", "content": "COMPILED BRAIN"},
        {"role": "developer", "content": clock},
        {"role": "user", "content": "హలో"},
    ]
    async for _ in live_turn_orchestrator._stream_composed_speech(
        adapter=_NativeAdapter(), messages=messages, schema=None, stream_kwargs={}, available_tools=[],
    ):
        pass
    return seen["messages"]


@pytest.mark.asyncio
async def test_delivery_contract_sits_before_the_dynamic_clock_and_the_prefix_is_identical(monkeypatch):
    first = await _sent_messages(monkeypatch, "Current local time: Friday 10:01. Receipts: []")
    second = await _sent_messages(monkeypatch, "Current local time: Friday 10:07. Receipts: [{\"outcome\": \"x\"}]")
    assert first[0]["content"] == "COMPILED BRAIN"
    assert first[1]["content"].startswith("Speech delivery contract")
    assert first[2]["content"].startswith("Current local time")
    # Everything before the per-turn message is byte-identical across turns.
    dump = lambda rows: json.dumps(rows[:2], ensure_ascii=False, sort_keys=True)  # noqa: E731
    assert dump(first) == dump(second)
    assert first[2] != second[2]
