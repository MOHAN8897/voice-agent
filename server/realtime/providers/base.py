"""Provider-neutral realtime text adapter interface."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol


class RealtimeTextAdapter(Protocol):
    async def connect(
        self,
        *,
        model: str,
        instructions: str,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None: ...

    async def wait_ready(self, timeout: float = 8.0) -> None: ...

    async def send_user_text(self, text: str) -> None: ...

    async def send_assistant_text(self, text: str) -> None: ...

    async def start_response(self) -> None: ...

    async def cancel_response(self) -> None: ...

    def events(self) -> AsyncIterator[dict[str, Any]]: ...

    def discard_queued(self) -> None: ...

    async def close(self) -> None: ...
