"""
WebSocket routes — server/routes/ws.py
/ws/stt-realtime : browser PCM16 → Sarvam saaras:v3-realtime (partials + VAD events back)
/ws/tts          : browser JSON config/text → Sarvam bulbul WS → base64 audio chunks back

TTS design (fix.md Issue #1/#4):
  • Browser WebSocket stays open for the whole live session.
  • Sarvam upstream may close after each flush — proxy reconnects upstream silently.
  • Browser is notified via {"type":"upstream_reset"} so it can re-send config.
"""
from __future__ import annotations

import asyncio
import base64
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.config.constants import constants
from server.config.env import get_settings
from server.providers import get_provider_registry, resolve_stack_for_session
from server.providers.base import STTConfig, TTSConfig
from server.services.runtime_settings import runtime_settings
from server.services.tts_config import TtsConfigError, merge_ws_tts_config
from server.utils.logger import log_error, log_ws

router = APIRouter()

_UPSTREAM_STT_EVENTS = {"audio_input", "speech_start", "speech_end", "flush", "config.update", "end", "ping"}


def _upstream_tts_config_payload(merged: dict) -> dict:
    """Browser TTS upstream config — preserve sample rate so playback matches generation."""
    out: dict = {
        "speaker": merged["speaker"],
        "language_code": merged["language_code"],
        "pace": merged["pace"],
        "min_buffer_size": merged["min_buffer_size"],
        "max_chunk_length": merged["max_chunk_length"],
        "output_audio_codec": merged["output_audio_codec"],
        "output_audio_bitrate": merged["output_audio_bitrate"],
        "model": merged["model"],
    }
    if "temperature" in merged:
        out["temperature"] = merged["temperature"]
    rate = merged.get("sample_rate")
    if rate is not None:
        rate_str = str(int(rate))
        provider = str(merged.get("provider") or "sarvam")
        if provider == "cartesia":
            out["sample_rate"] = int(rate)
            out["speech_sample_rate"] = rate_str
        elif provider == "sarvam":
            # Sarvam WS expects speech_sample_rate (not sample_rate).
            out["speech_sample_rate"] = rate_str
    return out


def _stack_for_ws(call_id: str | None, session_id: str, language: str = "te-IN"):
    if call_id:
        from server.call.call_context import get as get_call_ctx

        ctx = get_call_ctx(call_id)
        if ctx:
            return ctx.resolved_stack
    return resolve_stack_for_session(session_id, language=language)


def _connect_stt_upstream(session_id: str = "default", call_id: str | None = None, **kwargs):
    """Resolve STT upstream via locked call stack or provider registry."""
    settings = get_settings()
    if settings.use_provider_registry:
        stack = _stack_for_ws(call_id, session_id, language=kwargs.get("language_code", "te-IN"))
        registry = get_provider_registry()
        stt = registry.get_stt(stack.stt.provider)
        config = STTConfig(
            provider=stack.stt.provider,
            model=kwargs.get("model") or stack.stt.model,
            language=kwargs.get("language_code", stack.language),
            mode="realtime",
            stream_type=kwargs.get("stream_type", stack.stt.config.get("stream_type", "fast")),
            sample_rate=kwargs.get("sample_rate", 16000),
            vad_config={
                "silence_duration_ms": kwargs.get("silence_duration_ms"),
                "threshold": kwargs.get("threshold"),
            },
        )
        return stt.connect_realtime(config)
    return connect_stt_realtime(**kwargs)


def _is_cartesia_model(model: str) -> bool:
    return model in constants.CARTESIA_TTS_MODELS or str(model).startswith("sonic")


def _resolve_ws_tts_model(model: str, session_id: str, call_id: str | None) -> str:
    try:
        resolved = merge_ws_tts_config(session_id, {}, call_id=call_id, ws_model=model)
        return str(resolved.get("model") or "bulbul:v3")
    except Exception:
        stack = _stack_for_ws(call_id, session_id)
        if stack:
            if stack.tts.provider == "cartesia" or _is_cartesia_model(stack.tts.model):
                return stack.tts.model
            if model in constants.TTS_MODELS:
                return model
            return stack.tts.model
        if model in constants.TTS_MODELS or _is_cartesia_model(model):
            return model
        return "bulbul:v3"


