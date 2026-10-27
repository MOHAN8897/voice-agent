"""Gnani.ai (Vachana) TTS WebSocket upstream adapter — persistent low-latency streaming."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import websockets

from server.config.constants import constants
from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store

logger = logging.getLogger(__name__)

def _resolve_gnani_voice(speaker: str | None, *, model: str | None = None, language: str | None = None) -> str:
    from server.providers.voice_inventory import default_voice, voices_for_model

    selected_model = str(model or constants.GNANI_DEFAULT_MODEL)
    rows = voices_for_model("gnani", selected_model)
    if not rows:
        raise ValueError("The selected speech model is unavailable")
    requested = str(language or "").strip()
    if requested == "hi-en":
        requested = "hi-IN"
    elif requested == "auto":
        requested = ""
    wanted = str(speaker or "").strip()
    if wanted:
        # Case normalization preserves identity; aliases from another model do not.
        match = next((row for row in rows if row["providerVoiceId"].casefold() == wanted.casefold()), None)
        if match is not None and (not requested or requested in match["languages"]):
            return str(match["providerVoiceId"])
    return default_voice("gnani", selected_model, requested or None)


def _gnani_language_code(language_code: str | None, *, model: str | None = None) -> str:
    from server.providers.voice_inventory import voices_for_model

    lang = str(language_code or "te-IN").strip()
    if lang in {"auto", "hi-en"}:
        return lang
    from server.config.constants import normalize_supported_language

    lang = normalize_supported_language(lang)
    if lang == "en-US":
        lang = "en-IN"
    selected_model = str(model or constants.GNANI_DEFAULT_MODEL)
    supported = {code for row in voices_for_model("gnani", selected_model) for code in row["languages"]}
    if lang not in supported:
        raise ValueError("The selected speech model does not support this language")
    return lang


def _gnani_api_key() -> str:
    settings = get_settings()
    return dev_secrets_store.effective_secret("gnani_api_key") or settings.gnani_api_key or ""


def connect_gnani_tts_ws(model: str | None = None, **_: Any):
    settings = get_settings()
    key = _gnani_api_key()
    if not key:
        raise RuntimeError("Gnani API key not configured")

    resolved_model = str(model or settings.gnani_tts_model or constants.GNANI_DEFAULT_MODEL).strip()
    if resolved_model not in constants.GNANI_TTS_MODELS:
        raise ValueError("The selected speech model is unavailable")

    url = constants.GNANI_TTS_WS
    headers = {"X-API-Key-ID": key}

    class _GnaniTtsProxy:
        def __init__(self, cm, ws):
            self._cm = cm
            self._ws = ws
            self._cfg: dict[str, Any] | None = None
            self._model = resolved_model
            self._sample_rate = 16000
            self._language = "te-IN"
            self._requested_speaker: str | None = None
            self._speaker = _resolve_gnani_voice(None, model=resolved_model, language=self._language)
            self._queue: asyncio.Queue[str] = asyncio.Queue()
            self._requests_sent = 0
            self._requests_completed = 0
            self._flush_received = False
            self._eos_sent = False
            self._closed = False
            self._stripped_header = False
            self._send_lock = asyncio.Lock()
            self._request_done = asyncio.Event()
            self._request_done.set()
            self._reader_ended = False
            self._audio_progress = 0
            self._reader_task = asyncio.create_task(self._reader_loop())

        async def send(self, payload: str) -> None:
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                return
            mtype = obj.get("type")
            if mtype == "config":
                self._cfg = dict(obj.get("data") or {})
                if self._cfg.get("model"):
                    self._model = str(self._cfg["model"])
                if self._cfg.get("language_code"):
                    self._language = _gnani_language_code(str(self._cfg["language_code"]), model=self._model)
                if self._cfg.get("speaker"):
                    self._requested_speaker = str(self._cfg["speaker"])
                self._speaker = _resolve_gnani_voice(
                    self._requested_speaker, model=self._model, language=self._language
                )
                try:
                    self._sample_rate = int(
                        self._cfg.get("speech_sample_rate")
                        or self._cfg.get("sample_rate")
                        or self._sample_rate
                        or 16000
                    )
                except (TypeError, ValueError):
                    self._sample_rate = 16000
                return
            if mtype == "ping":
                return
            if mtype == "text":
                text = str((obj.get("data") or {}).get("text") or "")
                from server.prompts.tts_delivery_rules import sanitize_tts_tags

                text = sanitize_tts_tags(text, provider="gnani", model=self._model)
                if not text.strip():
                    return
                # The provider accepts one synthesis request at a time. Keep
                # consuming audio in the reader while a later sentence waits.
                async with self._send_lock:
                    await self._wait_for_request()
                    if self._closed or self._reader_ended:
                        raise RuntimeError("Speech stream closed before synthesis completed")
                    if self._flush_received or self._eos_sent:
                        self._flush_received = False
                        self._eos_sent = False
                    self._request_done.clear()
                    self._requests_sent += 1
                    await self._send_chunk(text)
                return
            if mtype == "flush":
                self._flush_received = True
                if not self._eos_sent and self._requests_completed >= self._requests_sent:
                    self._eos_sent = True
                    await self._queue.put(json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}}))

        async def _wait_for_request(self) -> None:
            # Bound a stalled request, while allowing long synthesis that keeps
            # producing audio. The call watchdog still bounds total call time.
            timeout = max(0.1, settings.request_timeout_ms / 1000)
            while not self._request_done.is_set():
                progress = self._audio_progress
                try:
                    await asyncio.wait_for(self._request_done.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    if progress == self._audio_progress:
                        raise

        async def _send_chunk(self, text: str) -> None:
            from server.providers.voice_inventory import provider_language

            language = provider_language("gnani", self._model, self._speaker, self._language)
            self._stripped_header = False
            pace_val = 1.0
            if self._cfg and self._cfg.get("pace"):
                try:
                    pace_val = max(0.85, min(1.15, float(self._cfg["pace"])))
                except (TypeError, ValueError):
                    pace_val = 1.0

            req = {
                "text": text,
                "voice": self._speaker,
                "model": self._model,
                "language": language,
                "speed": pace_val,
                "audio_config": {
                    "sample_rate": self._sample_rate,
                    "num_channels": 1,
                    "sample_width": 2,
                    "encoding": "linear_pcm",
                    "container": "raw",
                },
            }
            # Only documented delivery fields reach the provider. Unknown pitch
            # and volume keys can be silently ignored by its request schema.
            await self._ws.send(json.dumps(req))

        async def _reader_loop(self) -> None:
            try:
                while not self._closed:
                    try:
                        raw = await self._ws.recv()
                    except websockets.exceptions.ConnectionClosed:
                        break
                    except Exception:
                        break

                    if isinstance(raw, bytes):
                        self._audio_progress += 1
                        # Raw PCM/WAV binary frame
                        data_bytes = raw
                        if not self._stripped_header and len(data_bytes) >= 44 and data_bytes[:4] == b"RIFF":
                            data_bytes = data_bytes[44:]
                            self._stripped_header = True
                        b64 = base64.b64encode(data_bytes).decode("ascii")
                        await self._queue.put(
                            json.dumps(
                                {
                                    "type": "audio",
                                    "data": {
                                        "audio": b64,
                                        "event_type": "audio",
                                        "sample_rate": self._sample_rate,
                                        "speech_sample_rate": self._sample_rate,
                                    },
                                }
                            )
                        )
                        continue

                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    mtype = str(data.get("type") or "").lower()
                    if data.get("error") or data.get("errors") or data.get("status") in (401, 402, 403, 429) or mtype == "error":
                        err_msg = str(data.get("message") or data.get("error") or "Gnani TTS error")
                        is_credit = any(k in err_msg.lower() for k in ("credit", "balance", "quota", "payment", "unauthorized"))
                        fatal = is_credit or data.get("status") in (401, 402, 403) or data.get("fatal") is True or data.get("recoverable") is False
                        await self._queue.put(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "credits_exhausted" if is_credit else "gnani_error",
                                    "message": err_msg,
                                    "recoverable": not fatal,
                                }
                            )
                        )
                        if fatal:
                            break
                        if not self._request_done.is_set():
                            self._requests_completed += 1
                            self._request_done.set()
                        continue

                    is_final = bool((data.get("data") if isinstance(data.get("data"), dict) else {}).get("is_final") or data.get("is_final"))
                    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                    audio_b64 = (
                        data.get("audio")
                        or inner.get("audio")
                        or (data.get("data") if isinstance(data.get("data"), str) else None)
                    )
                    if audio_b64 and isinstance(audio_b64, str):
                        self._audio_progress += 1
                        try:
                            raw_bytes = base64.b64decode(audio_b64)
                            if not self._stripped_header and len(raw_bytes) >= 44 and raw_bytes[:4] == b"RIFF":
                                raw_bytes = raw_bytes[44:]
                                self._stripped_header = True
                                audio_b64 = base64.b64encode(raw_bytes).decode("ascii")
                        except Exception:
                            pass

                        await self._queue.put(
                            json.dumps(
                                {
                                    "type": "audio",
                                    "data": {
                                        "audio": audio_b64,
                                        "event_type": "audio",
                                        "sample_rate": self._sample_rate,
                                        "speech_sample_rate": self._sample_rate,
                                    },
                                }
                            )
                        )
                    # A final audio message may still contain the last PCM
                    # bytes. Deliver them before releasing the next request.
                    if mtype in ("complete", "end", "done") or is_final or data.get("done"):
                        if not self._request_done.is_set():
                            self._requests_completed += 1
                            self._request_done.set()
                        if not self._eos_sent and self._flush_received and self._requests_completed >= self._requests_sent:
                            self._eos_sent = True
                            await self._queue.put(json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}}))
            except asyncio.CancelledError:
                pass
            finally:
                self._reader_ended = True
                self._request_done.set()
                if not self._eos_sent:
                    self._eos_sent = True
                    await self._queue.put(json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}}))

        def __aiter__(self):
            return self

        async def __anext__(self) -> str:
            msg = await self._queue.get()
            return msg

        async def close(self) -> None:
            self._closed = True
            self._request_done.set()
            if hasattr(self, "_reader_task") and self._reader_task is not None:
                self._reader_task.cancel()
            try:
                await self._ws.close()
            except Exception:
                pass
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass

    class _Connector:
        async def __aenter__(self):
            try:
                ws = await websockets.connect(url, additional_headers=headers, max_size=None)
            except TypeError:
                ws = await websockets.connect(url, extra_headers=headers, max_size=None)
            except Exception as e:
                err_str = str(e).lower()
                if "401" in err_str or "402" in err_str or "429" in err_str or "credit" in err_str:
                    raise RuntimeError(f"HTTP 402/429 Gnani credits exhausted or unauthorized: {e}") from e
                raise
            self._ws = ws
            return _GnaniTtsProxy(self, ws)

        async def __aexit__(self, exc_type, exc, tb):
            try:
                await self._ws.close()
            except Exception:
                pass

    return _Connector()
