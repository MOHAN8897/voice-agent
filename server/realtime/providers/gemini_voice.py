"""Gemini Live API adapter — PCM audio in/out (speech-to-speech), PSTN parity with OpenAI Realtime."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

from server.call.call_controller import CALL_ACTION_TOOL
from server.providers.gemini_llm import _api_key, gemini_usage_from_metadata
from server.realtime.hangup_tools import REQUEST_LANGUAGE_CALLBACK_TOOL, realtime_hangup_tool_declarations
logger = logging.getLogger(__name__)

from server.realtime.models import (
    DEFAULT_REALTIME_TURN_DETECTION,
    REALTIME_PCM_RATE,
    normalize_realtime_silence_ms,
    normalize_realtime_turn_detection,
    normalize_realtime_vad_eagerness,
    normalize_realtime_voice,
    resolve_realtime_voice_max_output_tokens,
)
from server.services.audio_transcode import StreamingPcmResampler
from server.utils.logger import logger

GEMINI_LIVE_INPUT_RATE = 16000
GEMINI_LIVE_OUTPUT_RATE = 24000

# OpenAI Realtime voice slugs → Gemini prebuilt speech voices (Live API).
_OPENAI_TO_GEMINI_VOICE: dict[str, str] = {
    "ash": "Aoede",
    "marin": "Puck",
    "cedar": "Charon",
    "alloy": "Kore",
    "echo": "Fenrir",
    "shimmer": "Leda",
    "sage": "Orus",
    "ballad": "Zephyr",
    "coral": "Aoede",
    "verse": "Puck",
}

_EAGERNESS_TO_START: dict[str, str] = {
    "low": "START_SENSITIVITY_LOW",
    "medium": "START_SENSITIVITY_MEDIUM",
    "high": "START_SENSITIVITY_HIGH",
    "auto": "START_SENSITIVITY_HIGH",
}


def normalize_gemini_live_voice(voice: str | None) -> str:
    slug = str(voice or "").strip()
    if slug in _OPENAI_TO_GEMINI_VOICE.values():
        return slug
    mapped = _OPENAI_TO_GEMINI_VOICE.get(normalize_realtime_voice(voice), "Puck")
    return mapped


def _gemini_tools() -> list[types.Tool]:
    decls: list[types.FunctionDeclaration] = []
    for tool in (*realtime_hangup_tool_declarations(), REQUEST_LANGUAGE_CALLBACK_TOOL, CALL_ACTION_TOOL):
        decls.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description"),
                parameters_json_schema=tool.get("parameters"),
            )
        )
    return [types.Tool(function_declarations=decls)]


def _vad_config(
    *,
    turn_detection: str,
    vad_eagerness: str | None,
    silence_ms: int | None,
) -> types.RealtimeInputConfig:
    td = normalize_realtime_turn_detection(turn_detection)
    if td == "server_vad":
        return types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                silence_duration_ms=normalize_realtime_silence_ms(silence_ms),
            )
        )
    start = _EAGERNESS_TO_START.get(normalize_realtime_vad_eagerness(vad_eagerness), "START_SENSITIVITY_HIGH")
    silence_ms = normalize_realtime_silence_ms(silence_ms) if silence_ms else 650
    return types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(
            disabled=False,
            start_of_speech_sensitivity=start,
            silence_duration_ms=silence_ms,
        )
    )


OPENING_ALREADY_DELIVERED_NOTE = (
    "Silent control note. Do not read this aloud. "
    "The opening greeting was already spoken to the caller. "
    "Ignore any earlier request to speak that opening line. "
    "Wait for the caller, then answer their actual words "
    "(who is calling, company, purpose). Never repeat the opening. "
    "Do not hang up unless they clearly end the conversation."
)


def _usage_from_message(message: types.LiveServerMessage) -> dict[str, Any]:
    meta = message.usage_metadata
    if meta is None:
        return {}
    dump = meta.model_dump() if meta else {}
    usage = gemini_usage_from_metadata(dump, native_audio=True)
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cached = int(usage.get("cached_tokens") or 0)
    audio_in = int(usage.get("input_audio_tokens") or 0)
    audio_out = int(usage.get("output_audio_tokens") or 0)
    image_in = int(usage.get("input_image_tokens") or 0)
    audio_cached = int(usage.get("cached_audio_tokens") or 0)
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cached_tokens": cached,
        "cache_write_tokens": 0,
        "input_audio_tokens": audio_in,
        "output_audio_tokens": audio_out,
        "input_image_tokens": image_in,
        "cached_audio_tokens": min(audio_in, audio_cached),
    }


class GeminiLiveVoiceAdapter:
    """Persistent Gemini Live session for Telnyx speech-to-speech."""

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._client: genai.Client | None = None
        self._session: Any = None
        self._connect_cm: Any = None
        self._ready = asyncio.Event()
        self._configuration_error: str | None = None
        self._configured = False
        self._events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._pump_task: asyncio.Task | None = None
        self._closed = False
        self._accepting = False
        self._auto_response = True
        self._active_response_id: str | None = None
        self._response_idle = asyncio.Event()
        self._response_idle.set()
        self._response_lock = asyncio.Lock()
        self._cancelled_response_ids: deque[str] = deque(maxlen=128)
        self._completed_response_ids: deque[str] = deque(maxlen=64)
        self._in_resampler = StreamingPcmResampler(REALTIME_PCM_RATE, GEMINI_LIVE_INPUT_RATE)
        self._sent_realtime_audio = False
        self._max_output_tokens: int | None = None
        self.model = "gemini-3.8-live"
        self.voice = "Puck"
        self.turn_detection = DEFAULT_REALTIME_TURN_DETECTION
        self.instructions = ""
        self.last_session: dict[str, Any] | None = None
        self.needs_explicit_opening = True
        self.supports_external_opening_note = True
        self.opening_history_clean = True
        self._pump_restarts = 0
        self._drop_until_turn_complete = False
        self._input_transcript = ""
        self._input_transcript_final = False

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
        include_tools: bool = True,
    ) -> None:
        _ = temperature, noise_reduction, speed
        key = (self._api_key or _api_key()).strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self.model = (model or "gemini-3.8-live").strip()
        self.voice = normalize_gemini_live_voice(voice)
        self.turn_detection = normalize_realtime_turn_detection(turn_detection)
        self.instructions = instructions
        self._max_output_tokens = max_output_tokens
        self._closed = False
        self._accepting = False
        self._auto_response = True
        self._sent_realtime_audio = False
        self.opening_history_clean = True
        self._pump_restarts = 0
        self._completed_response_ids.clear()
        self._cancelled_response_ids.clear()
        self._active_response_id = None
        self._response_idle.set()
        self._drop_until_turn_complete = False
        self._input_transcript = ""
        self._input_transcript_final = False
        self._ready = asyncio.Event()
        self._configuration_error = None
        self._configured = False
        self._events = asyncio.Queue()
        self._in_resampler = StreamingPcmResampler(REALTIME_PCM_RATE, GEMINI_LIVE_INPUT_RATE)
        self._client = genai.Client(api_key=key)
        speech = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
            )
        )
        connect_kwargs: dict[str, Any] = {
            "response_modalities": ["AUDIO"],
            "max_output_tokens": resolve_realtime_voice_max_output_tokens(max_output_tokens),
            "speech_config": speech,
            "system_instruction": types.Content(parts=[types.Part(text=instructions)]),
            "realtime_input_config": _vad_config(
                turn_detection=self.turn_detection,
                vad_eagerness=vad_eagerness,
                silence_ms=silence_ms,
            ),
            # Bound repeated audio/text history costs while retaining recent call context.
            "context_window_compression": types.ContextWindowCompressionConfig(
                trigger_tokens=16000,
                sliding_window=types.SlidingWindow(target_tokens=8000),
            ),
        }
        if include_tools:
            connect_kwargs["tools"] = _gemini_tools()
        config = types.LiveConnectConfig(**connect_kwargs)
        aad = getattr(connect_kwargs.get("realtime_input_config"), "automatic_activity_detection", None)
        self.last_session = {
            "model": self.model,
            "instructions": instructions,
            "voice": self.voice,
            "turn_detection": self.turn_detection,
            "effective_vad": {
                "mode": self.turn_detection,
                "silence_duration_ms": getattr(aad, "silence_duration_ms", None),
                "start_of_speech_sensitivity": getattr(aad, "start_of_speech_sensitivity", None),
                "ignored_ui": {"noise_reduction": noise_reduction, "speed": speed},
            },
        }
        logger.info("[gemini_voice] connect effective_vad=%s", self.last_session["effective_vad"])
        self._connect_cm = self._client.aio.live.connect(model=self.model, config=config)
        self._session = await self._connect_cm.__aenter__()
        self._pump_task = asyncio.create_task(self._pump(), name="gemini-live-voice-recv")

    def _ensure_response_id(self) -> str:
        if not self._active_response_id:
            self._active_response_id = uuid.uuid4().hex
        return self._active_response_id

    def _emit_response_done(
        self, message: types.LiveServerMessage, response_id: str
    ) -> dict[str, Any] | None:
        rid = (response_id or "").strip()
        replay = bool(rid and rid in self._completed_response_ids)
        if not rid and self._completed_response_ids:
            rid = self._completed_response_ids[-1]
            replay = True
        if not rid:
            rid = self._ensure_response_id()
        if not replay:
            self._completed_response_ids.append(rid)
            self._accepting = False
            if self._active_response_id == rid or not self._active_response_id:
                self._active_response_id = None
            self._response_idle.set()
        payload: dict[str, Any] = {
            "type": "response_done",
            "status": "completed",
            "usage": {**_usage_from_message(message), "usage_scope": "response", "usage_id": rid} if message.usage_metadata else {},
            "failed": False,
            "output": [],
            "response_id": rid,
        }
        if replay:
            payload["usage_only"] = True
        return payload

    async def update_instructions(self, instructions: str) -> None:
        new = (instructions or "").strip()
        if not new:
            return
        previous = (self.instructions or "").strip()
        self.instructions = new
        if self.last_session:
            self.last_session["instructions"] = new
        if self._session is None:
            return
        # Live cannot replace system_instruction after connect. Replaying the
        # full script as a user turn double-bills input and can trigger hangup
        # tools. Only nudge when the published brain actually changed.
        if new == previous:
            return
        try:
            await self._session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=OPENING_ALREADY_DELIVERED_NOTE)],
                ),
                turn_complete=False,
            )
        except Exception as exc:
            logger.warning("[GEMINI_LIVE] instruction update failed: %s", str(exc)[:160])

    async def set_auto_response(self, enabled: bool) -> None:
        self._auto_response = bool(enabled)
        if enabled:
            return
        # Drop in-flight model audio so deferred PSTN greeting is not overwritten.
        rid = self._active_response_id
        if rid:
            self._cancelled_response_ids.append(rid)
        self._accepting = False
        self._active_response_id = None
        self._response_idle.set()
        self.discard_queued()
        await self._activity_end_if_audio()

    def is_open(self) -> bool:
        return (
            not self._closed
            and self._session is not None
            and self._pump_task is not None
            and not self._pump_task.done()
        )

    async def wait_ready(self, timeout: float = 12.0) -> None:
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Gemini Live did not become ready within {timeout}s (model={self.model})"
            ) from None
        if self._configuration_error:
            raise RuntimeError(self._configuration_error)
        if not self._configured or not self.is_open():
            raise ConnectionError("Gemini Live disconnected before session was ready")

    async def append_pcm16(self, pcm16: bytes) -> None:
        if self._session is None or not pcm16:
            return
        pcm_in = self._in_resampler.feed(pcm16)
        if not pcm_in:
            return
        self._sent_realtime_audio = True
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm_in, mime_type=f"audio/pcm;rate={GEMINI_LIVE_INPUT_RATE}")
        )

    async def start_response(self, *, instructions: str | None = None) -> None:
        if self._session is None:
            raise RuntimeError("gemini live connection is not open")
        async with self._response_lock:
            self._active_response_id = uuid.uuid4().hex
            self._accepting = True
            self._response_idle.clear()
            self._drop_until_turn_complete = False
            await self._events.put({"type": "response_created", "response_id": self._active_response_id})
            text = (instructions or "").strip()
            if not text:
                text = "Respond in the agent language with a short spoken reply."
            self.opening_history_clean = False
            await self._session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=text)]),
                turn_complete=True,
            )

    async def cancel_response(self, *, response_id: str | None = None) -> None:
        async with self._response_lock:
            if response_id and self._active_response_id and response_id != self._active_response_id:
                self._cancelled_response_ids.append(response_id)
                return
            rid = response_id or self._active_response_id
            if rid:
                self._cancelled_response_ids.append(rid)
                self._drop_until_turn_complete = True
            self._accepting = False
            self._response_idle.set()
            await self._activity_end_if_audio()

    async def _activity_end_if_audio(self) -> None:
        """Close a previously sent audio segment using the automatic-VAD protocol."""
        if self._session is None or not self._sent_realtime_audio:
            return
        self._sent_realtime_audio = False
        try:
            # This adapter always enables server VAD. activity_end is only
            # valid with manual VAD and can make the provider close the socket.
            await self._session.send_realtime_input(audio_stream_end=True)
        except Exception as exc:
            logger.warning("[GEMINI_LIVE] activity_end failed: %s", str(exc)[:160])

    async def clear_output_audio(self) -> None:
        return

    async def clear_input_audio(self) -> None:
        return

    async def submit_function_output(
        self, *, call_id: str, output: str, name: str | None = None
    ) -> None:
        if self._session is None or not call_id:
            return
        tool_name = str(name or "call_action").strip() or "call_action"
        await self._session.send_tool_response(
            function_responses=types.FunctionResponse(
                id=call_id,
                name=tool_name,
                response={"output": output},
            )
        )

    async def note_assistant_text(self, text: str) -> None:
        spoken = (text or "").strip()
        if not spoken or self._session is None:
            return
        await self._session.send_client_content(
            turns=types.Content(role="model", parts=[types.Part(text=spoken)]),
            turn_complete=False,
        )

    async def note_opening_delivered(self, *, spoken_line: str | None = None) -> None:
        """Tell the live session the opening was played (PCM prewarm or OpenAI-style cleanup)."""
        if self._session is None:
            return
        line = (spoken_line or "").strip()
        if self.opening_history_clean and not line:
            return
        if line:
            note = (
                "Silent control note. Do not read aloud. "
                f"The opening greeting was already spoken to the caller exactly as: «{line}». "
                "Do not repeat that opening verbatim. If they ask who is calling, answer with "
                "agent name, company, and purpose from AGENT IDENTITY in one short beat. "
                "Then continue CONVERSATION FLOW from the next step they have not answered. "
                "Follow OUTPUT LANGUAGE RULES in your instructions."
            )
        else:
            note = OPENING_ALREADY_DELIVERED_NOTE
        try:
            await self._session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=note)]),
                turn_complete=False,
            )
        except Exception as exc:
            logger.warning("[GEMINI_LIVE] opening-delivered note failed: %s", str(exc)[:160])

    async def delete_synthetic_response_items(self) -> None:
        """Clear prewarm 'speak this line' history so the live call does not re-greet."""
        self.discard_queued()
        if self.opening_history_clean:
            return
        await self.note_opening_delivered()
        self.discard_queued()

    async def poll_event(self, timeout: float = 0.5) -> dict[str, Any] | None:
        try:
            async with asyncio.timeout(timeout):
                while True:
                    item = await self._events.get()
                    if item is None:
                        self._events.put_nowait(None)
                        return {"type": "_stream_end"}
                    if item.get("usage_only") or item.get("response_id") not in self._cancelled_response_ids:
                        return item
        except asyncio.TimeoutError:
            return None

    def discard_queued(self) -> None:
        while True:
            try:
                item = self._events.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None:
                self._events.put_nowait(None)
                break

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._events.get()
            if item is None:
                break
            if not item.get("usage_only") and item.get("response_id") in self._cancelled_response_ids:
                continue
            yield item

    async def close(self) -> None:
        self._closed = True
        self._accepting = False
        self._response_idle.set()
        if self._pump_task and not self._pump_task.done():
            self._pump_task.cancel()
            try:
                await self._pump_task
            except asyncio.CancelledError:
                pass
        if self._connect_cm is not None:
            try:
                await self._connect_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._connect_cm = None
            self._session = None
        await self._events.put(None)

    def recv_pump_alive(self) -> bool:
        return self._pump_task is not None and not self._pump_task.done()

    async def ensure_recv_pump(self) -> None:
        """Restart Gemini receive loop when the server closes an idle stream segment."""
        if self._closed or self._session is None:
            return
        if self.recv_pump_alive():
            return
        if self._pump_restarts >= 6:
            logger.warning("[GEMINI_LIVE] recv pump restart limit reached")
            return
        self._pump_restarts += 1
        self._pump_task = asyncio.create_task(self._pump(), name="gemini-live-voice-recv")
        logger.warning("[GEMINI_LIVE] recv pump restarted attempt=%s", self._pump_restarts)

    async def _pump(self) -> None:
        session = self._session
        if session is None:
            return
        cancelled = False
        try:
            async for message in session.receive():
                self._pump_restarts = 0
                for evt in self._normalize(message):
                    await self._events.put(evt)
        except asyncio.CancelledError:
            cancelled = True
            return
        except Exception as exc:
            logger.warning("[GEMINI_LIVE] recv loop ended: %s", str(exc)[:200])
            await self._events.put({"type": "error", "message": str(exc)[:240]})
        finally:
            if cancelled:
                return
            if not self._closed and self._session is not None and self._pump_restarts < 6:
                self._pump_restarts += 1
                self._pump_task = asyncio.create_task(self._pump(), name="gemini-live-voice-recv")
                logger.warning(
                    "[GEMINI_LIVE] recv loop ended; auto-restart attempt=%s",
                    self._pump_restarts,
                )
                return
            if not self._closed:
                logger.warning("[GEMINI_LIVE] recv loop finished while session still open")
            self._ready.set()
            await self._events.put(None)

    def _normalize(self, message: types.LiveServerMessage) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        if message.setup_complete is not None:
            self._configured = True
            self._ready.set()
            return events

        # Live API v1beta often opens with session_resumption_update instead of setup_complete.
        if message.session_resumption_update is not None and not self._configured:
            self._configured = True
            self._ready.set()
            return events

        if message.voice_activity is not None:
            va = message.voice_activity
            activity = str(getattr(va, "voice_activity_type", ""))
            if getattr(va, "speech_started", None) or activity.endswith("ACTIVITY_START"):
                self._input_transcript = ""
                self._input_transcript_final = False
                self._drop_until_turn_complete = False
                events.append({"type": "speech_started"})
            if getattr(va, "speech_ended", None) or activity.endswith("ACTIVITY_END"):
                events.append({"type": "speech_stopped"})

        if message.tool_call and message.tool_call.function_calls:
            rid = self._ensure_response_id()
            if (self._auto_response or self._accepting) and not self._accepting:
                self._accepting = True
                self._response_idle.clear()
                events.append({"type": "response_created", "response_id": rid})
            for fc in message.tool_call.function_calls:
                args = fc.args
                if isinstance(args, dict):
                    args_payload = json.dumps(args)
                else:
                    args_payload = str(args or "")
                events.append(
                    {
                        "type": "function_call",
                        "name": str(fc.name or ""),
                        "arguments": args_payload,
                        "call_id": str(fc.id or ""),
                        "response_id": rid,
                    }
                )
            if self._auto_response or self._accepting:
                if not self._accepting:
                    self._accepting = True
                    if self._response_idle.is_set():
                        self._response_idle.clear()
                    events.append({"type": "response_created", "response_id": rid})

        content = message.server_content
        if content is None:
            if message.usage_metadata:
                rid = self._active_response_id or (self._completed_response_ids[-1] if self._completed_response_ids else "")
                events.append({"type": "response_done", "usage_only": True,
                               "response_id": rid, "usage": {**_usage_from_message(message), "usage_scope": "response", "usage_id": rid}})
            return events

        if content.interrupted:
            rid = self._active_response_id or ""
            if rid:
                self._completed_response_ids.append(rid)
            self._accepting = False
            self._active_response_id = None
            self._response_idle.set()
            self._drop_until_turn_complete = False
            events.append({"type": "cancelled", "response_id": rid, "provider_interrupted": True})

        if content.input_transcription:
            if self._input_transcript_final:
                self._input_transcript = ""
            self._input_transcript += content.input_transcription.text or ""
            self._input_transcript_final = bool(getattr(content.input_transcription, "finished", False))
            events.append(
                {
                    "type": "user_transcript",
                    "text": self._input_transcript,
                    "final": self._input_transcript_final,
                }
            )

        rid = self._active_response_id or ""
        if self._drop_until_turn_complete:
            if content.turn_complete:
                self._drop_until_turn_complete = False
                done = self._emit_response_done(message, rid)
                if done and done.get("usage"):
                    done["usage_only"] = True
                    events.append(done)
            elif message.usage_metadata:
                events.append({"type": "response_done", "usage_only": True,
                               "response_id": rid, "usage": {**_usage_from_message(message),
                               "usage_scope": "response", "usage_id": rid}})
            return events
        has_output = bool(content.output_transcription or content.model_turn)
        if has_output and not self._accepting and self._auto_response:
            if self._input_transcript and not self._input_transcript_final:
                events.append({"type": "user_transcript", "text": self._input_transcript, "final": True})
                self._input_transcript_final = True
            self._accepting = True
            self._response_idle.clear()
            rid = self._ensure_response_id()
            events.append({"type": "response_created", "response_id": rid})
        if content.output_transcription and content.output_transcription.text:
            if not rid and (self._auto_response or self._accepting):
                rid = self._ensure_response_id()
            events.append(
                {
                    "type": "assistant_transcript_delta",
                    "delta": content.output_transcription.text,
                    "response_id": rid,
                }
            )

        turn = content.model_turn
        if turn and turn.parts:
            if not self._accepting and self._auto_response:
                self._accepting = True
                if self._response_idle.is_set():
                    self._response_idle.clear()
                rid = self._ensure_response_id()
                events.append({"type": "response_created", "response_id": rid})
            elif self._accepting:
                rid = self._ensure_response_id()
            for part in turn.parts:
                blob = part.inline_data
                if blob and blob.data and self._accepting:
                    events.append(
                        {
                            "type": "audio_delta",
                            "pcm": bytes(blob.data),
                            "response_id": rid,
                        }
                    )

        if content.turn_complete:
            done_rid = rid or (self._active_response_id or "")
            done = self._emit_response_done(message, done_rid)
            if done is not None:
                events.append(done)
        elif message.usage_metadata:
            events.append({"type": "response_done", "usage_only": True,
                           "response_id": rid, "usage": {**_usage_from_message(message), "usage_scope": "response", "usage_id": rid}})
        return events
