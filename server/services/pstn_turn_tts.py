"""Persistent PSTN TTS session — one WebSocket per turn, many text messages, one flush."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import TYPE_CHECKING, Any

from server.services.audio_transcode import chunk_mulaw_frames, chunk_pcm16_frames
from server.services.pstn_debug import log_pstn
from server.services.pstn_voice_core import pstn_frame_bytes, pstn_wire_mode
from server.utils.logger import log_error, log_tts

if TYPE_CHECKING:
    from server.services.pstn_voice_core import PstnVoiceLoop

logger = logging.getLogger(__name__)


class PstnTurnTtsSession:
    """One upstream TTS socket per PSTN reply; mirrors browser StreamingTtsClient."""

    def __init__(self, voice: PstnVoiceLoop) -> None:
        self._voice = voice
        self._tts = None
        self._tts_cm = None
        self._ping_task: asyncio.Task | None = None
        self._reader_task: asyncio.Task | None = None
        self._opened = False
        self._closed = False
        self._flushed = False
        self._done = asyncio.Event()
        self._merged: dict[str, Any] = {}
        self._model = ""
        self._use_mp3 = False
        self._use_mulaw_wire = False
        self._use_l16_wire = False
        self._frame_bytes = 0
        self._audio_buf = bytearray()
        self._tts_rate = voice.sample_rate
        self._first_chunk = True
        self._tts_audio_bytes = 0
        self._tts_ws_msgs = 0
        self._chars_sent = 0

    @property
    def has_sent_text(self) -> bool:
        return self._chars_sent > 0

    async def open(
        self,
        *,
        speaker: str | None = None,
        language_code: str | None = None,
    ) -> None:
        if self._opened or self._closed:
            return
        from server.routes.ws import _connect_tts_upstream
        from server.services.tts_config import merge_pstn_tts_config

        voice = self._voice
        wire_mode = pstn_wire_mode(voice.tts_output_codec, voice.sample_rate)
        self._use_mp3 = voice.tts_output_codec == "mp3"
        self._use_mulaw_wire = wire_mode == "rtp_mulaw"
        self._use_l16_wire = wire_mode == "rtp_l16"
        self._frame_bytes = pstn_frame_bytes(wire_mode, voice.sample_rate)
        self._tts_rate = voice.sample_rate

        lang = language_code or voice._resolve_language()
        client_data: dict[str, Any] = {"language_code": lang}
        if speaker:
            client_data["speaker"] = speaker
        self._merged = merge_pstn_tts_config(
            voice.tts_session_id,
            client_data,
            call_id=voice.call_id,
            ws_model=None,
            wire_mode=wire_mode,
        )
        self._model = str(self._merged.get("model") or "bulbul:v3")
        self._tts_cm = _connect_tts_upstream(self._model, session_id=voice.tts_session_id, call_id=voice.call_id)
        self._tts = await self._tts_cm.__aenter__()
        self._ping_task = asyncio.create_task(self._tts_ping())

        if self._merged.get("provider") == "cartesia":
            self._use_mulaw_wire = False
            self._use_l16_wire = True
            self._use_mp3 = False
            self._frame_bytes = pstn_frame_bytes("rtp_l16", voice.sample_rate)
        if self._use_mp3:
            voice.current_output_codec = "MP3"
        elif self._use_l16_wire:
            voice.current_output_codec = "L16"
        elif self._use_mulaw_wire:
            voice.current_output_codec = "PCMU"
        else:
            voice.current_output_codec = "L16"

        log_tts(
            "PSTN turn TTS config",
            call_id=voice.call_id,
            speaker=self._merged.get("speaker"),
            pace=self._merged.get("pace"),
            model=self._model,
            codec=self._merged.get("output_audio_codec"),
            speech_sample_rate=self._merged.get("speech_sample_rate"),
        )
        await self._tts.send(
            json.dumps(
                {
                    "type": "config",
                    "data": {
                        k: v
                        for k, v in self._merged.items()
                        if k not in {"provider", "model"}
                    },
                }
            )
        )
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._opened = True

    async def send_text(self, text: str) -> None:
        if not text or self._closed or not self._tts:
            return
        if not self._opened:
            await self.open()
        voice = self._voice
        if self._chars_sent == 0:
            log_pstn(
                "tts.speak.start",
                call_id=voice.call_id,
                turn_id=voice.current_turn_id,
                generation_id=voice.current_generation_id,
                chars=len(text),
                speaker=self._merged.get("speaker"),
                pace=self._merged.get("pace"),
                codec=self._merged.get("output_audio_codec"),
                speech_sample_rate=self._merged.get("speech_sample_rate"),
                provider=self._merged.get("provider"),
                text=text[:120].encode("ascii", "replace").decode("ascii"),
            )
            if voice.call_id:
                from server.services.pstn_media_flow import pstn_media_flow

                pstn_media_flow.emit(
                    voice.call_id,
                    "tts_started",
                    "outbound",
                    turn_id=voice.current_turn_id,
                    generation_id=voice.current_generation_id,
                    codec=voice.current_output_codec,
                    sample_rate=voice.sample_rate,
                    channels=1,
                    status="processing",
                    detail=text[:200],
                )
        await self._tts.send(json.dumps({"type": "text", "data": {"text": text}}))
        self._chars_sent += len(text)

    async def finish(self) -> None:
        if self._closed or self._flushed or not self._tts:
            return
        self._flushed = True
        await self._tts.send(json.dumps({"type": "flush"}))
        try:
            await asyncio.wait_for(self._done.wait(), timeout=120.0)
        except asyncio.TimeoutError:
            log_pstn("tts.finish.timeout", call_id=self._voice.call_id)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._done.set()
        if self._ping_task:
            self._ping_task.cancel()
        if self._reader_task and self._reader_task is not asyncio.current_task():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._tts:
            try:
                await self._tts.close()
            except Exception:
                pass
        if self._tts_cm:
            try:
                await self._tts_cm.__aexit__(None, None, None)
            except Exception:
                pass
        voice = self._voice
        log_pstn(
            "tts.speak.done",
            call_id=voice.call_id,
            turn_id=voice.current_turn_id,
            generation_id=voice.current_generation_id,
            chars=self._chars_sent,
            tts_audio_bytes=self._tts_audio_bytes,
            wire_frames=voice._wire_frames_out,
            tts_ws_msgs=self._tts_ws_msgs,
        )
        voice.current_output_codec = "L16" if voice.sample_rate >= 16000 else "PCMU"

    async def interrupt(self) -> None:
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        await self.close()

    async def _tts_ping(self) -> None:
        while not self._closed and self._tts:
            await asyncio.sleep(20)
            try:
                await self._tts.send(json.dumps({"type": "ping"}))
            except Exception:
                return

    def _tts_is_completion(self, msg_type: str, data: Any) -> bool:
        if msg_type in ("end_of_stream", "done", "complete", "completion"):
            return True
        if msg_type != "event":
            return False
        if not isinstance(data, dict):
            return False
        event_type = str(data.get("event_type") or data.get("type") or "")
        return event_type in ("final", "completion", "end", "done")

    async def _reader_loop(self) -> None:
        voice = self._voice
        try:
            assert self._tts is not None
            async for raw in self._tts:
                if self._closed or voice._closed:
                    break
                if isinstance(raw, bytes):
                    raw = raw.decode(errors="ignore")
                obj = json.loads(raw)
                msg_type = obj.get("type") or obj.get("event") or ""
                self._tts_ws_msgs += 1
                if msg_type == "error":
                    log_error("PSTN TTS error", call_id=voice.call_id, detail=str(obj)[:300])
                    log_pstn("tts.error", call_id=voice.call_id, detail=str(obj)[:200])
                    break
                data = obj.get("data")
                if self._tts_is_completion(msg_type, data):
                    log_pstn("tts.complete", call_id=voice.call_id, msg_type=msg_type)
                    break
                audio_b64 = None
                if isinstance(data, dict):
                    audio_b64 = data.get("audio")
                    rate_val = data.get("speech_sample_rate") or data.get("sample_rate")
                    if rate_val:
                        try:
                            self._tts_rate = int(rate_val)
                        except (TypeError, ValueError):
                            pass
                audio_b64 = audio_b64 or obj.get("audio")
                if msg_type == "chunk" and isinstance(data, str):
                    audio_b64 = data
                if not audio_b64:
                    if self._tts_ws_msgs <= 3:
                        log_pstn(
                            "tts.ws.msg",
                            call_id=voice.call_id,
                            msg_type=msg_type,
                            keys=list(obj.keys())[:8],
                        )
                    continue
                audio = base64.b64decode(audio_b64)
                self._tts_audio_bytes += len(audio)
                await self._emit_audio_chunk(audio)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log_pstn("tts.reader.failed", call_id=voice.call_id, error=str(exc)[:200])
            logger.warning("[PSTN] turn TTS reader: %s", str(exc)[:200])
        finally:
            await self._flush_audio_tail()
            self._done.set()

    async def _emit_audio_chunk(self, audio: bytes) -> None:
        voice = self._voice
        use_mulaw_wire = self._use_mulaw_wire
        use_mp3 = self._use_mp3
        tts_rate = self._tts_rate
        first_chunk = self._first_chunk

        if use_mulaw_wire:
            from server.services.audio_transcode import pcm16_to_mulaw_8k

            audio = pcm16_to_mulaw_8k(audio, source_rate=tts_rate)
            tts_rate = 8000
        if use_mp3:
            if first_chunk and voice.call_id:
                from server.services.pstn_media_flow import pstn_media_flow

                pstn_media_flow.emit(
                    voice.call_id,
                    "tts_audio",
                    "outbound",
                    turn_id=voice.current_turn_id,
                    generation_id=voice.current_generation_id,
                    codec="MP3",
                    sample_rate=tts_rate,
                    channels=1,
                    bytes=len(audio),
                    status="healthy",
                )
                log_pstn(
                    "tts.first_audio",
                    timer_key=voice.call_id,
                    call_id=voice.call_id,
                    bytes=len(audio),
                    codec="mp3",
                    tts_rate=tts_rate,
                )
                self._first_chunk = False
            await voice._emit_agent_wire(audio)
            return
        if not use_mulaw_wire and not use_mp3 and tts_rate != voice.sample_rate:
            from server.services.audio_transcode import pcm_resample

            audio = pcm_resample(audio, tts_rate, voice.sample_rate)
        self._audio_buf.extend(audio)
        if first_chunk and voice.call_id:
            from server.services.pstn_media_flow import pstn_media_flow

            pstn_media_flow.emit(
                voice.call_id,
                "tts_audio",
                "outbound",
                turn_id=voice.current_turn_id,
                generation_id=voice.current_generation_id,
                codec=voice.current_output_codec,
                sample_rate=voice.sample_rate,
                channels=1,
                bytes=len(audio),
                duration_ms=len(audio) * 1000 / (voice.sample_rate * 2),
                status="healthy",
            )
            self._first_chunk = False
        while len(self._audio_buf) >= self._frame_bytes:
            chunk = bytes(self._audio_buf[: self._frame_bytes])
            del self._audio_buf[: self._frame_bytes]
            if self._first_chunk:
                log_pstn(
                    "tts.first_audio",
                    timer_key=voice.call_id,
                    call_id=voice.call_id,
                    bytes=len(chunk),
                    codec="mulaw" if use_mulaw_wire else "pcm16",
                    tts_rate=tts_rate,
                )
                log_tts("PSTN first audio", call_id=voice.call_id, bytes=len(chunk))
                self._first_chunk = False
            await voice._emit_agent_wire(chunk)

    async def _flush_audio_tail(self) -> None:
        if not self._audio_buf:
            return
        voice = self._voice
        tail = bytes(self._audio_buf)
        self._audio_buf.clear()
        if self._use_mulaw_wire:
            for frame in chunk_mulaw_frames(tail, sample_rate=8000):
                await voice._emit_agent_wire(frame)
        else:
            for frame in chunk_pcm16_frames(tail, sample_rate=voice.sample_rate):
                await voice._emit_agent_wire(frame)
