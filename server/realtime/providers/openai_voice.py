"""OpenAI Realtime GA adapter — PCM16 audio in, audio out (speech-to-speech)."""
from __future__ import annotations

import asyncio
import base64
import copy
import json
import uuid
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from server.call.call_controller import CALL_ACTION_TOOL
from server.realtime.models import (
    DEFAULT_REALTIME_MODEL,
    DEFAULT_REALTIME_TURN_DETECTION,
    DEFAULT_REALTIME_VOICE,
    END_CALL_TOOL,
    REALTIME_PCM_RATE,
    normalize_realtime_noise_reduction,
    normalize_realtime_silence_ms,
    normalize_realtime_speed,
    normalize_realtime_turn_detection,
    normalize_realtime_vad_eagerness,
    normalize_realtime_voice,
    resolve_realtime_voice_max_output_tokens,
)
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


def build_realtime_voice_session(
    *,
    model: str,
    instructions: str,
    voice: str | None = None,
    turn_detection: str | None = None,
    vad_eagerness: str | None = None,
    noise_reduction: str | None = None,
    speed: float | None = None,
    silence_ms: int | None = None,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """GA session.update payload — PCM16 @ 24 kHz audio in, audio out (OpenAI Realtime)."""
    vad = normalize_realtime_turn_detection(turn_detection)
    if vad == "server_vad":
        detection: dict[str, Any] = {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": normalize_realtime_silence_ms(silence_ms),
            "create_response": True,
            # Local AEC decides barge; auto-interrupt treats handset echo as the caller.
            "interrupt_response": False,
        }
    else:
        detection = {
            "type": "semantic_vad",
            "eagerness": normalize_realtime_vad_eagerness(vad_eagerness),
            "create_response": True,
            "interrupt_response": False,
        }
    audio_in: dict[str, Any] = {
        "format": {"type": "audio/pcm", "rate": REALTIME_PCM_RATE},
        "turn_detection": detection,
        "transcription": {"model": "gpt-4o-mini-transcribe"},
    }
    noise = normalize_realtime_noise_reduction(noise_reduction)
    if noise != "off":
        audio_in["noise_reduction"] = {"type": noise}
    else:
        # An omitted field preserves an existing session setting on update.
        audio_in["noise_reduction"] = None
    return {
        "type": "realtime",
        "model": model or DEFAULT_REALTIME_MODEL,
        "instructions": instructions,
        "output_modalities": ["audio"],
        "max_output_tokens": resolve_realtime_voice_max_output_tokens(max_output_tokens),
        "tools": [END_CALL_TOOL, {
            **CALL_ACTION_TOOL,
            "description": (
                "Report conversational intent in the same turn as your speech. "
                "Answer ordinary questions directly without calling a tool first. "
                "For a clear refusal or a confirmed end (bye, hang up, that's all, don't call), "
                "speak a short farewell, then report END_CALL. "
                "Use CALLBACK only for an explicitly requested callback; a withdrawal overrides earlier consent. "
                "Do not end for a bare okay/thanks, a pause, a follow-up question, or unspoken enough-is-known. "
                "Busy: one callback offer and stay on the line. Hangup is owned by end_call. "
                "Wait for the tool result before claiming a transfer or callback has been arranged."
            ),
        }],
        "tool_choice": "auto",
        "audio": {
            "input": audio_in,
            "output": {
                "format": {"type": "audio/pcm", "rate": REALTIME_PCM_RATE},
                "voice": normalize_realtime_voice(voice),
                "speed": normalize_realtime_speed(speed),
            },
        },
    }


class OpenAIRealtimeVoiceAdapter:
    """Persistent OpenAI Realtime WebSocket for Telnyx speech-to-speech."""

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
        self._response_idle = asyncio.Event()
        self._response_idle.set()
        self._response_lock = asyncio.Lock()
        self._cancelled_response_ids: deque[str] = deque(maxlen=128)
        self._cancelled_request_tokens: deque[str] = deque(maxlen=128)
        self._pending_response_token: str | None = None
        self._accepting = False
        self._current_output_item_ids: list[str] = []
        self.model = DEFAULT_REALTIME_MODEL
        self.voice = DEFAULT_REALTIME_VOICE
        self.turn_detection = DEFAULT_REALTIME_TURN_DETECTION
        self.last_session: dict[str, Any] | None = None

    async def connect(
        self,
        *,
        model: str,
        instructions: str,
        voice: str | None = None,
        turn_detection: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
        vad_eagerness: str | None = None,
        noise_reduction: str | None = None,
        speed: float | None = None,
        silence_ms: int | None = None,
    ) -> None:
        from openai import AsyncOpenAI

        from server.config.env import get_settings

        _ = temperature
        settings = get_settings()
        self.model = model or DEFAULT_REALTIME_MODEL
        self.voice = normalize_realtime_voice(voice)
        self.turn_detection = normalize_realtime_turn_detection(turn_detection)
        self._closed = False
        self._accepting = False
        self._active_response_id = None
        self._cancelled_response_ids.clear()
        self._cancelled_request_tokens.clear()
        self._pending_response_token = None
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
        self._pump_task = asyncio.create_task(self._pump(), name="openai-realtime-voice-recv")
        session = build_realtime_voice_session(
            model=self.model,
            instructions=instructions,
            voice=self.voice,
            turn_detection=self.turn_detection,
            vad_eagerness=vad_eagerness,
            noise_reduction=noise_reduction,
            speed=speed,
            silence_ms=silence_ms,
            max_output_tokens=max_output_tokens,
        )
        self.last_session = session
        await self._conn.send({"type": "session.update", "session": session})

    async def update_instructions(self, instructions: str) -> None:
        if self._conn is None or self._closed:
            return
        # Preserve VAD eagerness, silence duration, noise reduction, speed,
        # token cap, and the deferred-greeting auto-response state.
        session = copy.deepcopy(self.last_session) if self.last_session else {}
        if not session:
            session = build_realtime_voice_session(
                model=self.model,
                instructions=instructions,
                voice=self.voice,
                turn_detection=self.turn_detection,
            )
        else:
            session["instructions"] = instructions
        self.last_session = session
        await self._conn.send({"type": "session.update", "session": session})

    async def set_auto_response(self, enabled: bool) -> None:
        """Keep VAD events on while toggling automatic response creation."""
        if self._conn is None or self._closed or not self.last_session:
            return
        session = copy.deepcopy(self.last_session)
        try:
            detection = session["audio"]["input"]["turn_detection"]
            detection["create_response"] = bool(enabled)
        except (KeyError, TypeError):
            return
        self.last_session = session
        await self._conn.send({"type": "session.update", "session": session})

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
            raise ConnectionError("Realtime voice disconnected before session.updated")

    async def append_pcm16(self, pcm16: bytes) -> None:
        if self._conn is None or not pcm16:
            return
        await self._conn.send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm16).decode("ascii"),
            }
        )

    async def start_response(self, *, instructions: str | None = None) -> None:
        if self._conn is None:
            raise RuntimeError("realtime voice connection is not open")
        async with self._response_lock:
            automatic = bool(self.last_session and self.last_session["audio"]["input"]["turn_detection"].get("create_response"))
            try:
                if automatic:
                    await self.set_auto_response(False)
                # Commands share an ordered WebSocket. A VAD response may have
                # started remotely before disable, without response.created
                # reaching us yet, so cancel the default conversation as well.
                await self._cancel_response_locked(force=automatic)
                self._accepting = False
                self._active_response_id = None
                self._current_output_item_ids = []
                self._response_idle.clear()
                self._pending_response_token = uuid.uuid4().hex
                payload: dict[str, Any] = {
                    "type": "response.create",
                    "response": {
                        "output_modalities": ["audio"],
                        "metadata": {"pstn_request": self._pending_response_token},
                    },
                }
                if instructions:
                    payload["response"]["instructions"] = instructions
                await self._conn.send(payload)
            except Exception:
                self._accepting = False
                self._pending_response_token = None
                self._response_idle.set()
                raise
            finally:
                if automatic:
                    await self.set_auto_response(True)

    async def cancel_response(self, *, response_id: str | None = None) -> None:
        """Send cancellation without waiting for response.done on the audio path."""
        async with self._response_lock:
            await self._cancel_response_locked(response_id=response_id)

    async def clear_output_audio(self) -> None:
        """Compatibility no-op: this Realtime endpoint rejects output_audio_buffer.clear."""
        return

    async def clear_input_audio(self) -> None:
        """Drop inbound PCM already sitting in OpenAI's buffer (handset echo)."""
        if self._conn is None:
            return
        try:
            await self._conn.send({"type": "input_audio_buffer.clear"})
        except Exception as e:
            logger.warning("[REALTIME_VOICE] input_audio_buffer.clear failed: %s", str(e)[:160])

    async def _cancel_response_locked(
        self, *, response_id: str | None = None, force: bool = False,
    ) -> None:
        had_active = not self._response_idle.is_set()
        if self._pending_response_token and not response_id:
            self._cancelled_request_tokens.append(self._pending_response_token)
            self._pending_response_token = None
        rid = response_id or self._active_response_id
        if rid and rid in self._cancelled_response_ids and not force:
            return
        if not response_id or rid == self._active_response_id:
            self._accepting = False
        if self._conn is None:
            self._active_response_id = None
            self._response_idle.set()
            return
        if not had_active and not response_id and not force:
            return
        payload: dict[str, Any] = {"type": "response.cancel"}
        if rid:
            if not force:
                payload["response_id"] = rid
            if rid not in self._cancelled_response_ids:
                self._cancelled_response_ids.append(rid)
        try:
            await self._conn.send(payload)
        except Exception as e:
            if rid and rid in self._cancelled_response_ids:
                self._cancelled_response_ids.remove(rid)
            logger.warning("[REALTIME_VOICE] cancel failed: %s", str(e)[:160])
            raise

    async def submit_function_output(self, *, call_id: str, output: str) -> None:
        if self._conn is None or not call_id:
            return
        await self._conn.send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                },
            }
        )

    async def note_assistant_text(self, text: str) -> None:
        """Sync spoken assistant text into conversation history (prevents re-greeting)."""
        spoken = (text or "").strip()
        if not spoken or self._conn is None:
            return
        await self._conn.send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": spoken}],
                },
            }
        )

    async def delete_synthetic_response_items(self) -> None:
        """Remove assistant items from a synthetic prewarm response (keep history listen-first)."""
        if self._conn is None:
            self._current_output_item_ids = []
            return
        async with self._response_lock:
            for item_id in list(dict.fromkeys(self._current_output_item_ids)):
                try:
                    await self._conn.send({"type": "conversation.item.delete", "item_id": item_id})
                except Exception as e:
                    logger.warning("[REALTIME_VOICE] item delete failed: %s", str(e)[:160])
            self._current_output_item_ids = []

    async def poll_event(self, timeout: float = 0.5) -> dict[str, Any] | None:
        """Read one normalized event (prewarm greeting capture). None = timeout."""
        try:
            async with asyncio.timeout(timeout):
                while True:
                    item = await self._events.get()
                    if item is None:
                        self._events.put_nowait(None)
                        return {"type": "_stream_end"}
                    if item.get("response_id") not in self._cancelled_response_ids:
                        return item
        except asyncio.TimeoutError:
            return None

    def discard_queued(self) -> None:
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
            logger.info("[REALTIME_VOICE] discarded %s stale queued events", dumped)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._events.get()
            if item is None:
                break
            if item.get("response_id") in self._cancelled_response_ids:
                # Cancellation may happen after normalization but before the
                # PSTN event consumer catches up with the receive queue.
                continue
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
                        if _event_field(err, "code") == "response_cancel_not_active":
                            # Targeted cancel can race response.done; the session
                            # and any newer response remain valid.
                            continue
                        message = (
                            err
                            if isinstance(err, str)
                            else str(_event_field(err, "message") or err or kind)
                        )
                        logger.warning("[REALTIME_VOICE] session event error: %s", message[:240])
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
            logger.warning("[REALTIME_VOICE] recv loop ended: %s", str(e)[:200])
            await self._events.put({"type": "error", "message": str(e)[:240]})
        finally:
            self._ready.set()
            await self._events.put(None)

    def _normalize(self, event: Any) -> dict[str, Any] | None:
        kind = _event_type(event)
        rid = _response_id(event)
        if rid and rid in self._cancelled_response_ids:
            if kind not in ("response.done", "response.cancelled"):
                return None
            # A cancelled response may finish after a replacement was requested,
            # even before its response.created arrives. Never mark that idle.
            if rid != self._active_response_id:
                if self._active_response_id is None and self._pending_response_token is None:
                    self._response_idle.set()
                return None
        if kind == "response.created":
            rid = _response_id(event)
            response = _event_field(event, "response") or {}
            metadata = _event_field(response, "metadata") or {}
            token = _event_field(metadata, "pstn_request")
            if token and token in self._cancelled_request_tokens:
                if rid:
                    self._cancelled_response_ids.append(rid)
                return None
            if self._pending_response_token:
                if token != self._pending_response_token:
                    if rid:
                        self._cancelled_response_ids.append(rid)
                    return None
                self._pending_response_token = None
            if rid:
                self._active_response_id = rid
            self._accepting = True
            self._current_output_item_ids = []
            if self._response_idle.is_set():
                self._response_idle.clear()
            return {"type": "response_created", "response_id": rid}
        if kind == "response.output_item.added":
            item = _event_field(event, "item") or {}
            item_id = str(_event_field(item, "id") or "")
            if item_id and item_id not in self._current_output_item_ids:
                self._current_output_item_ids.append(item_id)
            return None
        if kind in (
            "input_audio_buffer.speech_started",
            "input_audio.speech_started",
        ):
            # Informational only — the PSTN loop decides whether echo should barge.
            # Clearing _accepting here truncated the rest of a legitimate reply.
            return {"type": "speech_started"}
        if kind in (
            "input_audio_buffer.speech_stopped",
            "input_audio.speech_stopped",
        ):
            return {"type": "speech_stopped"}
        if kind in (
            "conversation.item.input_audio_transcription.completed",
            "conversation.item.input_audio_transcription.delta",
        ):
            transcript = str(
                _event_field(event, "transcript")
                or _event_field(event, "delta")
                or ""
            )
            if not transcript.strip():
                return None
            return {
                "type": "user_transcript",
                "text": transcript,
                "final": kind.endswith("completed"),
            }
        if kind in (
            "response.output_audio.delta",
            "response.audio.delta",
            "response.output_audio.delta.delta",
        ):
            if not self._accepting:
                return None
            rid = _response_id(event)
            if rid and self._active_response_id and rid != self._active_response_id:
                return None
            delta = _event_field(event, "delta") or _event_field(event, "audio") or ""
            if not delta:
                return None
            try:
                pcm = base64.b64decode(delta) if isinstance(delta, str) else bytes(delta)
            except Exception:
                return None
            return {"type": "audio_delta", "pcm": pcm, "response_id": rid}
        if kind in (
            "response.output_audio_transcript.delta",
            "response.audio_transcript.delta",
            "response.output_audio_transcript.delta.delta",
        ):
            return {
                "type": "assistant_transcript_delta",
                "delta": str(_event_field(event, "delta") or ""),
                "response_id": _response_id(event),
            }
        if kind in (
            "response.output_audio_transcript.done",
            "response.audio_transcript.done",
        ):
            return {
                "type": "assistant_transcript",
                "text": str(_event_field(event, "transcript") or _event_field(event, "text") or ""),
                "response_id": _response_id(event),
            }
        if kind == "response.function_call_arguments.done":
            return {
                "type": "function_call",
                "name": str(_event_field(event, "name") or ""),
                "arguments": _event_field(event, "arguments") or "",
                "call_id": str(_event_field(event, "call_id") or ""),
                "response_id": _response_id(event),
            }
        if kind == "response.done":
            response = _event_field(event, "response")
            rid = _response_id(event)
            if rid and self._active_response_id and rid != self._active_response_id:
                return None
            self._accepting = False
            self._active_response_id = None
            self._response_idle.set()
            status = str(_event_field(response, "status") or "")
            usage = extract_realtime_usage(response)
            output = []
            for item in _event_field(response, "output") or []:
                output.append(
                    {
                        "type": _event_field(item, "type"),
                        "name": _event_field(item, "name"),
                        "arguments": _event_field(item, "arguments"),
                        "call_id": _event_field(item, "call_id"),
                    }
                )
            return {
                "type": "cancelled" if status == "cancelled" else "response_done",
                "status": status,
                "usage": usage,
                "failed": status == "failed",
                "output": output,
                "response_id": rid,
            }
        if kind == "response.cancelled":
            rid = _response_id(event)
            if rid and self._active_response_id and rid != self._active_response_id:
                return None
            self._accepting = False
            self._active_response_id = None
            self._response_idle.set()
            return {"type": "cancelled", "response_id": rid}
        if kind in ("error", "response.failed"):
            err = _event_field(event, "error") or {}
            message = err if isinstance(err, str) else str(_event_field(err, "message") or err or kind)
            self._accepting = False
            self._active_response_id = None
            self._response_idle.set()
            return {"type": "error", "message": message[:240]}
        return None

    @staticmethod
    def debug_event(event: Any) -> str:
        try:
            if hasattr(event, "model_dump_json"):
                return event.model_dump_json()[:400]
            return json.dumps(event, default=str)[:400]
        except Exception:
            return str(event)[:400]
