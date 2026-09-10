"""One persistent text-only Realtime session per call_id."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Literal

from server.call.end_call_validate import caller_firm_refusal, caller_requested_hangup, caller_requested_callback
from server.call.hangup_judge import agent_spoke_closing
from server.realtime.end_call_tool import parse_end_call_tool
from server.realtime.language_guard import filter_unrelated_scripts
from server.realtime.models import (
    CANCEL_DRAIN_TIMEOUT_SEC,
    DEFAULT_REALTIME_MODEL,
    LIVE_MAX_OUTPUT_TOKENS,
    REALTIME_TURN_TIMEOUT_SEC,
)
from server.realtime.usage import assert_zero_audio_tokens
from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE, LiveReplyStreamCap
from server.utils.logger import logger

SessionState = Literal["idle", "streaming", "cancelling", "closed"]


def _adapter_is_open(adapter: Any) -> bool:
    checker = getattr(adapter, "is_open", None)
    if callable(checker):
        return bool(checker())
    connected = getattr(adapter, "connected", True)
    closed = getattr(adapter, "closed", False)
    return bool(connected) and not closed


def build_session_instructions(
    compiled_brain: str | None,
    *,
    caller_id: str | None = None,
    language: str = "te-IN",
) -> str:
    from server.prompts.agent_voice_rules import live_realtime_output_rules

    parts = [
        (compiled_brain or "").strip()
        or f"You are a helpful live voice agent. {LIVE_REPLY_BREVITY_RULE}"
    ]
    parts.append(live_realtime_output_rules(language))
    if caller_id:
        parts.append("[Caller context]\nInbound caller connected (do not read their number aloud).")
    return "\n\n".join(parts)


class RealtimeTextSession:
    def __init__(
        self,
        call_id: str,
        *,
        adapter: Any,
        model: str,
        instructions: str,
        language: str = "te-IN",
        temperature: float | None = None,
    ) -> None:
        self.call_id = call_id
        self.model = model or DEFAULT_REALTIME_MODEL
        self.language = language
        self._adapter = adapter
        self._instructions = instructions
        self._temperature = temperature
        self._state: SessionState = "idle"
        self._turn_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._ready = False
        self._boot_task: asyncio.Task | None = None
        self._history: list[tuple[str, str]] = []
        self._needs_history_restore = False
        self._collector_idle = asyncio.Event()
        self._collector_idle.set()

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def is_ready(self) -> bool:
        return self._ready and _adapter_is_open(self._adapter) and self._state != "closed"

    async def wait_until_ready(self, timeout: float = 12.0) -> bool:
        if self.is_ready:
            return True
        if self._boot_task is not None and not self._boot_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._boot_task), timeout=timeout)
            except asyncio.TimeoutError:
                return self.is_ready
            except Exception:
                return False
            return self.is_ready
        try:
            await asyncio.wait_for(self.start(), timeout=timeout)
            return self.is_ready
        except Exception:
            return False

    def boot_in_background(self) -> None:
        if self._state == "closed":
            return
        if self._boot_task is None or self._boot_task.done():
            self._boot_task = asyncio.create_task(self.start(), name=f"rt-boot-{self.call_id}")
            self._boot_task.add_done_callback(self._boot_finished)

    def _boot_finished(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception() is not None:
            logger.error("[REALTIME] session boot failed call=%s: %s", self.call_id, task.exception())

    async def start(self) -> None:
        async with self._start_lock:
            if self._state == "closed":
                return
            if self._ready and _adapter_is_open(self._adapter) and not self._needs_history_restore:
                return
            if self._ready and _adapter_is_open(self._adapter) and self._needs_history_restore:
                reconcile = getattr(self._adapter, "reconcile_spoken", None)
                if callable(reconcile):
                    heard = self._history[-1][1] if self._history and self._history[-1][0] == "assistant" else ""
                    try:
                        await reconcile(heard)
                        self._needs_history_restore = False
                        self._state = "idle"
                        logger.info("[REALTIME] reconciled interrupted text in-session call=%s", self.call_id)
                        return
                    except Exception as e:
                        logger.warning(
                            "[REALTIME] in-session reconcile failed call=%s: %s",
                            self.call_id,
                            str(e)[:160],
                        )
            if self._ready:
                logger.warning("[REALTIME] rebuilding session history call=%s", self.call_id)
                try:
                    await self._adapter.close()
                except Exception:
                    pass
                self._ready = False
            await self._adapter.connect(
                model=self.model,
                instructions=self._instructions,
                max_output_tokens=LIVE_MAX_OUTPUT_TOKENS,
                temperature=self._temperature,
            )
            if self._state == "closed":
                await self._adapter.close()
                return
            try:
                await self._adapter.wait_ready()
            except BaseException:
                self._ready = False
                await self._adapter.close()
                raise
            if self._state == "closed":
                await self._adapter.close()
                return
            for role, text in self._history:
                sender = self._adapter.send_user_text if role == "user" else self._adapter.send_assistant_text
                await sender(text)
            self._needs_history_restore = False
            self._ready = True
            self._state = "idle"

    async def note_spoken(self, text: str) -> None:
        """Record an already-played line (PSTN greeting) so the model does not repeat it."""
        spoken = (text or "").strip()
        if not spoken or self._state == "closed":
            return
        if not self._ready or not _adapter_is_open(self._adapter):
            await self.start()
        sender = getattr(self._adapter, "send_assistant_text", None)
        if not callable(sender):
            return
        async with self._turn_lock:
            await sender(spoken)
            self._history.append(("assistant", spoken))

    def reconcile_spoken(self, heard: str) -> None:
        """Replace the current assistant output with playback evidence on reconnect.

        Text-only Realtime cannot use audio truncation. Rebuilding its conversation
        before the next turn also removes unplayed text already buffered remotely.
        """
        if self._history and self._history[-1][0] == "assistant":
            self._history.pop()
        if heard.strip():
            self._history.append(("assistant", heard.strip()))
        self._needs_history_restore = True

    async def run_turn(self, transcript: str, *, language: str | None = None) -> AsyncIterator[dict[str, Any]]:
        lang = language or self.language
        async with self._turn_lock:
            if not self._ready or not _adapter_is_open(self._adapter) or self._needs_history_restore:
                await self.start()
            self._history.append(("user", transcript))
            # Keep the opening plus a bounded recent conversation on reconnect.
            if len(self._history) > 81:
                self._history = self._history[:1] + self._history[-80:]
            for attempt in range(2):
                if self._state == "streaming":
                    await self.cancel_response()
                self._state = "streaming"
                spoken = ""
                stream_cap = LiveReplyStreamCap()
                end_call = {"should_end": False, "reason": "none", "farewell": ""}
                usage: dict[str, Any] = {}
                failed = False
                cancelled = False
                try:
                    if attempt == 0:
                        await self._adapter.send_user_text(transcript)
                    await self._adapter.start_response()
                    async for event in self._collect_until_done():
                        kind = event.get("type")
                        if kind == "text_delta":
                            piece = filter_unrelated_scripts(
                                str(event.get("delta") or ""), lang, streaming=True
                            )
                            if piece:
                                emit = stream_cap.feed(piece)
                                if emit:
                                    spoken += emit
                                    yield {"delta": emit}
                        elif kind == "text_done" and not spoken:
                            spoken = filter_unrelated_scripts(str(event.get("text") or ""), lang)
                        elif kind == "function_call" and event.get("name") == "end_call":
                            parsed = parse_end_call_tool(event.get("arguments"))
                            if parsed is not None:
                                end_call = parsed
                        elif kind == "response_done":
                            usage = event.get("usage") or {}
                            failed = bool(event.get("failed"))
                            for item in event.get("output") or []:
                                if item.get("type") == "function_call" and item.get("name") == "end_call":
                                    parsed = parse_end_call_tool(item.get("arguments"))
                                    if parsed is not None:
                                        end_call = parsed
                                elif not spoken and item.get("type") == "message":
                                    spoken = filter_unrelated_scripts("".join(
                                        str(part.get("text") or "") for part in item.get("content") or []
                                        if part.get("type") in {"text", "output_text"}
                                    ), lang)
                            assert_zero_audio_tokens(usage, call_id=self.call_id)
                        elif kind == "cancelled":
                            cancelled = True
                            if event.get("usage"):
                                usage = event.get("usage") or usage
                            break
                        elif kind == "error":
                            failed = True
                            logger.warning(
                                "[REALTIME] turn error call=%s %s",
                                self.call_id,
                                event.get("message"),
                            )
                except Exception as e:
                    failed = True
                    logger.warning("[REALTIME] turn failed call=%s %s", self.call_id, str(e)[:200])
                finally:
                    if self._state != "closed":
                        self._state = "idle"

                if caller_requested_hangup(transcript) and (failed or not end_call.get("should_end")):
                    from server.prompts.agent_voice_rules import CALL_END_FAREWELLS, normalize_compile_language

                    default_farewell = CALL_END_FAREWELLS[normalize_compile_language(lang)]
                    end_call = {
                        "should_end": True,
                        "reason": "goodbye",
                        "farewell": str(end_call.get("farewell") or spoken or default_farewell),
                    }
                elif caller_firm_refusal(transcript) and (failed or not end_call.get("should_end")):
                    from server.prompts.agent_voice_rules import CALL_END_FAREWELLS, normalize_compile_language

                    default_farewell = CALL_END_FAREWELLS[normalize_compile_language(lang)]
                    end_call = {
                        "should_end": True,
                        "reason": "firm_refusal",
                        "farewell": str(end_call.get("farewell") or spoken or default_farewell),
                    }
                elif caller_requested_callback(transcript) and not end_call.get("should_end"):
                    from server.call.hangup_judge import default_farewell_for

                    end_call = {
                        "should_end": True, "reason": "goal_complete",
                        "farewell": spoken or default_farewell_for(lang),
                    }
                elif (
                    not end_call.get("should_end")
                    and spoken
                    and agent_spoke_closing(spoken)
                ):
                    # Model spoke a closing handoff/farewell but forgot the tool — propose hangup;
                    # the server gate still requires evidence (lead memory / ack / goal phrase).
                    end_call = {
                        "should_end": True,
                        "reason": "goal_complete",
                        "farewell": str(end_call.get("farewell") or spoken),
                    }
                if end_call.get("should_end") and not spoken:
                    spoken = str(end_call.get("farewell") or "")
                spoken = stream_cap.finalize(spoken)
                # Barge crumbs ("We.") finalize to empty — treat as cancelled, do not archive.
                if cancelled:
                    yield {
                        "done": True,
                        "text": spoken if spoken.strip() else "",
                        "failed": False,
                        "cancelled": True,
                        "end_call": end_call,
                        "usage": usage,
                        "memory_update": {"operations": []},
                        "memory_parse_failed": False,
                    }
                    return
                if spoken.strip():
                    if not self._needs_history_restore:
                        self._history.append(("assistant", spoken))
                    yield {
                        "done": True,
                        "text": spoken,
                        "failed": failed,
                        "cancelled": False,
                        "end_call": end_call,
                        "usage": usage,
                        "memory_update": {"operations": []},
                        "memory_parse_failed": False,
                    }
                    return
                if attempt == 0:
                    logger.warning("[REALTIME] empty reply call=%s — retrying once", self.call_id)
                    continue
                from server.prompts.agent_voice_rules import UNCLEAR_FALLBACK, normalize_compile_language

                fallback = UNCLEAR_FALLBACK[normalize_compile_language(lang)]
                yield {
                    "done": True,
                    "text": fallback,
                    "failed": failed,
                    "cancelled": False,
                    "end_call": end_call,
                    "usage": usage,
                    "memory_update": {"operations": []},
                    "memory_parse_failed": False,
                }
                return

    async def cancel_response(self) -> None:
        if self._state not in ("streaming", "cancelling"):
            return
        self._state = "cancelling"
        try:
            await self._adapter.cancel_response()
            # Exactly one consumer may read adapter events. The active turn
            # consumes its cancellation acknowledgement; only drain if idle.
            waiter = self._drain_until_idle() if self._collector_idle.is_set() else self._collector_idle.wait()
            await asyncio.wait_for(waiter, timeout=CANCEL_DRAIN_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            logger.warning("[REALTIME] cancel drain timed out call=%s", self.call_id)
        except Exception as e:
            logger.warning("[REALTIME] cancel failed call=%s %s", self.call_id, str(e)[:160])
        finally:
            discard = getattr(self._adapter, "discard_queued", None)
            if callable(discard):
                discard()
            if self._state != "closed":
                self._state = "idle"

    async def close(self) -> None:
        was_streaming = self._state == "streaming"
        self._state = "closed"
        if self._boot_task and not self._boot_task.done():
            self._boot_task.cancel()
            try:
                await self._boot_task
            except (asyncio.CancelledError, Exception):
                pass
        if was_streaming:
            try:
                await self._adapter.cancel_response()
            except Exception:
                pass
        try:
            await self._adapter.close()
        except Exception as e:
            logger.warning("[REALTIME] close failed call=%s %s", self.call_id, str(e)[:160])

    async def _drain_until_idle(self) -> None:
        async for event in self._adapter.events():
            if event.get("type") in ("response_done", "cancelled", "error"):
                return

    async def _collect_until_done(self) -> AsyncIterator[dict[str, Any]]:
        import time as _time

        deadline = _time.monotonic() + REALTIME_TURN_TIMEOUT_SEC
        self._collector_idle.clear()
        try:
            agen = self._adapter.events().__aiter__()
            while True:
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                try:
                    event = await asyncio.wait_for(agen.__anext__(), timeout=remaining)
                except StopAsyncIteration:
                    return
                yield event
                if event.get("type") in ("response_done", "cancelled", "error"):
                    return
        except asyncio.TimeoutError:
            logger.warning(
                "[REALTIME] turn timed out after %.1fs call=%s",
                REALTIME_TURN_TIMEOUT_SEC,
                self.call_id,
            )
            try:
                await self.cancel_response()
            except Exception:
                pass
            yield {"type": "error", "message": "realtime_turn_timeout"}
        except asyncio.CancelledError:
            yield {"type": "cancelled"}
        finally:
            self._collector_idle.set()
