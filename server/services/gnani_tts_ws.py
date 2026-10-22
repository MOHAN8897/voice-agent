"""Gnani.ai (Vachana) TTS WebSocket upstream adapter — persistent low-latency streaming."""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

import websockets

from server.config.constants import constants
from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store

logger = logging.getLogger(__name__)

# Map generic / anonymized voice IDs to authentic Gnani Vachana voice catalog personas
_GNANI_VOICE_MAP: dict[str, str] = {
    "voice-gnani-1": "Nalini",
    "voice 1": "Nalini",
    "voice-1": "Nalini",
    "nalini": "Nalini",
    "shivani": "Shivani",
    "voice-gnani-2": "Pranav",
    "voice 2": "Pranav",
    "voice-2": "Pranav",
    "pranav": "Pranav",
    "avinash": "Avinash",
}


def _resolve_gnani_voice(raw: str | None) -> str:
    key = str(raw or "").strip().lower()
    return _GNANI_VOICE_MAP.get(key) or "Nalini"


def _gnani_language_code(language_code: str | None) -> str:
    lang = (language_code or "te-IN").strip()
    if lang.startswith("te"):
        return "te-IN"
    if lang.startswith("hi"):
        return "hi-IN"
    if lang.startswith("en"):
        return "en-IN"
    if lang.startswith("ta"):
        return "ta-IN"
    if lang.startswith("kn"):
        return "kn-IN"
    if lang.startswith("ml"):
        return "ml-IN"
    if lang.startswith("mr"):
        return "mr-IN"
    if lang.startswith("gu"):
        return "gu-IN"
    if lang.startswith("bn"):
        return "bn-IN"
    if lang.startswith("pa"):
        return "pa-IN"
    return "te-IN"


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
        resolved_model = constants.GNANI_DEFAULT_MODEL

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
            self._speaker = "Nalini"
            self._pending_done = False
            self._stripped_header = False

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
                if self._cfg.get("speaker"):
                    self._speaker = _resolve_gnani_voice(str(self._cfg["speaker"]))
                if self._cfg.get("language_code"):
                    self._language = _gnani_language_code(str(self._cfg["language_code"]))
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
                if not text.strip():
                    return
                await self._send_chunk(text)
                return
            if mtype == "flush":
                # Gnani is turn-based streaming; flush signifies end of current speaker turn
                self._pending_done = True

        async def _send_chunk(self, text: str) -> None:
            self._stripped_header = False
            pace_val = 1.0
            if self._cfg and self._cfg.get("pace"):
                try:
                    pace_val = max(0.5, min(2.0, float(self._cfg["pace"])))
                except (TypeError, ValueError):
                    pace_val = 1.0

            req = {
                "text": text,
                "voice": self._speaker,
                "model": self._model,
                "language": self._language,
                "speed": pace_val,
                "audio_config": {
                    "sample_rate": self._sample_rate,
                    "num_channels": 1,
                    "sample_width": 2,
                    "encoding": "linear_pcm",
                    "container": "wav",
                },
            }
            await self._ws.send(json.dumps(req))

        def __aiter__(self):
            return self

        async def __anext__(self) -> str:
            if self._pending_done:
                self._pending_done = False
                return json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}})

            while True:
                raw = await self._ws.recv()
                if isinstance(raw, bytes):
                    # Raw PCM/WAV binary frame
                    data_bytes = raw
                    if not self._stripped_header and len(data_bytes) >= 44 and data_bytes[:4] == b"RIFF":
                        data_bytes = data_bytes[44:]
                        self._stripped_header = True
                    b64 = base64.b64encode(data_bytes).decode("ascii")
                    return json.dumps(
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

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if "error" in data or "errors" in data or data.get("status") in (401, 402, 429):
                    err_msg = str(data.get("message") or data.get("error") or "Gnani TTS error")
                    is_credit = any(k in err_msg.lower() for k in ("credit", "balance", "quota", "payment", "unauthorized"))
                    return json.dumps(
                        {
                            "type": "error",
                            "code": "credits_exhausted" if is_credit else "gnani_error",
                            "message": err_msg,
                        }
                    )

                audio_b64 = data.get("audio") or data.get("data")
                if audio_b64 and isinstance(audio_b64, str):
                    try:
                        raw_bytes = base64.b64decode(audio_b64)
                        if not self._stripped_header and len(raw_bytes) >= 44 and raw_bytes[:4] == b"RIFF":
                            raw_bytes = raw_bytes[44:]
                            self._stripped_header = True
                            audio_b64 = base64.b64encode(raw_bytes).decode("ascii")
                    except Exception:
                        pass

                    return json.dumps(
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

                if data.get("is_final") or data.get("done"):
                    return json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}})

        async def close(self) -> None:
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
