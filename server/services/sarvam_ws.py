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
               output_audio_codec,output_audio_bitrate,temperature(v3),sample_rate?}}
              {"type":"text","data":{"text":"..."}} (≤2500, <500 rec) | {"type":"flush"} | {"type":"ping"}
  srv→client: audio chunks (base64 in data.audio) | event notification | error
  NOTE: no server-side cancel — barge-in is client-side.
"""
from __future__ import annotations

from typing import Any

import websockets  # provided by uvicorn[standard]

from server.config.constants import constants
from server.config.env import get_settings


def _connect(url: str, headers: dict[str, str], **kw: Any):
    """websockets v13+: additional_headers; older: extra_headers."""
    try:
        return websockets.connect(url, additional_headers=headers, max_size=None, **kw)
    except TypeError:  # pragma: no cover - older lib
        return websockets.connect(url, extra_headers=headers, max_size=None, **kw)


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
    high_vad_sensitivity: bool = True,
):
    settings = get_settings()
    params = {
        "language_code": language_code,
        "model": "saaras:v3-realtime",
        "stream_type": stream_type,
        "mode": mode,
        "endpointing": endpointing,
        "encoding": "linear16",
        "sample_rate": str(sample_rate),
    }
    if silence_duration_ms is not None:
        params["silence_duration_ms"] = str(silence_duration_ms)
    if threshold is not None:
        params["threshold"] = str(threshold)
    if min_speech_duration_ms is not None:
        params["min_speech_duration_ms"] = str(min_speech_duration_ms)
    if high_vad_sensitivity:
        params["high_vad_sensitivity"] = "true"
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{constants.SARVAM_STT_REALTIME_WS}?{qs}"
    headers = {"api-subscription-key": settings.sarvam_api_key}
    return _connect(url, headers, ping_interval=20, ping_timeout=20)


def connect_tts_ws(model: str = "bulbul:v3"):
    settings = get_settings()
    url = f"{constants.SARVAM_TTS_WS}?model={model}&send_completion_event=true"
    headers = {"api-subscription-key": settings.sarvam_api_key}
    return _connect(url, headers, ping_interval=None)  # we send app-level pings per protocol
