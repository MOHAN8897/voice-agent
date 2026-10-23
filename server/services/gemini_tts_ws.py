"""Gemini TTS WebSocket upstream shim — browser-proxy and PSTN WebSocket compatible."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from server.config.env import get_settings
from server.providers.base import TTSConfig
from server.services.dev_secrets_store import dev_secrets_store

logger = logging.getLogger(__name__)


def connect_gemini_tts_ws(
    model: str | None = None,
    tts_config: TTSConfig | None = None,
    **_: Any,
):
    """Return a WebSocket-compatible connector for Gemini streaming TTS.

    Conforms to the Sarvam/Cartesia WebSocket interface expected by PstnTurnTtsSession:
    - send({"type": "config", "data": {...}})
    - send({"type": "ping"})
    - send({"type": "text", "data": {"text": ...}})
    - send({"type": "flush"})
    - async iteration yields audio chunks or final completion
    - on credit or quota exhaustion (HTTP 429/402), yields an explicit error with no silent fallback
    """
    settings = get_settings()
    key = dev_secrets_store.effective_secret("gemini_api_key") or settings.gemini_api_key or ""
    if not key:
        raise RuntimeError("Google Gemini API key not configured")

    resolved_model = (model or settings.gemini_tts_model or "gemini-3.8-flash-tts").strip()

    class _GeminiTtsProxy:
        def __init__(self, cm):
            self._cm = cm
            self._cfg: dict[str, Any] = {}
            self._model = resolved_model
            self._queue: asyncio.Queue[str] = asyncio.Queue()
            self._active_stream_task: asyncio.Task | None = None
            self._closed = False
            self._sample_rate = 24000
            self._initial_config = tts_config

        async def send(self, payload: str) -> None:
            if self._closed:
                return
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                return
            mtype = obj.get("type")
            if mtype == "config":
                self._cfg = dict(obj.get("data") or {})
                if self._cfg.get("model"):
                    self._model = str(self._cfg["model"])
                return
            if mtype == "ping":
                return
            if mtype == "text":
                text = str((obj.get("data") or {}).get("text") or "")
                if not text.strip():
                    return
                # Stream this text using Gemini TTS adapter
                self._active_stream_task = asyncio.create_task(self._stream_text(text))
                return
            if mtype == "flush":
                if self._active_stream_task and not self._active_stream_task.done():
                    await self._active_stream_task
                await self._queue.put(
                    json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}})
                )

        async def _stream_text(self, text: str) -> None:
            from server.providers.gemini_tts import GeminiTTSAdapter

            adapter = GeminiTTSAdapter(api_key=key)
            speaker = (
                self._cfg.get("speaker")
                or (self._initial_config.speaker if self._initial_config else None)
                or "Zephyr"
            )
            language = str(
                self._cfg.get("language_code")
                or (self._initial_config.language if self._initial_config else None)
                or "te-IN"
            )
            pace = self._cfg.get("pace")
            if pace is None and self._initial_config is not None:
                pace = self._initial_config.pace
            cfg = TTSConfig(
                provider="gemini",
                model=self._model,
                language=language,
                speaker=speaker,
                pace=pace,
            )
            try:
                async for chunk in adapter.stream_with_metadata(text, cfg):
                    if self._closed:
                        break
                    audio_b64 = base64.b64encode(chunk.audio_bytes).decode("ascii")
                    await self._queue.put(
                        json.dumps(
                            {
                                "type": "audio",
                                "data": {
                                    "audio": audio_b64,
                                    "event_type": "audio",
                                    "sample_rate": chunk.sample_rate,
                                    "speech_sample_rate": chunk.sample_rate,
                                },
                            }
                        )
                    )
            except Exception as exc:
                err_msg = str(exc)
                is_credits_error = (
                    "429" in err_msg
                    or "402" in err_msg
                    or "quota" in err_msg.lower()
                    or "resource_exhausted" in err_msg.lower()
                )
                error_payload = {
                    "type": "error",
                    "code": "credits_exhausted" if is_credits_error else "gemini_tts_error",
                    "message": (
                        f"Gemini TTS credits or quota exhausted ({err_msg})"
                        if is_credits_error
                        else f"Gemini TTS error: {err_msg}"
                    ),
                }
                await self._queue.put(json.dumps(error_payload))

        def __aiter__(self):
            return self

        async def __anext__(self) -> str:
            if self._closed and self._queue.empty():
                raise StopAsyncIteration
            msg = await self._queue.get()
            return msg

        async def close(self) -> None:
            if self._closed:
                return
            self._closed = True
            if self._active_stream_task and not self._active_stream_task.done():
                self._active_stream_task.cancel()
                try:
                    await self._active_stream_task
                except asyncio.CancelledError:
                    pass

    class _Connector:
        async def __aenter__(self):
            return _GeminiTtsProxy(self)

        async def __aexit__(self, exc_type, exc, tb):
            pass

    return _Connector()
