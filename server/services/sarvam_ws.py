"""
Sarvam WebSocket upstream connectors — server/services/sarvam_ws.py
Verified protocols (docs.sarvam.ai, Aug 2026):

STT realtime: wss://api.sarvam.ai/speech-to-text-realtime/ws
  query: language_code(req), model=saaras:v3-realtime, stream_type=fast|balanced|simulated,
         mode, endpointing=vad|manual, encoding=linear16, sample_rate=16000|8000,
         threshold, silence_duration_ms, min_speech_duration_ms, prompt, return_timestamps
  client→srv JSON: {"event":"audio_input","audio":"<b64 PCM>"} | speech_start/speech_end/flush |
                   {"event":"config.update",...} | {"event":"end"} | ping
  srv→client: session.begin, vad.speech_start/end, transcript.partial{.text},
              transcript.final{.text}, config.updated, pong, session.end{audio_duration_s},
              error{code,is_fatal,message}
  auth header: api-subscription-key ; close codes 1003 auth/quota,1008 idle(ping!),1011 err,4000 bad param

TTS WS: wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v3&send_completion_event=true
  client→srv: {"type":"config","data":{speaker,language_code,pace,min_buffer_size,max_chunk_length,
               output_audio_codec,speech_sample_rate,temperature(v3)}}
              {"type":"text","data":{"text":"..."}} (≤2500, <500 rec) | {"type":"flush"} | {"type":"ping"}
  srv→client: audio chunks (base64 in data.audio) | event notification | error
  NOTE: no server-side cancel — barge-in is client-side.
"""
from __future__ import annotations

import inspect
from typing import Any

import websockets  # provided by uvicorn[standard]

from server.config.constants import constants, provider_language_code
from server.config.env import get_settings
from server.services.voice_stt_runtime import sarvam_vad_config


def _connect(url: str, headers: dict[str, str], **kw: Any):
    """Select the installed client API before connect defers work until await."""
    parameters = inspect.signature(websockets.connect).parameters
    header_name = "additional_headers" if "additional_headers" in parameters else "extra_headers"
    return websockets.connect(url, **{header_name: headers}, max_size=None, **kw)


def _handshake_status(exc: BaseException) -> int | None:
    """HTTP status of a rejected WebSocket upgrade (websockets 10-14 shapes)."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _handshake_body(exc: BaseException) -> bytes | None:
    response = getattr(exc, "response", None)
    body = getattr(response, "body", None)
    return body if isinstance(body, (bytes, bytearray)) else None


class _FailoverConnect:
    """Drop-in for ``websockets.connect(...)``: awaitable and ``async with``.

    A handshake rejected for credits / quota / auth retries the upgrade with
    the next Sarvam key before the caller sees anything.
    """

    def __init__(self, url: str, component: str, label: str, connect_kwargs: dict[str, Any]) -> None:
        self._url = url
        self._component = component
        self._label = label
        self._kwargs = connect_kwargs
        self._ws = None
        from server.services.sarvam_keys import sarvam_key_pool

        self._attempts = sarvam_key_pool.plan()
        # websockets.connect() is lazy, so building the first attempt now
        # costs nothing and keeps the URL/headers inspectable before await.
        self._first = (
            _connect(url, {"api-subscription-key": self._attempts[0][1]}, **connect_kwargs)
            if self._attempts else None
        )

    async def _open(self):
        from server.services import provider_health as ph
        from server.services.sarvam_keys import _handle_rejection, no_key_available, sarvam_key_pool

        attempts = self._attempts
        if not attempts:
            raise no_key_available(self._component, self._label)
        for index, (slot, key) in enumerate(attempts):
            sarvam_key_pool.mark_attempt(slot)
            try:
                pending = self._first if index == 0 else _connect(
                    self._url, {"api-subscription-key": key}, **self._kwargs)
                ws = await pending
            except Exception as exc:
                status = _handshake_status(exc)
                if status is None:
                    ph.record_exception(exc, provider="sarvam", component=self._component, key_slot=slot)
                    raise
                if _handle_rejection(attempts, index, component=self._component, status=status,
                                     body=_handshake_body(exc)):
                    continue
                raise
            sarvam_key_pool.report_success(slot, component=self._component)
            return ws
        raise no_key_available(self._component, self._label)

    def __await__(self):
        return self._open().__await__()

    async def __aenter__(self):
        self._ws = await self._open()
        return self._ws

    async def __aexit__(self, exc_type, exc, tb):
        ws, self._ws = self._ws, None
        if ws is not None:
            await ws.close()
        return False


def _resolve_realtime_stt_model(model: str | None = None) -> str:
    """Map REST catalog model to realtime WS model (SARVAM_STT_MODEL env)."""
    settings = get_settings()
    raw = (model or settings.sarvam_stt_model).strip()
    if raw.endswith("-realtime"):
        return raw
    if raw == "saaras:v3":
        return "saaras:v3-realtime"
    return raw


def connect_stt_realtime(
    *,
    language_code: str = "te-IN",
    stream_type: str = "fast",
    mode: str = "transcribe",
    endpointing: str = "vad",
    sample_rate: int = 16000,
    silence_duration_ms: int | None = None,
    threshold: float | None = None,
    min_speech_duration_ms: int | None = None,
    prefix_padding_ms: int | None = None,
    high_vad_sensitivity: bool = False,
    model: str | None = None,
):
    settings = get_settings()
    params = {
        "language_code": provider_language_code(language_code, provider="sarvam", stage="stt"),
        "model": _resolve_realtime_stt_model(model),
        "stream_type": stream_type,
        "mode": mode,
        "endpointing": endpointing,
        "encoding": "linear16",
        "sample_rate": str(sample_rate),
    }
    vad = sarvam_vad_config({
        "silence_duration_ms": silence_duration_ms, "threshold": threshold,
        "min_speech_duration_ms": min_speech_duration_ms, "prefix_padding_ms": prefix_padding_ms,
    })
    params.update({key: str(value) for key, value in vad.items()})
    # Explicit VAD controls supersede the legacy high-sensitivity shortcut.
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{constants.SARVAM_STT_REALTIME_WS}?{qs}"
    return _FailoverConnect(url, "stt", "Sarvam realtime speech-to-text",
                            {"ping_interval": 20, "ping_timeout": 20})


def connect_tts_ws(model: str = "bulbul:v3"):
    settings = get_settings()
    url = f"{constants.SARVAM_TTS_WS}?model={model}&send_completion_event=true"
    # We send app-level pings per protocol.
    return _FailoverConnect(url, "tts", "Sarvam text-to-speech WebSocket", {"ping_interval": None})
