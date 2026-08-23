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
from server.utils.logger import log_error, log_ws

router = APIRouter()

_UPSTREAM_STT_EVENTS = {"audio_input", "speech_start", "speech_end", "flush", "config.update", "end", "ping"}


@router.websocket("/ws/stt-realtime")
async def ws_stt_realtime(ws: WebSocket):
    await ws.accept()
    q = ws.query_params
    session_id = q.get("sessionId", "default")
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
        log_ws("STT upstream connected", session=session_id, language=q.get("language_code", "te-IN"))

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
        log_ws("STT client disconnected", session=session_id)
    except Exception as e:
        log_error("STT realtime proxy error", err=str(e)[:300], session=session_id)
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
    Browser connects: /ws/tts?model=bulbul:v3&sessionId=default
    Client must FIRST send {"type":"config","data":{...}} then {"type":"text",...}, {"type":"flush"}.
    Persistent across turns — client sends flush per turn, not close.
    """
    await ws.accept()
    model = ws.query_params.get("model", "bulbul:v3")
    session_id = ws.query_params.get("sessionId", "default")
    if model not in constants.TTS_MODELS:
        model = "bulbul:v3"
    upstream = None
    upstream_task = None
    configured = False
    audio_chunks = 0
    try:
        upstream_cm = connect_tts_ws(model)
        upstream = await upstream_cm.__aenter__()
        log_ws("TTS upstream connected", model=model, session=session_id)

        async def upstream_to_client():
            nonlocal audio_chunks
            try:
                async for raw in upstream:
                    if isinstance(raw, bytes):
                        raw = raw.decode(errors="ignore")
                    try:
                        obj = json.loads(raw)
                        if obj.get("type") == "audio" or (obj.get("data") and isinstance(obj.get("data"), dict) and obj["data"].get("audio")):
                            audio_chunks += 1
                            if audio_chunks == 1:
                                log_ws("TTS first audio chunk", session=session_id, model=model)
                    except Exception:
                        pass
                    await ws.send_text(raw)
            except Exception as exc:
                log_ws("TTS upstream read ended", session=session_id, reason=str(exc)[:120])
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
                    log_ws("TTS client disconnected", session=session_id, configured=configured, chunks=audio_chunks)
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
                        configured = True
                        log_ws(
                            "TTS configured",
                            session=session_id,
                            speaker=out["speaker"],
                            codec=out["output_audio_codec"],
                            temperature=out.get("temperature"),
                            min_buffer=out["min_buffer_size"],
                        )
                    except TtsConfigError as e:
                        await ws.send_text(json.dumps({"type": "error", "message": str(e), "code": "SPEAKER_INVALID"}))
                        continue
                elif mtype == "text":
                    piece = (obj.get("data") or {}).get("text") or ""
                    if piece:
                        log_ws("TTS text forward", session=session_id, chars=len(piece))
                    await upstream.send(text)
                elif mtype in ("flush", "ping"):
                    if mtype == "flush":
                        log_ws("TTS flush", session=session_id)
                    await upstream.send(text)

        upstream_task = asyncio.create_task(upstream_to_client())
        await client_to_upstream()
    except WebSocketDisconnect:
        log_ws("TTS WS disconnect", session=session_id)
    except Exception as e:
        log_error("TTS WS proxy error", err=str(e)[:300], session=session_id)
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