def _connect_tts_upstream(
    model: str,
    session_id: str = "default",
    call_id: str | None = None,
    *,
    resolved: dict | None = None,
):
    """Open TTS from a frozen media profile when provided — never re-resolve a locked PSTN stack."""
    from server.services.sarvam_ws import connect_tts_ws
    from server.services.tts_config import resolve_tts_config

    locked = resolved is not None
    cfg = resolved if locked else resolve_tts_config(session_id, model=model, call_id=call_id)
    provider = str(cfg.get("provider") or "sarvam")
    effective_model = str(cfg.get("model") or model or "bulbul:v3")
    speaker = str(cfg.get("speaker") or "shubh")
    language = str(cfg.get("language_code") or "te-IN")
    settings = get_settings()
    if settings.use_provider_registry:
        registry = get_provider_registry()
        # Locked call profiles stay on the provider that merge_pstn_tts_config chose.
        # Runtime/env fallbacks apply only when this helper is resolving from scratch.
        if not locked and not registry.is_provider_enabled(provider, "tts"):
            provider = "sarvam"
            if effective_model not in constants.TTS_MODELS:
                effective_model = "bulbul:v3"
            from server.services.cartesia_voices import is_cartesia_voice_id

            if is_cartesia_voice_id(speaker):
                speaker = settings.sarvam_tts_speaker_te
        tts = registry.get_tts(provider)
        config = TTSConfig(
            provider=provider,
            model=effective_model,
            language=language,
            speaker=speaker,
        )
        log_ws(
            "TTS upstream opening",
            provider=provider,
            model=effective_model,
            speaker=speaker,
            session=session_id,
            call_id=call_id,
            locked=locked,
        )
        return tts.connect_stream(config)
    return connect_tts_ws(model=effective_model if effective_model in constants.TTS_MODELS else "bulbul:v3")


