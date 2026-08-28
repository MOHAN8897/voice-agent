"""Cartesia STT WebSocket upstream — Sarvam-proxy compatible shim."""
from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlencode

import websockets

from server.config.constants import constants
from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store


def _cartesia_language(language_code: str, model: str) -> str:
    code = (language_code or "te-IN").split("-")[0].lower()
    if model == "ink-2":
        return "en"
    return code if code in {"en", "te", "hi", "es", "fr", "de", "ja", "ko", "pt", "zh"} else "en"


def _resolve_stt_model(model: str | None) -> str:
    settings = get_settings()
    raw = (model or settings.cartesia_stt_model or "ink-whisper").strip()
    if raw in constants.CARTESIA_STT_MODELS:
        return raw
    if raw in {"ink-whisper-2025-06-04", "saaras:v3"}:
        return "ink-whisper"
    return "ink-whisper"


def connect_cartesia_stt_realtime(
    *,
    language_code: str = "te-IN",
    sample_rate: int = 16000,
    model: str | None = None,
    **_: Any,
):
    settings = get_settings()
    key = dev_secrets_store.effective_secret("cartesia_api_key") or settings.cartesia_api_key or ""
    if not key:
        raise RuntimeError("Cartesia API key not configured")

    resolved_model = _resolve_stt_model(model)
    params = {
        "model": resolved_model,
        "encoding": "pcm_s16le",
        "sample_rate": str(sample_rate),
        "cartesia_version": settings.cartesia_api_version or constants.CARTESIA_API_VERSION,
        "language": _cartesia_language(language_code, resolved_model),
    }
    url = f"{constants.CARTESIA_STT_WS}?{urlencode(params)}"
    headers = {"X-API-Key": key}

    class _CartesiaSttProxy:
        def __init__(self, cm, ws):
            self._cm = cm
            self._ws = ws

        async def send(self, payload: str) -> None:
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                return
            event = obj.get("event")
            if event == "audio_input":
                audio = base64.b64decode(obj.get("audio") or "")
                if audio:
                    await self._ws.send(audio)
            elif event in ("speech_end", "flush"):
                await self._ws.send("finalize")
            elif event == "end":
                await self._ws.send("close")
            elif event == "ping":
                await self._ws.send(json.dumps({"type": "ping"}))

        def __aiter__(self):
            return self

        async def __anext__(self) -> str:
            while True:
                raw = await self._ws.recv()
                if isinstance(raw, bytes):
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_type = data.get("type")
                if msg_type == "transcript":
                    text = (data.get("text") or "").strip()
                    if not text:
                        continue
                    is_final = bool(data.get("is_final"))
                    if is_final:
                        return json.dumps(
                            {
                                "type": "final",
                                "text": text,
                                "transcript": text,
                            }
                        )
                    return json.dumps(
                        {
                            "type": "partial",
                            "text": text,
                            "transcript": text,
                        }
                    )
                if msg_type == "error":
                    return json.dumps(
                        {
                            "event": "error",
                            "code": data.get("error_code", "cartesia_error"),
                            "message": data.get("message") or data.get("title") or "Cartesia STT error",
                            "is_fatal": True,
                        }
                    )
                if msg_type in ("done", "flush_done"):
                    continue

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
            self._ws = ws
            return _CartesiaSttProxy(self, ws)

        async def __aexit__(self, exc_type, exc, tb):
            try:
                await self._ws.close()
            except Exception:
                pass

    return _Connector()
