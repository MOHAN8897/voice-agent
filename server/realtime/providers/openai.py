"""OpenAI Realtime GA adapter — text in, text out, never audio."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from server.realtime.models import DEFAULT_REALTIME_MODEL, END_CALL_TOOL, LIVE_MAX_OUTPUT_TOKENS
from server.realtime.usage import extract_realtime_usage
from server.utils.logger import logger


def _event_type(event: Any) -> str:
    if isinstance(event, dict):
        return str(event.get("type") or "")
    return str(getattr(event, "type", "") or "")


def _event_field(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(name, default)
    return getattr(event, name, default)


def _response_id(event: Any) -> str:
    rid = _event_field(event, "response_id")
    if rid:
        return str(rid)
    response = _event_field(event, "response")
    if isinstance(response, dict):
        return str(response.get("id") or "")
    return str(getattr(response, "id", "") or "")


class OpenAIRealtimeTextAdapter:
    """Persistent OpenAI Realtime WebSocket. Audio events are never sent."""

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._conn: Any = None
        self._manager: Any = None
        self._ready = asyncio.Event()
        self._configuration_error: str | None = None
        self._configured = False
        self._events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._pump_task: asyncio.Task | None = None
        self._closed = False
        self._active_response_id: str | None = None
        self._current_output_item_ids: list[str] = []
        self._response_idle = asyncio.Event()
        self._response_idle.set()
        self._response_lock = asyncio.Lock()
        self._accepting = False
        self._max_output_tokens = LIVE_MAX_OUTPUT_TOKENS
        self.model = DEFAULT_REALTIME_MODEL

    async def connect(
        self,
        *,
        model: str,
        instructions: str,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        from openai import AsyncOpenAI

        from server.config.env import get_settings

        # GA Realtime rejects `temperature` (unknown_parameter) and drops the whole
        # session.update — which left calls greeting-only with empty assistant turns.
        _ = temperature
        settings = get_settings()
        self.model = model or DEFAULT_REALTIME_MODEL
        self._max_output_tokens = int(max_output_tokens or LIVE_MAX_OUTPUT_TOKENS)
        self._closed = False
        self._accepting = False
        self._active_response_id = None
        self._current_output_item_ids = []
        self._response_idle = asyncio.Event()
        self._response_idle.set()
        self._response_lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._configuration_error = None
        self._configured = False
        self._events = asyncio.Queue()
        key = self._api_key or settings.openai_api_key
        client = AsyncOpenAI(api_key=key)
        self._manager = client.realtime.connect(model=self.model)
        self._conn = await self._manager.enter()
        self._pump_task = asyncio.create_task(self._pump(), name="openai-realtime-recv")
        await self._conn.send(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": self.model,
                    "instructions": instructions,
                    "output_modalities": ["text"],
                    "max_output_tokens": self._max_output_tokens,
                    "tools": [END_CALL_TOOL],
                    "tool_choice": "auto",
                    "audio": {"input": {"turn_detection": None}},
                },
            }
        )

    def is_open(self) -> bool:
        return (
            not self._closed
            and self._conn is not None
            and self._pump_task is not None
            and not self._pump_task.done()
        )

    async def wait_ready(self, timeout: float = 8.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        if self._configuration_error:
            raise RuntimeError(self._configuration_error)
        if not self._configured or not self.is_open():
            raise ConnectionError("Realtime disconnected before session.updated")

    async def send_assistant_text(self, text: str) -> None:
        if self._conn is None:
            raise RuntimeError("realtime connection is not open")
        await self._conn.send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                },
            }
        )

    async def send_user_text(self, text: str) -> None:
        if self._conn is None:
            raise RuntimeError("realtime connection is not open")
        await self._conn.send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )

    async def reconcile_spoken(self, text: str) -> None:
        """Replace the latest generated text items with what reached the handset."""
        if self._conn is None or not self.is_open():
            raise RuntimeError("realtime connection is not open")
        async with self._response_lock:
            # Conversation mutations must happen only after OpenAI acknowledges the
            # interrupted response. Local task cancellation alone does not make the
            # server-side response idle.
            if not self._response_idle.is_set():
                await self._cancel_response_locked()
            item_ids = list(dict.fromkeys(self._current_output_item_ids))
            for item_id in item_ids:
                await self._conn.send(
                    {"type": "conversation.item.delete", "item_id": item_id}
                )
            if text.strip():
                await self.send_assistant_text(text.strip())
            self._current_output_item_ids = []
            self._active_response_id = None

    async def start_response(self) -> None:
        if self._conn is None:
            raise RuntimeError("realtime connection is not open")
        async with self._response_lock:
            if not self._response_idle.is_set():
                await self._cancel_response_locked()
            self._accepting = True
            self._active_response_id = None
            self._current_output_item_ids = []
            self._response_idle.clear()
            try:
                await self._conn.send(
                    {
                        "type": "response.create",
                        "response": {
                            "output_modalities": ["text"],
                            "max_output_tokens": self._max_output_tokens,
                        },
                    }
                )
            except Exception:
                self._accepting = False
                self._response_idle.set()
                raise

    async def cancel_response(self) -> None:
        async with self._response_lock:
            await self._cancel_response_locked()

    async def _cancel_response_locked(self) -> None:
        had_active_response = not self._response_idle.is_set()
        self._accepting = False
        if self._conn is None:
            self._active_response_id = None
            self._response_idle.set()
            return
        if not had_active_response:
            self._active_response_id = None
            return
        try:
            await self._conn.send({"type": "response.cancel"})
            await asyncio.wait_for(self._response_idle.wait(), timeout=1.5)
        except Exception as e:
            logger.warning("[REALTIME] cancel failed: %s", str(e)[:160])
            raise
        finally:
            self._active_response_id = None

    def discard_queued(self) -> None:
        self._accepting = False
        self._active_response_id = None
        dumped = 0
        while True:
            try:
                item = self._events.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None:
                self._events.put_nowait(None)
                break
            dumped += 1
        if dumped:
            logger.info("[REALTIME] discarded %s stale queued events", dumped)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._events.get()
            if item is None:
                break
            yield item

    async def close(self) -> None:
        self._closed = True
        self._accepting = False
        self._active_response_id = None
        self._response_idle.set()
        if self._pump_task and not self._pump_task.done():
            self._pump_task.cancel()
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
        if self._manager is not None:
            try:
                await self._manager.__aexit__(None, None, None)
            except Exception:
                pass
            self._manager = None
        await self._events.put(None)

    async def _pump(self) -> None:
        conn = self._conn
        if conn is None:
            return
        try:
            async for event in conn:
                kind = _event_type(event)
                if kind in ("session.created", "session.updated", "error"):
                    if kind == "session.updated":
                        self._configured = True
                        self._ready.set()
                    if kind == "error":
                        err = _event_field(event, "error") or {}
                        message = (
                            err
                            if isinstance(err, str)
                            else str(_event_field(err, "message") or err or kind)
                        )
                        logger.warning("[REALTIME] session event error: %s", message[:240])
                        if not self._configured:
                            self._configuration_error = message[:240]
                            self._ready.set()
                        await self._events.put({"type": "error", "message": message[:240]})
                        continue
                    continue
                normalized = self._normalize(event)
                if normalized is None:
                    continue
                await self._events.put(normalized)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning("[REALTIME] recv loop ended: %s", str(e)[:200])
            await self._events.put({"type": "error", "message": str(e)[:240]})
        finally:
            self._ready.set()
            await self._events.put(None)

    def _belongs_to_active_response(self, event: Any) -> bool:
        if not self._accepting:
            return False
        rid = _response_id(event)
        if self._active_response_id and rid and rid != self._active_response_id:
            return False
        if rid and not self._active_response_id:
            self._active_response_id = rid
        return True

    def _normalize(self, event: Any) -> dict[str, Any] | None:
        kind = _event_type(event)
        if kind == "response.created":
            if self._accepting:
                self._current_output_item_ids = []
                rid = _response_id(event)
                if rid:
                    self._active_response_id = rid
            return None
        if kind == "response.output_item.added":
            if not self._belongs_to_active_response(event):
                return None
            item = _event_field(event, "item")
            item_id = str(_event_field(item, "id") or "")
            if item_id and item_id not in self._current_output_item_ids:
                self._current_output_item_ids.append(item_id)
            return None
        if kind == "response.output_text.delta":
            if not self._belongs_to_active_response(event):
                return None
            return {"type": "text_delta", "delta": str(_event_field(event, "delta") or "")}
        if kind == "response.output_text.done":
            if not self._belongs_to_active_response(event):
                return None
            return {"type": "text_done", "text": str(_event_field(event, "text") or "")}
        if kind == "response.function_call_arguments.done":
            if not self._belongs_to_active_response(event):
                return None
            return {
                "type": "function_call",
                "name": str(_event_field(event, "name") or ""),
                "arguments": _event_field(event, "arguments") or "",
            }
        if kind == "response.done":
            response = _event_field(event, "response")
            for item in (_event_field(response, "output") or []):
                item_id = str(_event_field(item, "id") or "")
                if item_id and item_id not in self._current_output_item_ids:
                    self._current_output_item_ids.append(item_id)
            # After cancel, _accepting is False and response_id was cleared — a late
            # response.done still carries usage but text deltas were dropped. Treating
            # that as a normal empty reply archived silence after short affirmations.
            if not self._accepting:
                self._active_response_id = None
                self._response_idle.set()
                return {"type": "cancelled"}
            if self._active_response_id and not self._belongs_to_active_response(event):
                return None
            self._accepting = False
            self._response_idle.set()
            status = str(_event_field(response, "status") or "")
            usage = extract_realtime_usage(response)
            failed = status == "failed"
            cancelled = status == "cancelled"
            if cancelled:
                self._active_response_id = None
                return {"type": "cancelled", "usage": usage}
            return {
                "type": "response_done",
                "status": status,
                "usage": usage,
                "failed": failed,
                # Final output is authoritative when a tool-name/arguments event
                # was missing or a response contained only a function call.
                "output": [
                    {
                        "type": _event_field(item, "type"),
                        "name": _event_field(item, "name"),
                        "arguments": _event_field(item, "arguments"),
                        "content": [
                            {"type": _event_field(part, "type"), "text": _event_field(part, "text")}
                            for part in (_event_field(item, "content") or [])
                        ],
                    }
                    for item in (_event_field(response, "output") or [])
                ],
            }
        if kind in ("error", "response.failed"):
            err = _event_field(event, "error") or {}
            message = err if isinstance(err, str) else str(_event_field(err, "message") or err or kind)
            if kind == "response.failed" or "no active response" in message.lower():
                self._accepting = False
                self._active_response_id = None
                self._response_idle.set()
            return {"type": "error", "message": message[:240]}
        if kind == "response.cancelled":
            self._accepting = False
            self._active_response_id = None
            self._response_idle.set()
            return {"type": "cancelled"}
        return None

    @staticmethod
    def debug_event(event: Any) -> str:
        try:
            if hasattr(event, "model_dump_json"):
                return event.model_dump_json()[:400]
            return json.dumps(event, default=str)[:400]
        except Exception:
            return str(event)[:400]
