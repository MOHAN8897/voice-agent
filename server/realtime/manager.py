"""Process-local registry: one RealtimeTextSession per call_id."""
from __future__ import annotations

from typing import Any, Callable

from server.realtime.models import DEFAULT_REALTIME_MODEL, live_openai_model
from server.realtime.providers.openai import OpenAIRealtimeTextAdapter
from server.realtime.text_session import RealtimeTextSession, build_session_instructions
from server.utils.logger import logger

AdapterFactory = Callable[[], Any]


class RealtimeTextManager:
    def __init__(self, adapter_factory: AdapterFactory | None = None) -> None:
        self._sessions: dict[str, RealtimeTextSession] = {}
        self._adapter_factory = adapter_factory or OpenAIRealtimeTextAdapter

    def get(self, call_id: str | None) -> RealtimeTextSession | None:
        if not call_id:
            return None
        return self._sessions.get(call_id)

    async def create(
        self,
        call_id: str,
        *,
        instructions: str | None = None,
        compiled_brain: str | None = None,
        model: str | None = None,
        language: str = "te-IN",
        caller_id: str | None = None,
        adapter: Any | None = None,
        wait_ready: bool = True,
        temperature: float | None = None,
    ) -> RealtimeTextSession:
        if call_id in self._sessions:
            raise RuntimeError(f"Realtime session already owns call_id={call_id}")
        text = instructions if instructions is not None else build_session_instructions(
            compiled_brain, caller_id=caller_id, language=language
        )
        live_model = live_openai_model(model)
        if temperature is None:
            try:
                from server.config.env import get_settings

                temperature = float(get_settings().openai_temperature)
            except Exception:
                temperature = None
        session = RealtimeTextSession(
            call_id,
            adapter=adapter or self._adapter_factory(),
            model=live_model or DEFAULT_REALTIME_MODEL,
            instructions=text,
            language=language,
            temperature=temperature,
        )
        self._sessions[call_id] = session
        try:
            if wait_ready:
                await session.start()
                logger.info("[REALTIME] session started call=%s model=%s", call_id, session.model)
            else:
                session.boot_in_background()
                logger.info("[REALTIME] session booting call=%s model=%s", call_id, session.model)
        except Exception:
            self._sessions.pop(call_id, None)
            raise
        return session

    async def note_spoken(self, call_id: str | None, text: str) -> None:
        session = self.get(call_id)
        if session is not None:
            await session.note_spoken(text)

    async def wait_until_ready(self, call_id: str | None, *, timeout: float = 12.0) -> bool:
        session = self.get(call_id)
        if session is None:
            return False
        return await session.wait_until_ready(timeout=timeout)

    async def cancel(self, call_id: str | None) -> None:
        session = self.get(call_id)
        if session is not None:
            await session.cancel_response()

    async def destroy(self, call_id: str | None) -> None:
        if not call_id:
            return
        session = self._sessions.pop(call_id, None)
        if session is None:
            return
        await session.close()
        logger.info("[REALTIME] session closed call=%s", call_id)

    def adopt_session(self, from_call_id: str, to_call_id: str) -> RealtimeTextSession | None:
        """Move a prewarmed Realtime socket from dial-time key to the live call_id."""
        session = self._sessions.pop(from_call_id, None)
        if session is None:
            return None
        session.call_id = to_call_id
        self._sessions[to_call_id] = session
        logger.info("[REALTIME] adopted prewarm %s -> %s", from_call_id, to_call_id)
        return session

    def reset_for_tests(self) -> None:
        self._sessions.clear()


realtime_text_manager = RealtimeTextManager()
