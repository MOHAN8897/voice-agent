"""
WebSocket routes — server/routes/ws.py
/ws/stt-realtime : browser PCM16 → Sarvam saaras:v3-realtime (partials + VAD events back)
/ws/tts          : browser JSON config/text → Sarvam bulbul WS → base64 audio chunks back
Both are thin, validated proxies — keys never leave server.
"""
from __future__ import annotations

import asyncio
import base64
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.config.constants import constants
from server.services.sarvam_ws import connect_stt_realtime, connect_tts_ws
from server.services.tts_config import TtsConfigError, merge_ws_tts_config
from server.utils.logger import logger

router = APIRouter()

_UPSTREAM_STT_EVENTS = {"audio_input", "speech_start", "speech_end", "flush", "config.update", "end", "ping"}


@router.websocket("/ws/stt-realtime")
async def ws_stt_realtime(ws: WebSocket):
    """
    Browser connects: /ws/stt-realtime?language_code=te-IN&stream_type=fast&mode=transcribe
    Send: binary frames = raw linear16 PCM chunks (we base64+wrap), or text frames = JSON control.
    Receive: JSON text frames passthrough of Sarvam events.
    """
    await ws.accept()
    q = ws.query_params
    upstream = None
    upstream_task = None
    ping_task = None
    try:
        upstream_cm = connect_stt_realtime(
            language_code=q.get("language_code", "te-IN"),
            stream_type=q.get("stream_type", "fast"),
            mode=q.get("mode", "transcribe"),
            endpointing=q.get("endpointing", "vad"),
            sample_rate=int(q.get("sample_rate", 16000)),
            silence_duration_ms=int(q["silence_duration_ms"]) if q.get("silence_duration_ms") else None,
            threshold=float(q["threshold"]) if q.get("threshold") else None,
        )
        upstream = await upstream_cm.__aenter__()
        logger.info("[WS] STT realtime upstream connected")

        async def upstream_to_client():
            try:
                async for raw in upstream:
                    # Sarvam sends JSON text; pass through as-is
                    if isinstance(raw, bytes):
                        raw = raw.decode(errors="ignore")
                    await ws.send_text(raw)
            except Exception:
                pass
            finally:
                try:
                    await ws.close()
                except Exception:
                    pass

        async def client_to_upstream():
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                text = msg.get("text")
                if data:
                    b64 = base64.b64encode(data).decode()
                    await upstream.send(json.dumps({"event": "audio_input", "audio": b64}))
                elif text:
                    try:
                        obj = json.loads(text)
                        ev = obj.get("event")
                        if ev in _UPSTREAM_STT_EVENTS:
                            await upstream.send(text)
                    except Exception:
                        pass

        async def keepalive():
            while True:
                await asyncio.sleep(20)
                try:
                    await upstream.send(json.dumps({"event": "ping"}))
                except Exception:
                    return

        upstream_task = asyncio.create_task(upstream_to_client())
        ping_task = asyncio.create_task(keepalive())
        await client_to_upstream()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[WS] stt-realtime error: {str(e)[:300]}")
        try:
            await ws.send_text(json.dumps({"event": "error", "code": "proxy_error", "message": str(e)[:200]}))
        except Exception:
            pass
    finally:
        for t in (upstream_task, ping_task):
            if t:
                t.cancel()
        if upstream:
            try:
                await upstream.close()
            except Exception:
                pass


@router.websocket("/ws/tts")
async def ws_tts(ws: WebSocket):
    """
    Browser connects: /ws/tts?model=bulbul:v3
    Client must FIRST send {"type":"config","data":{...}} then {"type":"text",...}, {"type":"flush"}.
    Server proxies to Sarvam and streams back audio/event/error JSON as-is.
    """
    await ws.accept()
    model = ws.query_params.get("model", "bulbul:v3")
    session_id = ws.query_params.get("sessionId", "default")
    if model not in constants.TTS_MODELS:
        model = "bulbul:v3"
    upstream = None
    upstream_task = None
    configured = False
    try:
        upstream_cm = connect_tts_ws(model)
        upstream = await upstream_cm.__aenter__()
        logger.info(f"[WS] TTS upstream connected model={model}")

        async def upstream_to_client():
            try:
                async for raw in upstream:
                    if isinstance(raw, bytes):
                        raw = raw.decode(errors="ignore")
                    await ws.send_text(raw)
            except Exception:
                pass
            finally:
                try:
                    await ws.close()
                except Exception:
                    pass

        async def client_to_upstream():
            nonlocal configured
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                text = msg.get("text")
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except Exception:
                    continue
                mtype = obj.get("type")
                if mtype == "config":
                    d = dict(obj.get("data") or {})
                    try:
                        merged = merge_ws_tts_config(session_id, d)
                        merged["model"] = model
                        # Sarvam WS expects these keys in config payload
                        out = {
                            "speaker": merged["speaker"],
                            "language_code": merged["language_code"],
                            "pace": merged["pace"],
                            "min_buffer_size": merged["min_buffer_size"],
                            "max_chunk_length": merged["max_chunk_length"],
                            "output_audio_codec": merged["output_audio_codec"],
                            "output_audio_bitrate": merged["output_audio_bitrate"],
                        }
                        if "temperature" in merged:
                            out["temperature"] = merged["temperature"]
                        await upstream.send(json.dumps({"type": "config", "data": out}))
                    except TtsConfigError as e:
                        await ws.send_text(json.dumps({"type": "error", "message": str(e), "code": "SPEAKER_INVALID"}))
                        continue
                    configured = True
                elif mtype in ("text", "flush", "ping"):
                    await upstream.send(text)

        upstream_task = asyncio.create_task(upstream_to_client())
        await client_to_upstream()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[WS] tts error: {str(e)[:300]}")
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)[:200]}))
        except Exception:
            pass
    finally:
        if upstream_task:
            upstream_task.cancel()
        if upstream:
            try:
                await upstream.close()
            except Exception:
                pass