@router.websocket("/ws/stt-realtime")
async def ws_stt_realtime(ws: WebSocket):
    await ws.accept()
    q = ws.query_params
    session_id = q.get("sessionId", "default")
    call_id = q.get("call_id") or q.get("callId")
    upstream = None
    upstream_task = None
    ping_task = None
    try:
        if not call_id and get_settings().enable_call_archive:
            log_ws("STT connected without call_id — audio will not be archived")
        if call_id:
            from server.call.call_lifecycle_service import call_lifecycle_service

            call_lifecycle_service.note_ws_open(call_id)
        rt = runtime_settings.get(session_id)
        from server.services.voice_stt_runtime import (
            effective_stt_mode,
            effective_stt_silence_ms,
            effective_stt_stream_type,
        )

        explicit_silence = int(q["silence_duration_ms"]) if q.get("silence_duration_ms") else None
        silence_ms = effective_stt_silence_ms(rt, explicit=explicit_silence)
        threshold_val = float(q["threshold"]) if q.get("threshold") else rt.get("sttThreshold")
        upstream_cm = _connect_stt_upstream(
            session_id=session_id,
            call_id=call_id,
            language_code=q.get("language_code", "te-IN"),
            stream_type=effective_stt_stream_type(q.get("stream_type") or rt.get("sttStreamType")),
            mode=effective_stt_mode(q.get("mode") or rt.get("sttMode")),
            endpointing=q.get("endpointing", "vad"),
            sample_rate=int(q.get("sample_rate", 16000)),
            silence_duration_ms=silence_ms,
            threshold=float(threshold_val) if threshold_val is not None else None,
        )
        upstream = await upstream_cm.__aenter__()
        log_ws("STT upstream connected", session=session_id, language=q.get("language_code", "te-IN"))

        audio_stats = {"frames": 0, "peak": 0}

        async def upstream_to_client():
            try:
                async for raw in upstream:
                    if isinstance(raw, bytes):
                        raw = raw.decode(errors="ignore")
                    try:
                        msg = json.loads(raw)
                        ev = msg.get("event") or msg.get("type") or ""
                        data_obj = msg.get("data") if isinstance(msg.get("data"), dict) else {}
                        txt = (msg.get("text") or data_obj.get("text") or "")[:80]
                        if ev in (
                            "session.begin",
                            "transcript.partial",
                            "transcript.final",
                            "error",
                            "vad.speech_start",
                            "vad.speech_end",
                        ):
                            log_ws("STT relay", event=ev, text=txt, session=session_id, call_id=call_id)
                    except Exception:
                        pass
                    await ws.send_text(raw)
            except Exception as exc:
                log_error("STT upstream read failed", err=str(exc)[:300], session=session_id)
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
                    audio_stats["frames"] += 1
                    probe = data[: min(len(data), 4096)]
                    for i in range(0, len(probe) - 1, 2):
                        sample = int.from_bytes(probe[i : i + 2], "little", signed=True)
                        amp = abs(sample)
                        if amp > audio_stats["peak"]:
                            audio_stats["peak"] = amp
                    if audio_stats["frames"] == 1 or audio_stats["frames"] % 40 == 0:
                        log_ws(
                            "STT audio in",
                            frames=audio_stats["frames"],
                            bytes=len(data),
                            peak=audio_stats["peak"],
                            session=session_id,
                            call_id=call_id,
                        )
                    if call_id:
                        from server.call.audio_archive import audio_archive

                        asyncio.create_task(audio_archive.append_user_pcm(call_id, data))
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
        if call_id:
            try:
                from server.call.call_lifecycle_service import call_lifecycle_service

                call_lifecycle_service.note_ws_close(call_id)
            except Exception:
                pass
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
    Persistent browser proxy — upstream Sarvam WS reconnects per synthesis turn.
    Client keeps one /ws/tts open; sends config+text+flush each turn.
    """
    await ws.accept()
    model = ws.query_params.get("model", "bulbul:v3")
    session_id = ws.query_params.get("sessionId", "default")
    call_id = ws.query_params.get("call_id") or ws.query_params.get("callId")
    model = _resolve_ws_tts_model(model, session_id, call_id)
    if model not in constants.TTS_MODELS and not str(model).startswith("sonic") and model not in constants.CARTESIA_TTS_MODELS:
        model = "bulbul:v3"

    if call_id:
        from server.call.call_lifecycle_service import call_lifecycle_service

        call_lifecycle_service.note_ws_open(call_id)

    upstream = None
    upstream_cm = None
    upstream_lock = asyncio.Lock()
    client_open = True
    reader_task = None
    ping_task = None
    audio_chunks = 0
    configured = False
    last_upstream_config: dict | None = None

    async def close_upstream():
        nonlocal upstream, upstream_cm, configured
        async with upstream_lock:
            if upstream is not None:
                try:
                    await upstream.close()
                except Exception:
                    pass
                upstream = None
            upstream_cm = None
            configured = False

    async def notify_upstream_reset(reason: str) -> None:
        if not client_open:
            return
        try:
            await ws.send_text(json.dumps({"type": "upstream_reset", "reason": reason}))
        except Exception:
            pass

    async def connect_upstream() -> None:
        nonlocal upstream, upstream_cm, configured, audio_chunks
        async with upstream_lock:
            if upstream is not None:
                return
            upstream_cm = _connect_tts_upstream(model, session_id=session_id, call_id=call_id)
            upstream = await upstream_cm.__aenter__()
            configured = False
            audio_chunks = 0
            log_ws("TTS upstream connected", model=model, session=session_id)

    async def upstream_reader():
        nonlocal audio_chunks, configured, client_open
        while client_open:
            try:
                await connect_upstream()
                assert upstream is not None
                async for raw in upstream:
                    if not client_open:
                        break
                    if isinstance(raw, bytes):
                        raw = raw.decode(errors="ignore")
                    try:
                        obj = json.loads(raw)
                        if obj.get("type") == "audio" or obj.get("type") == "chunk" or (
                            obj.get("data")
                            and isinstance(obj.get("data"), dict)
                            and obj["data"].get("audio")
                        ):
                            audio_chunks += 1
                            if audio_chunks == 1:
                                log_ws("TTS first audio chunk", session=session_id, model=model)
                            if call_id:
                                audio_b64 = obj.get("data", {}).get("audio") if isinstance(obj.get("data"), dict) else None
                                if not audio_b64:
                                    audio_b64 = obj.get("audio")
                                if audio_b64:
                                    from server.call.audio_archive import audio_archive

                                    asyncio.create_task(
                                        audio_archive.append_agent_audio(call_id, base64.b64decode(audio_b64))
                                    )
                    except Exception:
                        pass
                    await ws.send_text(raw)
                # Sarvam closed upstream after synthesis — reconnect on next client message
                log_ws("TTS upstream turn ended — will reconnect", session=session_id, chunks=audio_chunks)
                await close_upstream()
                await notify_upstream_reset("turn_complete")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log_ws("TTS upstream read error", session=session_id, reason=str(exc)[:120])
                await close_upstream()
                await notify_upstream_reset("upstream_error")
                await asyncio.sleep(0.15)

    async def forward_upstream(payload: str) -> None:
        nonlocal configured
        await connect_upstream()
        assert upstream is not None
        if not configured and last_upstream_config is not None:
            await upstream.send(json.dumps({"type": "config", "data": last_upstream_config}))
            configured = True
            log_ws("TTS auto-reconfig before forward", session=session_id)
        await upstream.send(payload)

    async def tts_keepalive():
        while client_open:
            await asyncio.sleep(20)
            try:
                if upstream is not None:
                    await upstream.send(json.dumps({"type": "ping"}))
            except Exception:
                pass

    try:
        reader_task = asyncio.create_task(upstream_reader())
        ping_task = asyncio.create_task(tts_keepalive())

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
                    merged = merge_ws_tts_config(session_id, d, call_id=call_id, ws_model=model)
                    out = _upstream_tts_config_payload(merged)
                    last_upstream_config = out
                    await connect_upstream()
                    assert upstream is not None
                    await upstream.send(json.dumps({"type": "config", "data": out}))
                    configured = True
                    log_ws(
                        "TTS configured",
                        session=session_id,
                        provider=merged.get("provider"),
                        model=out["model"],
                        speaker=out["speaker"],
                        codec=out["output_audio_codec"],
                        temperature=out.get("temperature"),
                        min_buffer=out["min_buffer_size"],
                    )
                except TtsConfigError as e:
                    await ws.send_text(json.dumps({"type": "error", "message": str(e), "code": "SPEAKER_INVALID"}))
            elif mtype == "text":
                piece = (obj.get("data") or {}).get("text") or ""
                if piece:
                    log_ws("TTS text forward", session=session_id, chars=len(piece))
                await forward_upstream(text)
            elif mtype == "flush":
                log_ws("TTS flush", session=session_id)
                await forward_upstream(text)
            elif mtype == "cancel":
                log_ws("TTS cancel", session=session_id)
                await close_upstream()
                configured = False
                await notify_upstream_reset("client_cancel")
            elif mtype == "ping":
                if upstream is not None:
                    await forward_upstream(text)
    except WebSocketDisconnect:
        log_ws("TTS WS disconnect", session=session_id)
    except Exception as e:
        log_error("TTS WS proxy error", err=str(e)[:300], session=session_id)
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)[:200]}))
        except Exception:
            pass
    finally:
        client_open = False
        if call_id:
            try:
                from server.call.call_lifecycle_service import call_lifecycle_service

                call_lifecycle_service.note_ws_close(call_id)
            except Exception:
                pass
        for t in (reader_task, ping_task):
            if t:
                t.cancel()
        await close_upstream()
