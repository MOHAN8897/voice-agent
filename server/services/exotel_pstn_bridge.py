"""Exotel AgentStream bidirectional bridge — PSTN audio ↔ STT/Brain/TTS."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from fastapi import WebSocket

from server.services.audio_transcode import chunk_pcm_for_exotel, pcm16k_to_pcm8k, pcm8k_to_pcm16k

logger = logging.getLogger(__name__)


def parse_custom_field(value: str | dict[str, Any] | None) -> dict[str, str]:
    if not value:
        return {}
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    out: dict[str, str] = {}
    for part in str(value).split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


class ExotelPstnBridge:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.stream_sid: str | None = None
        self.exotel_call_sid: str | None = None
        self.call_id: str | None = None
        self.agent_id: str | None = None
        self.tier: str | None = None
        self.session_id: str = "pstn"
        self.caller_id: str | None = None
        self.direction: str = "outbound"
        self._stt_cm = None
        self._stt = None
        self._stt_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._agent_speaking = False
        self._turn_busy = False
        self._closed = False

    async def run(self, *, agent_id: str | None, tier: str | None, token_meta: dict[str, Any] | None) -> None:
        self.agent_id = agent_id or (token_meta or {}).get("agent_id")
        self.tier = tier or (token_meta or {}).get("tier")
        try:
            while not self._closed:
                raw = await self.ws.receive_text()
                ev = json.loads(raw)
                name = ev.get("event", "")
                if name == "connected":
                    continue
                if name == "start":
                    await self._on_start(ev)
                elif name == "media":
                    await self._on_media(ev)
                elif name == "mark":
                    if (ev.get("mark") or {}).get("name") == "turn-end":
                        self._agent_speaking = False
                elif name == "stop":
                    break
        finally:
            await self._cleanup("stop")

    async def _on_start(self, ev: dict[str, Any]) -> None:
        start = ev.get("start") or {}
        self.stream_sid = start.get("stream_sid") or ev.get("stream_sid")
        self.exotel_call_sid = start.get("call_sid")
        self.caller_id = start.get("from")
        custom = parse_custom_field(start.get("custom_parameters"))
        self.agent_id = self.agent_id or custom.get("agent") or custom.get("agent_id") or custom.get("agentId")
        self.tier = self.tier or custom.get("tier")

        from server.services.exotel_call_registry import exotel_call_registry

        if self.exotel_call_sid:
            local = exotel_call_registry.get(self.exotel_call_sid) or {}
            self.agent_id = self.agent_id or local.get("agent_id")
            self.tier = self.tier or local.get("tier")
            self.direction = str(local.get("direction") or "outbound-api")

        if self.agent_id:
            from server.call.call_lifecycle_service import call_lifecycle_service

            started = await call_lifecycle_service.start(
                agent_id=self.agent_id,
                session_id=f"pstn-{self.exotel_call_sid or self.stream_sid}",
                channel="pstn",
                direction="outbound" if "outbound" in self.direction else "inbound",
                tier=self.tier,
                caller_id=self.caller_id,
            )
            self.call_id = started["call_id"]
            self.session_id = started["session_id"]
            if self.exotel_call_sid:
                exotel_call_registry.upsert(
                    self.exotel_call_sid,
                    {"internal_call_id": self.call_id, "status": "streaming", "last_event": "stream-start"},
                )
            logger.info("[EXOTEL] stream started call_id=%s exotel=%s", self.call_id, self.exotel_call_sid)

        await self._open_stt()

    async def _open_stt(self) -> None:
        from server.routes.ws import _connect_stt_upstream

        self._stt_cm = _connect_stt_upstream(
            session_id=self.session_id,
            call_id=self.call_id,
            language_code="te-IN",
            sample_rate=16000,
        )
        self._stt = await self._stt_cm.__aenter__()
        self._stt_task = asyncio.create_task(self._stt_reader())
        self._ping_task = asyncio.create_task(self._stt_ping())

    async def _stt_ping(self) -> None:
        while not self._closed and self._stt:
            await asyncio.sleep(20)
            try:
                await self._stt.send(json.dumps({"event": "ping"}))
            except Exception:
                return

    async def _stt_reader(self) -> None:
        assert self._stt is not None
        try:
            async for raw in self._stt:
                if isinstance(raw, bytes):
                    raw = raw.decode(errors="ignore")
                msg = json.loads(raw)
                ev = msg.get("event") or msg.get("type") or ""
                if ev == "transcript.partial":
                    text = (msg.get("text") or (msg.get("data") or {}).get("text") or "").strip()
                    if text and self._agent_speaking and len(text.split()) >= 2:
                        await self._barge_in()
                elif ev == "transcript.final":
                    text = (msg.get("text") or (msg.get("data") or {}).get("text") or "").strip()
                    if text and not self._turn_busy:
                        asyncio.create_task(self._run_turn(text))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("[EXOTEL] stt reader: %s", str(e)[:200])

    async def _on_media(self, ev: dict[str, Any]) -> None:
        if not self._stt:
            return
        payload = (ev.get("media") or {}).get("payload")
        if not payload:
            return
        pcm8k = base64.b64decode(payload)
        pcm16k = pcm8k_to_pcm16k(pcm8k)
        if self.call_id:
            from server.call.audio_archive import audio_archive

            asyncio.create_task(audio_archive.append_user_pcm(self.call_id, pcm16k))
        b64 = base64.b64encode(pcm16k).decode()
        await self._stt.send(json.dumps({"event": "audio_input", "audio": b64}))

    async def _barge_in(self) -> None:
        if not self.stream_sid:
            return
        await self.ws.send_text(json.dumps({"event": "clear", "stream_sid": self.stream_sid}))
        self._agent_speaking = False

    async def _run_turn(self, text: str) -> None:
        if self._turn_busy or not self.call_id:
            return
        self._turn_busy = True
        try:
            from server.call.live_turn_orchestrator import LiveTurnOrchestrator

            orch = LiveTurnOrchestrator()
            assistant = ""
            async for chunk in orch.handle_user_turn_stream(
                transcript=text,
                session_id=self.session_id,
                call_id=self.call_id,
            ):
                if chunk.get("delta"):
                    assistant += chunk.get("delta") or ""
                elif chunk.get("done"):
                    assistant = chunk.get("text") or assistant
            if assistant.strip():
                await self._speak(assistant.strip())
        except Exception as e:
            logger.warning("[EXOTEL] turn error: %s", str(e)[:300])
        finally:
            self._turn_busy = False

    async def _speak(self, text: str) -> None:
        if not self.stream_sid or not text:
            return
        from server.config.env import get_settings
        from server.routes.ws import _connect_tts_upstream, _resolve_ws_tts_model

        model = _resolve_ws_tts_model("bulbul:v3", self.session_id, self.call_id)
        tts_cm = _connect_tts_upstream(model, session_id=self.session_id, call_id=self.call_id)
        tts = await tts_cm.__aenter__()
        try:
            ctx = None
            if self.call_id:
                from server.call.call_context import get as get_ctx

                ctx = get_ctx(self.call_id)
            stack = ctx.resolved_stack if ctx else None
            speaker = stack.tts.config.get("speaker") if stack else None
            lang = stack.language if stack else "te-IN"
            await tts.send(
                json.dumps(
                    {
                        "type": "config",
                        "data": {
                            "speaker": speaker or get_settings().sarvam_tts_speaker_te,
                            "language_code": lang,
                            "pace": 1.0,
                            "output_audio_codec": "linear16",
                            "sample_rate": 16000,
                        },
                    }
                )
            )
            await tts.send(json.dumps({"type": "text", "data": {"text": text}}))
            await tts.send(json.dumps({"type": "flush"}))

            pcm_buf = bytearray()
            async for raw in tts:
                if isinstance(raw, bytes):
                    raw = raw.decode(errors="ignore")
                obj = json.loads(raw)
                audio_b64 = None
                if isinstance(obj.get("data"), dict):
                    audio_b64 = obj["data"].get("audio")
                audio_b64 = audio_b64 or obj.get("audio")
                if audio_b64:
                    pcm_buf.extend(base64.b64decode(audio_b64))

            if pcm_buf:
                pcm8k = pcm16k_to_pcm8k(bytes(pcm_buf))
                self._agent_speaking = True
                for chunk in chunk_pcm_for_exotel(pcm8k):
                    if self.call_id:
                        from server.call.audio_archive import audio_archive

                        asyncio.create_task(audio_archive.append_agent_audio(self.call_id, pcm8k_to_pcm16k(chunk)))
                    await self.ws.send_text(
                        json.dumps(
                            {
                                "event": "media",
                                "stream_sid": self.stream_sid,
                                "media": {"payload": base64.b64encode(chunk).decode()},
                            }
                        )
                    )
                await self.ws.send_text(
                    json.dumps(
                        {
                            "event": "mark",
                            "stream_sid": self.stream_sid,
                            "mark": {"name": "turn-end"},
                        }
                    )
                )
        finally:
            try:
                await tts.close()
            except Exception:
                pass
            try:
                await tts_cm.__aexit__(None, None, None)
            except Exception:
                pass

    async def _cleanup(self, reason: str) -> None:
        if self._closed:
            return
        self._closed = True
        for task in (self._stt_task, self._ping_task):
            if task:
                task.cancel()
        if self._stt:
            try:
                await self._stt.close()
            except Exception:
                pass
        if self._stt_cm:
            try:
                await self._stt_cm.__aexit__(None, None, None)
            except Exception:
                pass
        if self.call_id:
            from server.call.call_lifecycle_service import call_lifecycle_service

            try:
                await call_lifecycle_service.end(self.call_id, reason="pstn_hangup")
            except Exception:
                pass
        if self.exotel_call_sid:
            from server.services.exotel_call_registry import exotel_call_registry

            exotel_call_registry.upsert(
                self.exotel_call_sid,
                {"status": "completed", "last_event": reason},
            )
