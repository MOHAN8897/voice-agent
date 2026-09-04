"""Plivo bidirectional Stream bridge — μ-law 8kHz ↔ STT/Brain/TTS."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from fastapi import WebSocket

from server.services.audio_transcode import encode_mulaw_base64, mulaw_to_pcm16, pcm16_chunk_to_mulaw_frames
from server.services.pstn_debug import log_pstn, log_pstn_summary
from server.services.pstn_voice_core import PstnVoiceLoop, pstn_call_options

logger = logging.getLogger(__name__)


class PlivoPstnBridge:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.stream_id: str | None = None
        self.plivo_call_uuid: str | None = None
        self.call_id: str | None = None
        self.agent_id: str | None = None
        self.tier: str | None = None
        self.session_id: str = "pstn"
        self.caller_id: str | None = None
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
                event = ev.get("event") or ev.get("name") or ""
                if event == "start":
                    await self._on_start(ev)
                elif event == "media":
                    await self._on_media(ev)
                elif event == "stop" or event == "clearedAudio":
                    if event == "stop":
                        break
        finally:
            await self._cleanup("stop")

    async def _on_start(self, ev: dict[str, Any]) -> None:
        start = ev.get("start") or ev
        self.stream_id = start.get("streamId") or start.get("stream_id")
        self.plivo_call_uuid = start.get("callId") or start.get("call_uuid")
        self.caller_id = start.get("from")

        from server.services.plivo_client import plivo_call_registry

        local = plivo_call_registry.get(self.plivo_call_uuid or "") or {}
        # Outbound may register under request_uuid before callId is known.
        if not local.get("agent_id"):
            for row in plivo_call_registry.list_recent(30):
                if row.get("to") and row.get("agent_id") and not row.get("internal_call_id"):
                    local = row
                    break
        self.agent_id = self.agent_id or local.get("agent_id")
        self.tier = self.tier or local.get("tier")
        pstn_opts = pstn_call_options(local)
        log_pstn("stream.start", call_uuid=self.plivo_call_uuid, agent_id=self.agent_id)

        if self.agent_id:
            from server.call.call_lifecycle_service import call_lifecycle_service

            started = await call_lifecycle_service.start(
                agent_id=self.agent_id,
                session_id=f"pstn-plivo-{self.plivo_call_uuid}",
                channel="pstn",
                direction=str(local.get("direction") or "outbound"),
                tier=self.tier,
                caller_id=self.caller_id,
                stack_override=pstn_opts.get("stack_override"),
                language=str(pstn_opts.get("language") or "te-IN"),
            )
            self.call_id = started["call_id"]
            self.session_id = started["session_id"]
            if self.plivo_call_uuid:
                plivo_call_registry.upsert(
                    self.plivo_call_uuid,
                    {
                        "agent_id": self.agent_id,
                        "tier": self.tier,
                        "internal_call_id": self.call_id,
                        "status": "streaming",
                        "last_event": "stream-start",
                    },
                )

        self._voice = PstnVoiceLoop(
            session_id=self.session_id,
            call_id=self.call_id,
            on_agent_wire=self._send_agent_wire,
            sample_rate=8000,
            tts_session_id=pstn_opts.get("tts_session_id"),
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
            logger.exception("[PLIVO] voice loop failed uuid=%s: %s", self.plivo_call_uuid, exc)

    async def _on_media(self, ev: dict[str, Any]) -> None:
        if not self._voice:
            return
        media = ev.get("media") or {}
        payload = media.get("payload") or media.get("chunk")
        if not payload:
            return
        mulaw = base64.b64decode(payload)
        pcm8k = mulaw_to_pcm16(mulaw, target_rate=8000)
        self._media_frames_in += 1
        if self._media_frames_in == 1:
            log_pstn("media.in.first", call_uuid=self.plivo_call_uuid, call_id=self.call_id, bytes=len(pcm8k))
        await self._voice.feed_user_pcm16(pcm8k)

    async def _send_agent_wire(self, wire: bytes) -> None:
        if len(wire) == 160:
            frames = [wire]
        else:
            frames = list(pcm16_chunk_to_mulaw_frames(wire, sample_rate=8000, frame_ms=20))
        first_out = self._media_frames_out == 0
        for frame in frames:
            await self.ws.send_text(
                json.dumps(
                    {
                        "event": "playAudio",
                        "media": {
                            "contentType": "audio/x-mulaw;rate=8000",
                            "payload": encode_mulaw_base64(frame),
                        },
                    }
                )
            )
        self._media_frames_out += len(frames)
        if first_out:
            log_pstn(
                "media.out.first",
                call_uuid=self.plivo_call_uuid,
                call_id=self.call_id,
                frames=len(frames),
            )

    async def _barge_in(self) -> None:
        await self.ws.send_text(json.dumps({"event": "clearAudio"}))

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
        if self.plivo_call_uuid:
            from server.services.plivo_client import plivo_call_registry

            plivo_call_registry.upsert(
                self.plivo_call_uuid,
                {
                    "status": "completed",
                    "last_event": reason,
                    "media_frames_in": self._media_frames_in,
                    "media_frames_out": self._media_frames_out,
                    "bidirectional_ok": self._media_frames_in > 0 and self._media_frames_out > 0,
                },
            )
            log_pstn_summary(
                provider="plivo",
                external_id=self.plivo_call_uuid,
                call_id=self.call_id,
                media_in=self._media_frames_in,
                media_out=self._media_frames_out,
                reason=reason,
            )
