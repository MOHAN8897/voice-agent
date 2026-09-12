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
from server.services.pstn_voice_core import pstn_call_options
from server.services.pstn_voice_flow import create_pstn_voice_loop

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
        self._start_handled = False
        self._token_meta: dict[str, Any] = {}
        self._media_frames_in = 0
        self._media_frames_out = 0

    async def run(self, *, agent_id: str | None, tier: str | None, token_meta: dict[str, Any] | None) -> None:
        self._token_meta = dict(token_meta or {})
        self.agent_id = agent_id or self._token_meta.get("agent_id")
        self.tier = tier or self._token_meta.get("tier")
        try:
            while not self._closed:
                raw = await self.ws.receive_text()
                ev = json.loads(raw)
                event = ev.get("event") or ev.get("name") or ""
                if event == "start":
                    if self._start_handled:
                        continue
                    self._start_handled = True
                    try:
                        await self._on_start(ev)
                    except Exception:
                        self._start_handled = False
                        raise
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
        if not local.get("agent_id"):
            request_uuid = str(self._token_meta.get("request_uuid") or "")
            if request_uuid:
                local = plivo_call_registry.get(request_uuid) or local
        self.agent_id = self.agent_id or local.get("agent_id")
        self.tier = self.tier or local.get("tier")
        pstn_opts = pstn_call_options(local)
        log_pstn("stream.start", call_uuid=self.plivo_call_uuid, agent_id=self.agent_id)

        if self.agent_id:
            prewarm = None
            request_uuid = str(self._token_meta.get("request_uuid") or "")
            if self.plivo_call_uuid or request_uuid:
                from server.services.pstn_prewarm import take_prewarm_for_answer

                prewarm = await take_prewarm_for_answer(
                    "plivo",
                    self.plivo_call_uuid or "",
                    fallback_external_id=request_uuid or None,
                )
            self._prewarm_bundle = prewarm
            from server.call.call_lifecycle_service import call_lifecycle_service

            started = await call_lifecycle_service.start(
                agent_id=self.agent_id,
                session_id=f"pstn-plivo-{self.plivo_call_uuid}",
                config_session_id=pstn_opts.get("config_session_id"),
                channel="pstn",
                direction=str(local.get("direction") or "outbound"),
                tier=self.tier,
                caller_id=self.caller_id,
                stack_override=pstn_opts.get("stack_override"),
                language=str(pstn_opts.get("language") or "te-IN"),
                realtime_prewarm_key=prewarm.realtime_key if prewarm else None,
            )
            self.call_id = started["call_id"]
            self.session_id = started["session_id"]
        if self.plivo_call_uuid:
            patch = {
                "agent_id": self.agent_id,
                "tier": self.tier,
                "internal_call_id": self.call_id,
                "status": "streaming",
                "last_event": "stream-start",
            }
            if request_uuid := str(self._token_meta.get("request_uuid") or ""):
                patch["request_uuid"] = request_uuid
            plivo_call_registry.upsert(self.plivo_call_uuid, patch)

        from server.services.pstn_playback import EstimatedPlaybackTracker

        self._playback = EstimatedPlaybackTracker(frame_ms=20.0)
        self._voice = create_pstn_voice_loop(
            stack_override=pstn_opts.get("stack_override"),
            session_id=self.session_id,
            call_id=self.call_id,
            on_agent_wire=self._send_agent_wire,
            sample_rate=8000,
            tts_session_id=pstn_opts.get("tts_session_id"),
            config_session_id=pstn_opts.get("config_session_id"),
            tts_output_codec="mulaw",
            is_agent_audio_active=self._playback.is_active,
            playback=self._playback,
        )
        self._voice.set_barge_handler(self._barge_in)
        self._voice.set_hangup_handler(self._provider_hangup)
        asyncio.create_task(self._start_voice_loop())

    async def _start_voice_loop(self) -> None:
        if not self._voice:
            return
        try:
            prewarm = getattr(self, "_prewarm_bundle", None)
            await self._voice.start_call(
                play_greeting=bool(self.call_id),
                greeting_wire_frames=prewarm.greeting_wire_frames if prewarm else None,
                greeting_text=prewarm.greeting_text if prewarm else None,
            )
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
        generation_id = self._voice.current_generation_id if self._voice else None
        playback = getattr(self, "_playback", None)
        if playback is not None and not playback.is_generation_valid(generation_id):
            return
        if len(wire) == 160:
            frames = [wire]
        else:
            frames = list(pcm16_chunk_to_mulaw_frames(wire, sample_rate=8000, frame_ms=20))
        first_out = self._media_frames_out == 0
        for i, frame in enumerate(frames):
            if playback is not None and not playback.is_generation_valid(generation_id):
                return
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
            if i + 1 < len(frames):
                await asyncio.sleep(0.02)
        self._media_frames_out += len(frames)
        if first_out:
            log_pstn(
                "media.out.first",
                call_uuid=self.plivo_call_uuid,
                call_id=self.call_id,
                frames=len(frames),
            )

    async def _provider_hangup(self) -> None:
        if not self.plivo_call_uuid:
            return
        from server.services.plivo_client import PlivoClient

        try:
            await PlivoClient().hangup(self.plivo_call_uuid)
            log_pstn("hangup.provider", call_uuid=self.plivo_call_uuid, call_id=self.call_id)
        except Exception as exc:
            log_pstn("hangup.provider.failed", call_uuid=self.plivo_call_uuid, error=str(exc)[:200])

    async def _barge_in(self) -> None:
        generation_id = self._voice.current_generation_id if self._voice else None
        playback = getattr(self, "_playback", None)
        if playback is not None:
            playback.invalidate_generation(generation_id)
            drained = playback.clear()
            log_pstn(
                "PROVIDER_CLEAR",
                call_uuid=self.plivo_call_uuid,
                call_id=self.call_id,
                frames=drained,
                generation_id=generation_id,
                queue_ms=playback.queued_ms(),
            )
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
