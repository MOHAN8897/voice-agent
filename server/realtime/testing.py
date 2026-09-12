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


class FakeRealtimeVoiceAdapter:
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.events_script = events
        self.appended: list[bytes] = []
        self.cancelled = 0
        self.connected = False
        self.closed = False
        self.model = ""
        self.instructions = ""
        self.voice = ""
        self.turn_detection = ""
        self.started_responses: list[str] = []
        self.noted_assistant: list[str] = []
        self.last_session: dict[str, Any] | None = None
        self.max_output_tokens: int | None = None
        self.cleared_input = 0
        self.deleted_item_ids: list[str] = []
        self.auto_response_states: list[bool] = []
        self._poll_events: list[dict[str, Any]] = []
        self._poll_index = 0

    def set_poll_events(self, events: list[dict[str, Any]]) -> None:
        self._poll_events = list(events)
        self._poll_index = 0

    async def poll_event(self, timeout: float = 0.5) -> dict[str, Any] | None:
        _ = timeout
        if self._poll_index >= len(self._poll_events):
            return None
        event = self._poll_events[self._poll_index]
        self._poll_index += 1
        return event

    async def delete_synthetic_response_items(self) -> None:
        self.deleted_item_ids.append("synthetic")

    async def connect(self, *, model: str, instructions: str, voice: str | None = None, turn_detection: str | None = None, **_kwargs: Any) -> None:
        self.connected = True
        self.closed = False
        self.model = model
        self.instructions = instructions
        self.voice = str(voice or "")
        self.turn_detection = str(turn_detection or "")
        tokens = _kwargs.get("max_output_tokens")
        self.max_output_tokens = int(tokens) if tokens is not None else None

    async def update_instructions(self, instructions: str) -> None:
        self.instructions = instructions

    async def set_auto_response(self, enabled: bool) -> None:
        self.auto_response_states.append(bool(enabled))

    def is_open(self) -> bool:
        return self.connected and not self.closed

    async def wait_ready(self, timeout: float = 8.0) -> None:
        return None

    async def append_pcm16(self, pcm16: bytes) -> None:
        self.appended.append(pcm16)

    async def note_assistant_text(self, text: str) -> None:
        self.noted_assistant.append(text)

    async def start_response(self, *, instructions: str | None = None) -> None:
        self.started_responses.append(instructions or "")

    async def cancel_response(self) -> None:
        self.cancelled += 1

    async def submit_function_output(self, *, call_id: str, output: str) -> None:
        self.started_responses.append(f"fn:{call_id}:{output}")

    async def clear_output_audio(self) -> None:
        return None

    async def clear_input_audio(self) -> None:
        self.cleared_input += 1

    def discard_queued(self) -> None:
        return None

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        script = list(self.events_script) if self.events_script is not None else []
        for event in script:
            yield event

    async def close(self) -> None:
        self.closed = True
