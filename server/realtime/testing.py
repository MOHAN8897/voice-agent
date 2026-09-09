"""In-process Realtime adapter for tests — no OpenAI WebSocket."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

ZERO_USAGE = {
    "input_tokens": 8,
    "output_tokens": 4,
    "cached_tokens": 0,
    "cache_write_tokens": 0,
    "audio_tokens": 0,
    "input_audio_tokens": 0,
    "output_audio_tokens": 0,
    "text_tokens": 12,
    "reasoning_tokens": 0,
}


class FakeRealtimeAdapter:
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.events_script = events
        self.sent: list[str] = []
        self.cancelled = 0
        self.connected = False
        self.closed = False
        self.model = ""
        self.instructions = ""

    async def connect(self, *, model: str, instructions: str, **_kwargs: Any) -> None:
        self.connected = True
        self.closed = False
        self.model = model
        self.instructions = instructions

    def discard_queued(self) -> None:
        return None

    def is_open(self) -> bool:
        return self.connected and not self.closed

    async def wait_ready(self, timeout: float = 8.0) -> None:
        return None

    async def send_user_text(self, text: str) -> None:
        self.sent.append(text)

    async def send_assistant_text(self, text: str) -> None:
        self.sent.append(f"__assistant__:{text}")

    async def start_response(self) -> None:
        self.sent.append("__response.create__")

    async def cancel_response(self) -> None:
        self.cancelled += 1

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        script = (
            list(self.events_script)
            if self.events_script is not None
            else [
                {"type": "text_delta", "delta": "Hello."},
                {
                    "type": "response_done",
                    "status": "completed",
                    "usage": dict(ZERO_USAGE),
                    "failed": False,
                },
            ]
        )
        for event in script:
            yield event

    async def close(self) -> None:
        self.closed = True
