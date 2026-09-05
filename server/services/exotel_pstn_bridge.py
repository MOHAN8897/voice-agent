"""Exotel AgentStream bidirectional bridge — PSTN audio ↔ STT/Brain/TTS."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from fastapi import WebSocket

from server.services.audio_transcode import chunk_pcm_for_exotel
from server.services.pstn_debug import log_pstn, log_pstn_summary
from server.services.pstn_voice_core import PstnVoiceLoop, pstn_call_options

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
        self._voice: PstnVoiceLoop | None = None
        self._closed = False
        self._media_frames_in = 0
        self._media_frames_out = 0

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
                        pass
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

        local: dict[str, Any] = {}
        if self.exotel_call_sid:
            local = exotel_call_registry.get(self.exotel_call_sid) or {}
            self.agent_id = self.agent_id or local.get("agent_id")
            self.tier = self.tier or local.get("tier")
            self.direction = str(local.get("direction") or "outbound-api")
        pstn_opts = pstn_call_options(local)
        log_pstn("stream.start", call_sid=self.exotel_call_sid, agent_id=self.agent_id)

        if self.agent_id:
            from server.call.call_lifecycle_service import call_lifecycle_service

            started = await call_lifecycle_service.start(
                agent_id=self.agent_id,
                session_id=f"pstn-{self.exotel_call_sid or self.stream_sid}",
                config_session_id=pstn_opts.get("config_session_id"),
                channel="pstn",
                direction="outbound" if "outbound" in self.direction else "inbound",
                tier=self.tier,
                caller_id=self.caller_id,
                stack_override=pstn_opts.get("stack_override"),
                language=str(pstn_opts.get("language") or "te-IN"),
            )
            self.call_id = started["call_id"]
            self.session_id = started["session_id"]
            if self.exotel_call_sid:
                exotel_call_registry.upsert(
                    self.exotel_call_sid,
                    {"internal_call_id": self.call_id, "status": "streaming", "last_event": "stream-start"},
                )
            logger.info("[EXOTEL] stream started call_id=%s exotel=%s", self.call_id, self.exotel_call_sid)

        self._voice = PstnVoiceLoop(
            session_id=self.session_id,
            call_id=self.call_id,
            on_agent_wire=self._send_agent_wire,
            sample_rate=8000,
            tts_session_id=pstn_opts.get("tts_session_id"),
            config_session_id=pstn_opts.get("config_session_id"),
            tts_output_codec="mulaw",
        )
        self._voice.set_barge_handler(self._barge_in)
        asyncio.create_task(self._start_voice_loop())

    async def _start_voice_loop(self) -> None:
        if not self._voice:
            return
        try:
            await self._voice.start_call(play_greeting=bool(self.call_id))
        except Exception as exc:
            logger.exception("[EXOTEL] voice loop failed sid=%s: %s", self.exotel_call_sid, exc)

    async def _on_media(self, ev: dict[str, Any]) -> None:
        if not self._voice:
            return
        payload = (ev.get("media") or {}).get("payload")
        if not payload:
            return
        pcm8k = base64.b64decode(payload)
        self._media_frames_in += 1
        if self._media_frames_in == 1:
            log_pstn("media.in.first", call_sid=self.exotel_call_sid, call_id=self.call_id, bytes=len(pcm8k))
        await self._voice.feed_user_pcm16(pcm8k)

    async def _send_agent_wire(self, wire: bytes) -> None:
        if not self.stream_sid or not wire:
            return
        from server.services.audio_transcode import mulaw_to_pcm16, pcm16_to_mulaw

        if len(wire) == 160:
            pcm8k = mulaw_to_pcm16(wire, target_rate=8000)
        else:
            pcm8k = wire
        chunks = list(chunk_pcm_for_exotel(pcm8k))
        first_out = self._media_frames_out == 0
        for chunk in chunks:
            await self.ws.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "stream_sid": self.stream_sid,
                        "media": {"payload": base64.b64encode(chunk).decode()},
                    }
                )
            )
        self._media_frames_out += len(chunks)
        if first_out:
            log_pstn(
                "media.out.first",
                call_sid=self.exotel_call_sid,
                call_id=self.call_id,
                frames=len(chunks),
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

    async def _barge_in(self) -> None:
        if not self.stream_sid:
            return
        await self.ws.send_text(json.dumps({"event": "clear", "stream_sid": self.stream_sid}))

    async def _cleanup(self, reason: str) -> None:
        if self._closed:
            return
        self._closed = True
        if self._voice:
            await self._voice.close()
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
                {
                    "status": "completed",
                    "last_event": reason,
                    "media_frames_in": self._media_frames_in,
                    "media_frames_out": self._media_frames_out,
                    "bidirectional_ok": self._media_frames_in > 0 and self._media_frames_out > 0,
                },
            )
            log_pstn_summary(
                provider="exotel",
                external_id=self.exotel_call_sid,
                call_id=self.call_id,
                media_in=self._media_frames_in,
                media_out=self._media_frames_out,
                reason=reason,
            )
