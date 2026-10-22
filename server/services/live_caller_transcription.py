"""Bounded, transcript-only audio streams for the primary Gemini PSTN flow.

The selected recognizer owns caller ledger text. Gemini still owns conversation
audio and turn/hangup decisions; a failed recognizer never changes voice provider.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

import websockets

from server.config.env import get_settings
from server.services.audio_transcode import StreamingPcmResampler
from server.services.dev_secrets_store import dev_secrets_store

LIVE_MODELS = frozenset({"gemini-native", "gpt-4o-mini-transcribe", "gpt-transcribe", "saaras:v3-realtime"})
OnFinal = Callable[[str], Awaitable[None]]
OnState = Callable[[str, str], Awaitable[None]]


def live_provider(model: str) -> str:
    if model == "gemini-native":
        return "gemini"
    if model == "saaras:v3-realtime":
        return "sarvam"
    if model in {"gpt-transcribe", "gpt-4o-mini-transcribe"}:
        return "openai"
    raise ValueError("Unsupported live transcription model")


def live_api_key(model: str) -> str:
    provider = live_provider(model)
    if provider == "gemini":
        return ""
    name = f"{provider}_api_key"
    return (dev_secrets_store.effective_secret(name) or getattr(get_settings(), name, "") or "").strip()


def validate_live_transcription(stack: dict[str, Any]) -> None:
    from server.services.transcription_policy import transcription_policy_from_stack

    policy = transcription_policy_from_stack(stack)
    raw_llm = stack.get("llm")
    llm = raw_llm if isinstance(raw_llm, dict) else {}
    from server.realtime.models import is_gemini_live_voice_model
    if policy.live_enabled and policy.live_model != "gpt-4o-mini-transcribe" and not (
            llm.get("provider") == "gemini" or is_gemini_live_voice_model(llm.get("model"))):
        raise ValueError("This live transcription option requires the Gemini voice stack")
    if policy.live_enabled and policy.live_model != "gemini-native" and not live_api_key(policy.live_model):
        raise ValueError("Selected live transcription credentials are unavailable")


class LiveCallerTranscriber:
    def __init__(self, *, model: str, language: str, input_rate: int,
                 on_final: OnFinal, on_state: OnState) -> None:
        self.model = model
        self.language = language
        self.provider = live_provider(model)
        if self.provider == "gemini":
            raise ValueError("Native transcription uses the conversation session")
        self.input_rate = input_rate
        self.rate = 16000 if self.provider == "sarvam" else 24000
        self._resampler = StreamingPcmResampler(input_rate, self.rate)
        self._on_final = on_final
        self._on_state = on_state
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=250)
        self._queued_bytes = 0
        self._task: asyncio.Task | None = None
        self._closing = False
        self._failure = ""
        self._sent_seconds = 0.0
        self._billed_seconds: float | None = None
        self._uncommitted_bytes = 0
        self._pending: deque[str] = deque()
        self._finals: dict[str, str] = {}
        self._partials: dict[str, str] = {}
        self._seen: deque[str] = deque(maxlen=1024)
        self._final_count = 0
        self._last_partial_at = 0.0
        self._end_sent = False
        self._needs_tail = True

    @property
    def billed_audio_sec(self) -> float:
        return self._billed_seconds if self._billed_seconds is not None else self._sent_seconds

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="pstn-live-transcription")

    def feed_pcm16(self, pcm16: bytes) -> None:
        if self._closing or self._failure or (self._task and self._task.done()) or not pcm16:
            return
        pcm = self._resampler.feed(pcm16)
        if not pcm:
            return
        # Five seconds of startup/backpressure, never unbounded customer audio.
        if self._queue.full() or self._queued_bytes + len(pcm) > self.rate * 2 * 5:
            self._failure = "audio_backpressure"
            if not self._queue.full():
                self._queue.put_nowait(None)
            return
        self._queued_bytes += len(pcm)
        self._queue.put_nowait(pcm)

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if not self._task:
            return
        try:
            if not self._task.done():
                await asyncio.wait_for(self._queue.put(None), timeout=1)
            await asyncio.wait_for(asyncio.shield(self._task), timeout=10)
        except (TimeoutError, asyncio.CancelledError):
            self._failure = self._failure or "finalization_timeout"
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def _connect(self):
        key = live_api_key(self.model)
        if not key:
            raise ValueError("Live transcription credentials unavailable")
        if self.provider == "sarvam":
            url = "wss://api.sarvam.ai/speech-to-text-realtime/ws?" + urlencode({
                "model": self.model, "language_code": "auto", "mode": "transcribe",
                "stream_type": "fast", "endpointing": "vad", "encoding": "linear16",
                "sample_rate": 16000, "silence_duration_ms": 500, "return_timestamps": "true",
            })
            headers = {"api-subscription-key": key}
        else:
            url = "wss://api.openai.com/v1/realtime?intent=transcription"
            headers = {"Authorization": f"Bearer {key}"}
        return websockets.connect(url, additional_headers=headers, open_timeout=8,
                                  close_timeout=2, ping_interval=20, ping_timeout=10, max_size=1_048_576)

    async def _configure(self, ws: Any) -> None:
        if self.provider == "openai":
            transcription: dict[str, Any] = {"model": self.model}
            if self.model == "gpt-transcribe":
                # A list enables natural Indian-language/English code mixing.
                transcription["languages"] = list(dict.fromkeys([self.language.split("-")[0], "en"]))
            else:
                transcription["language"] = self.language.split("-")[0]
            await ws.send(json.dumps({"type": "session.update", "session": {
                "type": "transcription", "audio": {"input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "transcription": transcription,
                    "turn_detection": {"type": "server_vad", "threshold": 0.5,
                                       "prefix_padding_ms": 300, "silence_duration_ms": 500},
                }}}}))
        expected = {"session.begin"} if self.provider == "sarvam" else {"session.updated", "transcription_session.updated"}
        async with asyncio.timeout(8):
            while True:
                event = json.loads(await ws.recv())
                if event.get("event", event.get("type")) == "error":
                    self._record_error(event)
                    raise RuntimeError("transcription_configuration_rejected")
                if event.get("event", event.get("type")) in expected:
                    return

    async def _run(self) -> None:
        workers: list[asyncio.Task] = []
        try:
            await self._on_state("connecting", "")
            if self._failure:
                return
            async with self._connect() as ws:
                await asyncio.wait_for(self._configure(ws), timeout=8)
                await self._on_state("streaming", "")
                writer = asyncio.create_task(self._send(ws))
                reader = asyncio.create_task(self._receive(ws))
                workers = [writer, reader]
                done, _ = await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                if reader in done and not self._end_sent:
                    raise RuntimeError("transcription_stream_closed")
                if writer in done and self._sent_seconds and self._needs_tail:
                    await asyncio.wait_for(asyncio.shield(reader), timeout=8)
        except asyncio.CancelledError:
            # Teardown may cancel the media task after all committed turns have
            # been delivered. Keep that completed transcript out of the failed
            # state; outstanding audio or turns still make cancellation partial.
            if not self._closing or self._queued_bytes or self._uncommitted_bytes or self._pending:
                self._failure = self._failure or "stream_cancelled"
        except Exception as exc:  # noqa: BLE001 -- supervised provider boundary records safe failure status
            # Never persist provider errors containing URLs, IDs, credentials or audio.
            self._failure = self._failure or type(exc).__name__
        finally:
            for task in workers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            while not self._queue.empty():
                self._queue.get_nowait()
            self._queued_bytes = 0
            status = "complete" if not self._failure else ("partial" if self._final_count else "failed")
            await self._on_state(status, "")

    async def _send(self, ws: Any) -> None:
        while True:
            pcm = await self._queue.get()
            if self._failure:
                raise RuntimeError("transcription_audio_backpressure")
            if pcm is None:
                self._end_sent = True
                if self.provider == "sarvam":
                    await asyncio.wait_for(ws.send(json.dumps({"event": "end"})), timeout=2)
                elif self._uncommitted_bytes >= self.rate // 5:
                    await asyncio.wait_for(ws.send(json.dumps({"type": "input_audio_buffer.commit"})), timeout=2)
                else:
                    self._needs_tail = bool(self._pending)
                return
            self._queued_bytes -= len(pcm)
            audio = base64.b64encode(pcm).decode("ascii")
            payload = ({"event": "audio_input", "audio": audio} if self.provider == "sarvam"
                       else {"type": "input_audio_buffer.append", "audio": audio})
            await asyncio.wait_for(ws.send(json.dumps(payload)), timeout=3)
            self._sent_seconds += len(pcm) / (self.rate * 2)
            self._uncommitted_bytes += len(pcm)

    async def _receive(self, ws: Any) -> None:
        async for raw in ws:
            event = json.loads(raw)
            kind = event.get("event", event.get("type", ""))
            if kind == "error":
                code = (event.get("error") or {}).get("code") if isinstance(event.get("error"), dict) else event.get("code")
                if self._closing and code == "input_audio_buffer_commit_empty":
                    if not self._pending:
                        return
                    continue
                self._record_error(event)
                raise RuntimeError("transcription_stream_rejected")
            if kind == "session.end":
                seconds = event.get("audio_duration_s")
                if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds) and seconds >= 0:
                    self._billed_seconds = float(seconds)
                return
            item = str(event.get("item_id") or event.get("utterance_id") or "")
            if kind == "input_audio_buffer.committed":
                self._uncommitted_bytes = 0
                if item and item not in self._pending and item not in self._seen:
                    self._pending.append(item)
                if len(self._pending) > 128:
                    raise RuntimeError("transcription_results_backpressure")
            if kind.endswith("input_audio_transcription.failed"):
                raise RuntimeError("transcription_turn_failed")
            if kind == "transcript.partial" or kind.endswith("input_audio_transcription.delta"):
                partial = str(event.get("text") or "")
                if self.provider == "openai":
                    partial = self._partials.get(item, "") + str(event.get("delta") or "")
                    self._partials[item] = partial[-16000:]
                    if len(self._partials) > 128:
                        raise RuntimeError("transcription_results_backpressure")
                if time.monotonic() - self._last_partial_at >= 0.5:
                    self._last_partial_at = time.monotonic()
                    await self._on_state("streaming", partial[-16000:])
            if kind == "transcript.final":
                if not item and event.get("start_s") is not None and event.get("end_s") is not None:
                    item = f"{event['start_s']}:{event['end_s']}"
                if not item or item not in self._seen:
                    await self._deliver(str(event.get("text") or ""))
                    if item:
                        self._seen.append(item)
            if kind.endswith("input_audio_transcription.completed") and item not in self._seen:
                if item not in self._pending:
                    self._pending.append(item)
                self._finals[item] = str(event.get("transcript") or "")
                self._partials.pop(item, None)
                # Completions can arrive out of order; committed IDs define turn order.
                while self._pending and self._pending[0] in self._finals:
                    head = self._pending.popleft()
                    await self._deliver(self._finals.pop(head))
                    self._seen.append(head)
                if self._end_sent and not self._pending:
                    return
        # A transport close is not a provider acknowledgement of the final turn.
        raise RuntimeError("transcription_stream_closed_before_final")

    async def _deliver(self, text: str) -> None:
        if text.strip():
            await self._on_final(text.strip())
            self._final_count += 1
        await self._on_state("streaming", "")

    def _record_error(self, event: dict[str, Any]) -> None:
        error = event.get("error") if isinstance(event.get("error"), dict) else event
        code = str(error.get("code") or "provider_rejected")
        self._failure = code if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,79}", code) else "provider_rejected"
