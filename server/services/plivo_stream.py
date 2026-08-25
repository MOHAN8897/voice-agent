"""Plivo bidirectional stream session handler — Phase 5."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from server.services.audio_transcode import encode_mulaw_base64, mulaw_frame_to_pcm16, pcm16_to_mulaw

logger = logging.getLogger(__name__)


@dataclass
class PlivoStreamSession:
    stream_id: str
    call_id: str | None = None
    plivo_call_uuid: str | None = None
    caller_id: str | None = None
    agent_speaking: bool = False
    pcm_buffer: bytearray = field(default_factory=bytearray)

    def handle_start(self, payload: dict[str, Any]) -> None:
        self.stream_id = payload.get("streamId") or payload.get("stream_id") or self.stream_id
        self.plivo_call_uuid = payload.get("callUUID") or payload.get("call_uuid")
        start = payload.get("start") or {}
        self.caller_id = start.get("from") or start.get("callerId")

    def ingest_media(self, payload: dict[str, Any]) -> bytes | None:
        media = payload.get("media") or {}
        raw = media.get("payload")
        if not raw:
            return None
        import base64

        mulaw = base64.b64decode(raw)
        pcm = mulaw_frame_to_pcm16(mulaw)
        self.pcm_buffer.extend(pcm)
        return pcm

    def build_play_audio(self, pcm16: bytes, sample_rate: int = 16000) -> dict[str, Any]:
        mulaw = pcm16_to_mulaw(pcm16, sample_rate)
        self.agent_speaking = True
        return {
            "event": "playAudio",
            "media": {
                "contentType": "audio/x-mulaw",
                "sampleRate": 8000,
                "payload": encode_mulaw_base64(mulaw),
            },
        }

    def build_clear_audio(self) -> dict[str, Any]:
        self.agent_speaking = False
        return {"event": "clearAudio"}

    def drain_pcm_buffer(self) -> bytes:
        data = bytes(self.pcm_buffer)
        self.pcm_buffer.clear()
        return data


def parse_plivo_event(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return json.loads(raw)
