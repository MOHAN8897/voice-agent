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
from server.services.pstn_voice_core import pstn_call_options
from server.services.pstn_voice_flow import create_pstn_voice_loop

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
        self._start_handled = False
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
                    if self._start_handled:
                        continue
                    self._start_handled = True
                    try:
                        await self._on_start(ev)
                    except Exception:
                        self._start_handled = False
                        raise
                elif name == "media":
                    await self._on_media(ev)
                elif name == "mark":
                    # Playback ack from Exotel (turn-end after TTS completes).
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
            prewarm = None
            if self.exotel_call_sid:
                from server.services.pstn_prewarm import take_prewarm_for_answer

                prewarm = await take_prewarm_for_answer("exotel", self.exotel_call_sid)
            self._prewarm_bundle = prewarm
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
                realtime_prewarm_key=prewarm.realtime_key if prewarm else None,
            )
            self.call_id = started["call_id"]
            self.session_id = started["session_id"]
            if self.exotel_call_sid:
                exotel_call_registry.upsert(
                    self.exotel_call_sid,
                    {"internal_call_id": self.call_id, "status": "streaming", "last_event": "stream-start"},
                )
            logger.info("[EXOTEL] stream started call_id=%s exotel=%s", self.call_id, self.exotel_call_sid)

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
        self._voice.set_turn_audio_done_handler(self._mark_turn_end)
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
            from server.services.pstn_prewarm import record_bundle_greeting_usage

            await record_bundle_greeting_usage(self.call_id, prewarm)
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
        generation_id = self._voice.current_generation_id if self._voice else None
        playback = getattr(self, "_playback", None)
        if playback is not None and not playback.is_generation_valid(generation_id):
            return
        chunks = list(chunk_pcm_for_exotel(pcm8k))
        first_out = self._media_frames_out == 0
        for i, chunk in enumerate(chunks):
            if playback is not None and not playback.is_generation_valid(generation_id):
                return
            await self.ws.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "stream_sid": self.stream_sid,
                        "media": {"payload": base64.b64encode(chunk).decode()},
                    }
                )
            )
            # Pace ~realtime: 3200 B PCM @ 8 kHz ≈ 200 ms; smaller chunks use proportion.
            if i + 1 < len(chunks):
                await asyncio.sleep(max(0.02, len(chunk) / (8000 * 2)))
        self._media_frames_out += len(chunks)
        if first_out:
            log_pstn(
                "media.out.first",
                call_sid=self.exotel_call_sid,
                call_id=self.call_id,
                frames=len(chunks),
            )

    async def _mark_turn_end(self) -> None:
        """One Exotel mark per TTS turn end (not per wire frame)."""
        if not self.stream_sid or self._closed:
            return
        try:
            await self.ws.send_text(
                json.dumps(
                    {
                        "event": "mark",
                        "stream_sid": self.stream_sid,
                        "mark": {"name": "turn-end"},
                    }
                )
            )
        except Exception as exc:
            log_pstn("mark.failed", call_sid=self.exotel_call_sid, error=str(exc)[:120])

    async def _provider_hangup(self) -> None:
        if not self.exotel_call_sid:
            return
        from server.services.exotel_client import ExotelClient

        try:
            await ExotelClient().hangup(self.exotel_call_sid)
            log_pstn("hangup.provider", call_sid=self.exotel_call_sid, call_id=self.call_id)
        except Exception as exc:
            log_pstn("hangup.provider.failed", call_sid=self.exotel_call_sid, error=str(exc)[:200])

    async def _barge_in(self) -> None:
        generation_id = self._voice.current_generation_id if self._voice else None
        playback = getattr(self, "_playback", None)
        if playback is not None:
            playback.invalidate_generation(generation_id)
            drained = playback.clear()
            log_pstn(
                "PROVIDER_CLEAR",
                call_sid=self.exotel_call_sid,
                call_id=self.call_id,
                frames=drained,
                generation_id=generation_id,
                queue_ms=playback.queued_ms(),
            )
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
