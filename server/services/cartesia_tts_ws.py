"""Cartesia TTS WebSocket upstream — Sarvam browser-proxy compatible shim."""
from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import urlencode

import websockets

from server.config.constants import constants
from server.config.env import get_settings
from server.services.dev_secrets_store import dev_secrets_store


def _cartesia_language(language_code: str) -> str:
    code = (language_code or "te-IN").split("-")[0].lower()
    return code if code in {"en", "te", "hi", "es", "fr", "de", "ja", "ko", "pt", "zh"} else "en"


def _resolve_tts_model(model: str | None) -> str:
    settings = get_settings()
    raw = (model or settings.cartesia_tts_model or "sonic-3.5").strip()
    if raw in constants.CARTESIA_TTS_MODELS or raw.startswith("sonic"):
        return raw
    return "sonic-3.5"


def connect_cartesia_tts_ws(model: str | None = None, **_: Any):
    settings = get_settings()
    key = dev_secrets_store.effective_secret("cartesia_api_key") or settings.cartesia_api_key or ""
    if not key:
        raise RuntimeError("Cartesia API key not configured")

    resolved_model = _resolve_tts_model(model)
    version = settings.cartesia_api_version or constants.CARTESIA_API_VERSION
    params = {"cartesia_version": version}
    url = f"{constants.CARTESIA_TTS_WS}?{urlencode(params)}"
    headers = {"X-API-Key": key, "Cartesia-Version": version}

    class _CartesiaTtsProxy:
        def __init__(self, cm, ws):
            self._cm = cm
            self._ws = ws
            self._cfg: dict[str, Any] | None = None
            self._context_id: str | None = None
            self._model = resolved_model
            self._pending_done = False

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
                return
            if mtype == "ping":
                return
            if mtype == "text":
                text = str((obj.get("data") or {}).get("text") or "")
                if not text.strip():
                    return
                if not self._context_id:
                    self._context_id = str(uuid.uuid4())
                await self._send_generation(text, continue_=True)
                return
            if mtype == "flush":
                if self._context_id:
                    await self._send_generation("", continue_=False)
                    self._context_id = None
                else:
                    self._pending_done = True

        async def _send_generation(self, transcript: str, *, continue_: bool) -> None:
            cfg = self._cfg or {}
            voice_id = cfg.get("speaker") or settings.cartesia_tts_voice_id or constants.CARTESIA_DEFAULT_VOICE_ID
            sample_rate = int(cfg.get("sample_rate") or 24000)
            lang = _cartesia_language(str(cfg.get("language_code") or "te-IN"))
            req = {
                "model_id": self._model,
                "transcript": transcript,
                "voice": {"mode": "id", "id": voice_id},
                "output_format": {
                    "container": "raw",
                    "encoding": "pcm_s16le",
                    "sample_rate": sample_rate,
                },
                "language": lang,
                "context_id": self._context_id,
                "continue": continue_,
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
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type")
                if msg_type == "chunk":
                    audio_b64 = data.get("data") or ""
                    if audio_b64:
                        return json.dumps(
                            {
                                "type": "audio",
                                "data": {"audio": audio_b64, "event_type": "audio"},
                            }
                        )
                    if data.get("done"):
                        return json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}})
                    continue
                if msg_type == "done":
                    return json.dumps({"type": "end_of_stream", "data": {"event_type": "final"}})
                if msg_type == "error":
                    return json.dumps(
                        {
                            "type": "error",
                            "message": data.get("message") or data.get("title") or "Cartesia TTS error",
                            "code": data.get("error_code") or "cartesia_tts_error",
                        }
                    )

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
            return _CartesiaTtsProxy(self, ws)

        async def __aexit__(self, exc_type, exc, tb):
            try:
                await self._ws.close()
            except Exception:
                pass

    return _Connector()
