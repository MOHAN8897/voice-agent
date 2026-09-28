"""Process-local registry: one Realtime voice (audio) session per call_id."""
from __future__ import annotations

from typing import Any, Callable

from server.realtime.models import (
    DEFAULT_REALTIME_MODEL,
    realtime_voice_config,
    realtime_voice_llm_provider,
)
from server.realtime.voice_factory import create_realtime_voice_adapter
from server.realtime.voice_instructions import build_realtime_voice_instructions
from server.utils.logger import logger

AdapterFactory = Callable[[], Any]


class RealtimeVoiceManager:
    def __init__(self, adapter_factory: AdapterFactory | None = None) -> None:
        self._sessions: dict[str, Any] = {}
        self._adapter_factory = adapter_factory
        self._meta: dict[str, dict[str, Any]] = {}

    def get(self, call_id: str | None) -> Any | None:
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
        voice: str | None = None,
        turn_detection: str | None = None,
        stack_override: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        wait_ready: bool = True,
    ) -> Any:
        if call_id in self._sessions:
            raise RuntimeError(f"Realtime voice session already owns call_id={call_id}")
        text = instructions if instructions is not None else build_realtime_voice_instructions(
            compiled_brain,
            model=model,
            stack_override=stack_override,
            caller_id=caller_id,
            language=language,
        )
        cfg = realtime_voice_config(stack_override)
        from server.services.transcription_policy import transcription_policy_from_stack

        tx_policy = transcription_policy_from_stack(stack_override)
        _provider, live_model = realtime_voice_llm_provider(stack_override, model)
        factory = self._adapter_factory or create_realtime_voice_adapter
        session = adapter or factory(stack_override=stack_override, model=live_model)
        self._sessions[call_id] = session
        self._meta[call_id] = {"instructions": text, "language": language}
        try:
            connect_kwargs: dict[str, Any] = {
                "model": live_model or DEFAULT_REALTIME_MODEL,
                "instructions": text,
                "voice": voice or cfg["voice"],
                "turn_detection": turn_detection or cfg["turn_detection"],
                "vad_eagerness": cfg.get("vad_eagerness"),
                "noise_reduction": cfg.get("noise_reduction"),
                "speed": cfg.get("speed"),
                "silence_ms": cfg.get("silence_ms"),
                "max_output_tokens": max_output_tokens,
            }
            if hasattr(session, "connect"):
                import inspect

                if "input_transcription_enabled" in inspect.signature(session.connect).parameters:
                    connect_kwargs["input_transcription_enabled"] = tx_policy.openai_session_input_transcription()
            await session.connect(**connect_kwargs)
            if wait_ready and hasattr(session, "wait_ready"):
                await session.wait_ready()
            logger.info("[REALTIME_VOICE] session started call=%s model=%s", call_id, live_model)
        except Exception:
            self._sessions.pop(call_id, None)
            self._meta.pop(call_id, None)
            raise
        return session

    async def cancel(self, call_id: str | None) -> None:
        session = self.get(call_id)
        if session is not None:
            await session.cancel_response()

    async def destroy(self, call_id: str | None) -> None:
        if not call_id:
            return
        session = self._sessions.pop(call_id, None)
        self._meta.pop(call_id, None)
        if session is None:
            return
        await session.close()
        logger.info("[REALTIME_VOICE] session closed call=%s", call_id)

    def adopt_session(self, from_call_id: str, to_call_id: str) -> Any | None:
        session = self._sessions.pop(from_call_id, None)
        if session is None:
            return None
        self._sessions[to_call_id] = session
        if from_call_id in self._meta:
            self._meta[to_call_id] = self._meta.pop(from_call_id)
        logger.info("[REALTIME_VOICE] adopted prewarm %s -> %s", from_call_id, to_call_id)
        return session

    def reset_for_tests(self) -> None:
        self._sessions.clear()
        self._meta.clear()


realtime_voice_manager = RealtimeVoiceManager()
