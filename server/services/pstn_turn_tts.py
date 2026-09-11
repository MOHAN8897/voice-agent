"""Persistent PSTN TTS session — one warm WebSocket per call, many turns, one flush each."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import TYPE_CHECKING, Any

from server.services.audio_transcode import (
    StreamingPcmResampler,
    chunk_mulaw_frames,
    chunk_pcm16_frames,
    pcm16_to_mulaw,
)
from server.services.pstn_debug import log_pstn
from server.services.pstn_voice_core import pstn_frame_bytes, pstn_wire_mode
from server.utils.logger import log_error, log_tts

if TYPE_CHECKING:
    from server.services.pstn_voice_core import PstnVoiceLoop

logger = logging.getLogger(__name__)


def _tts_config_sample_rate(merged: dict[str, Any], *, fallback: int) -> int:
    """Prefer explicit TTS output rate from config over the PSTN wire rate."""
    for key in ("speech_sample_rate", "sample_rate"):
        raw = merged.get(key)
        if raw is None or raw == "":
            continue
        try:
            rate = int(raw)
        except (TypeError, ValueError):
            continue
        if rate > 0:
            return rate
    return int(fallback)


def _sarvam_fallback_config(language: str, wire_mode: str) -> dict[str, Any] | None:
    """Use only the configured, enabled fallback; never mutate a session's stack."""
    from server.config.env import get_settings
    from server.services.dev_fallback_store import dev_fallback_store
    from server.services.dev_secrets_store import dev_secrets_store
    from server.services.tts_config import resolve_tts_config

    settings = get_settings()
    if "sarvam" not in dev_fallback_store.get_chains().get("tts", []):
        return None
    if not dev_secrets_store.effective("enable_sarvam", settings.enable_sarvam):
        return None
    if not (dev_secrets_store.effective_secret("sarvam_api_key") or settings.sarvam_api_key):
        return None
    rate = 24000 if wire_mode == "mp3" else (8000 if wire_mode == "rtp_mulaw" else 16000)
    cfg = resolve_tts_config(
        language_code=language, provider_override="sarvam",
        codec="mp3" if wire_mode == "mp3" else "linear16", sample_rate=rate,
    )
    cfg["speech_sample_rate"] = str(cfg.pop("sample_rate"))
    if wire_mode != "mp3":
        cfg.pop("output_audio_bitrate", None)
    return cfg


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
        self._pcm_resampler: StreamingPcmResampler | None = None
        self._first_chunk = True
        self._tts_audio_bytes = 0
        self._tts_ws_msgs = 0
        self._chars_sent = 0
        self._interrupted = False
        self._had_error = False
        self._bound_generation: str | None = None
        self._awaiting_audio = False
        self._collecting_frames = False
        self._collected_frames: list[bytes] = []

    @property
    def has_sent_text(self) -> bool:
        return self._chars_sent > 0

    @property
    def had_error(self) -> bool:
        return self._had_error

    @property
    def audio_emitted(self) -> bool:
        return self._tts_audio_bytes > 0

    def _stale_generation(self) -> bool:
        voice = self._voice
        bound = getattr(self, "_bound_generation", None)
        if self._interrupted:
            return True
        if voice.emission_blocked():
            return True
        if bound and voice._interrupted_generation and bound == voice._interrupted_generation:
            return True
        if bound and voice.current_generation_id and bound != voice.current_generation_id:
            return True
        return False

    async def open(
        self,
        *,
        speaker: str | None = None,
        language_code: str | None = None,
        resolved_stack: Any | None = None,
    ) -> None:
        if self._opened or self._closed:
            return
        from server.routes.ws import _connect_tts_upstream
        from server.services.tts_config import merge_pstn_tts_config

        voice = self._voice
        self._bound_generation = voice.current_generation_id
        wire_mode = pstn_wire_mode(voice.tts_output_codec, voice.sample_rate)
        self._use_mp3 = voice.tts_output_codec == "mp3"
        self._use_mulaw_wire = wire_mode == "rtp_mulaw"
        self._use_l16_wire = wire_mode == "rtp_l16"
        self._frame_bytes = pstn_frame_bytes(wire_mode, voice.sample_rate)

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
            resolved_stack=resolved_stack,
        )
        using_fallback = False
        if self._merged.get("provider") == "cartesia" and getattr(voice, "_tts_fallback_provider", None) == "sarvam":
            fallback = _sarvam_fallback_config(lang, wire_mode)
            if fallback:
                self._merged = fallback
                using_fallback = True
        # Trust TTS config rate — never assume wire rate (Cartesia μ-law path is 16k→8k).
        self._tts_rate = _tts_config_sample_rate(self._merged, fallback=voice.sample_rate)
        self._pcm_resampler = None
        self._model = str(self._merged.get("model") or "bulbul:v3")
        # Resolve the fallback connector directly: the normal connector re-resolves
        # the locked call stack and would select the failing Cartesia service again.
        from server.services.sarvam_ws import connect_tts_ws

        self._tts_cm = (
            connect_tts_ws(model=self._model) if using_fallback else
            _connect_tts_upstream(
                self._model,
                session_id=voice.tts_session_id,
                call_id=voice.call_id,
                resolved=self._merged,
            )
        )
        try:
            self._tts = await asyncio.wait_for(self._tts_cm.__aenter__(), timeout=8.0)
        except Exception as exc:
            try:
                await self._tts_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._tts_cm = None
            fallback = _sarvam_fallback_config(lang, wire_mode) if self._merged.get("provider") == "cartesia" else None
            if fallback is None:
                if isinstance(exc, asyncio.TimeoutError):
                    log_pstn("tts.connect.timeout", call_id=voice.call_id, timeout_s=8.0)
                    raise TimeoutError("TTS upstream connect timed out after 8s") from exc
                raise
            log_pstn(
                "tts.fallback", call_id=voice.call_id, failed_provider="cartesia",
                provider="sarvam", error=str(exc)[:200],
            )
            self._merged = fallback
            self._model = str(fallback["model"])
            self._tts_rate = _tts_config_sample_rate(fallback, fallback=voice.sample_rate)
            self._tts_cm = connect_tts_ws(model=self._model)
            self._tts = await asyncio.wait_for(self._tts_cm.__aenter__(), timeout=8.0)
            voice._tts_fallback_provider = "sarvam"
        self._ping_task = asyncio.create_task(self._tts_ping())

        if self._merged.get("provider") == "cartesia":
            # Cartesia returns PCM16; on 8 kHz μ-law bridges still convert to mulaw wire.
            if voice.sample_rate <= 8000 and str(voice.tts_output_codec or "").lower() in {
                "mulaw",
                "ulaw",
                "pcmu",
            }:
                self._use_mulaw_wire = True
                self._use_l16_wire = False
                self._use_mp3 = False
                self._frame_bytes = pstn_frame_bytes("rtp_mulaw", 8000)
            else:
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
        if not text or self._closed or self._interrupted or not self._tts:
            return
        if not self._opened:
            await self.open()
        voice = self._voice
        if self._stale_generation():
            return
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

    async def prepare_for_turn(self) -> None:
        """Reset per-turn state while keeping the upstream WebSocket warm."""
        if self._closed or not self._opened:
            await self.open()
        await self._prepare_for_chunk()

    async def _prepare_for_chunk(self) -> None:
        """Reset per-chunk synthesis state; keep the upstream WebSocket warm."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._flushed = False
        self._done.clear()
        self._chars_sent = 0
        self._tts_audio_bytes = 0
        self._tts_ws_msgs = 0
        self._first_chunk = True
        self._audio_buf.clear()
        self._interrupted = False
        self._had_error = False
        self._awaiting_audio = False
        self._collecting_frames = False
        self._collected_frames = []
        self._pcm_resampler = None
        self._bound_generation = self._voice.current_generation_id
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def synthesize_to_frames(self, text: str) -> list[bytes]:
        """One send_text + flush; collect wire frames without live Telnyx playout."""
        if not text or self._closed or self._stale_generation():
            return []
        if not self._opened:
            await self.open()
        await self._prepare_for_chunk()
        self._collecting_frames = True
        self._collected_frames = []
        try:
            await self.send_text(text)
            await self.finish()
            if self._stale_generation() or self._had_error:
                return []
            return list(self._collected_frames)
        finally:
            self._collecting_frames = False

    async def finish(self) -> None:
        if self._closed or self._flushed or not self._tts:
            return
        self._flushed = True
        self._awaiting_audio = True
        await self._tts.send(json.dumps({"type": "flush"}))
        try:
            await asyncio.wait_for(self._done.wait(), timeout=12.0)
        except asyncio.TimeoutError:
            log_pstn("tts.finish.timeout", call_id=self._voice.call_id)
            # Treat silent hang as an error so the turn can speak a fallback (6.5).
            if self._tts_audio_bytes <= 0:
                self._had_error = True
            self._done.set()
        finally:
            self._awaiting_audio = False

    async def end_turn(self) -> None:
        """Finish a turn without tearing down the upstream socket."""
        voice = self._voice
        self._awaiting_audio = False
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
        await self.end_turn()

    async def interrupt(self) -> None:
        self._interrupted = True
        self._audio_buf.clear()
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
        self._awaiting_audio = True
        try:
            assert self._tts is not None
            async for raw in self._tts:
                self._awaiting_audio = False
                if self._closed or self._interrupted or voice._closed or self._stale_generation():
                    break
                if isinstance(raw, bytes):
                    raw = raw.decode(errors="ignore")
                obj = json.loads(raw)
                msg_type = obj.get("type") or obj.get("event") or ""
                self._tts_ws_msgs += 1
                if msg_type == "error":
                    log_error("PSTN TTS error", call_id=voice.call_id, detail=str(obj)[:300])
                    log_pstn("tts.error", call_id=voice.call_id, detail=str(obj)[:200])
                    self._had_error = True
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
                            new_rate = int(rate_val)
                            if new_rate > 0 and new_rate != self._tts_rate:
                                self._tts_rate = new_rate
                                self._pcm_resampler = None
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
                if self._stale_generation():
                    break
                audio = base64.b64decode(audio_b64)
                self._tts_audio_bytes += len(audio)
                await self._emit_audio_chunk(audio)
                self._awaiting_audio = True
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._had_error = True
            log_pstn("tts.reader.failed", call_id=voice.call_id, error=str(exc)[:200])
            logger.warning("[PSTN] turn TTS reader: %s", str(exc)[:200])
        finally:
            self._awaiting_audio = False
            # Interrupt invariant: never flush tail after barge/cancel / stale generation.
            if not self._stale_generation():
                await self._flush_audio_tail()
            else:
                self._audio_buf.clear()
            self._done.set()

    def _ensure_resampler(self, from_rate: int, to_rate: int) -> StreamingPcmResampler:
        if (
            self._pcm_resampler is None
            or self._pcm_resampler.from_rate != from_rate
            or self._pcm_resampler.to_rate != to_rate
        ):
            self._pcm_resampler = StreamingPcmResampler(from_rate, to_rate)
        return self._pcm_resampler

    async def _emit_wire_frame(self, frame: bytes) -> None:
        if self._collecting_frames:
            self._collected_frames.append(frame)
            return
        await self._voice._emit_agent_wire(frame)

    async def _emit_audio_chunk(self, audio: bytes) -> None:
        voice = self._voice
        if self._stale_generation():
            return
        use_mulaw_wire = self._use_mulaw_wire
        use_mp3 = self._use_mp3
        tts_rate = self._tts_rate
        first_chunk = self._first_chunk

        if use_mulaw_wire:
            # Stateful 16k→8k (or whatever TTS rate → 8k) then μ-law — avoids chipmunk + clicks.
            resampler = self._ensure_resampler(tts_rate, 8000)
            pcm8k = resampler.feed(audio)
            if not pcm8k:
                return
            audio = pcm16_to_mulaw(pcm8k, sample_rate=8000)
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
            if self._stale_generation():
                return
            await self._emit_wire_frame(audio)
            return
        if not use_mulaw_wire and not use_mp3 and tts_rate != voice.sample_rate:
            resampler = self._ensure_resampler(tts_rate, voice.sample_rate)
            audio = resampler.feed(audio)
            if not audio:
                return
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
            if self._stale_generation():
                self._audio_buf.clear()
                return
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
                    source_tts_rate=self._tts_rate,
                )
                log_tts("PSTN first audio", call_id=voice.call_id, bytes=len(chunk))
                self._first_chunk = False
            await self._emit_wire_frame(chunk)

    async def _flush_audio_tail(self) -> None:
        if self._stale_generation():
            self._audio_buf.clear()
            self._pcm_resampler = None
            return
        voice = self._voice
        # Drain residual resampler bytes before framing the tail.
        if self._pcm_resampler is not None and not self._use_mp3:
            leftover = self._pcm_resampler.flush()
            if leftover:
                if self._use_mulaw_wire:
                    leftover = pcm16_to_mulaw(leftover, sample_rate=8000)
                self._audio_buf.extend(leftover)
            self._pcm_resampler = None
        if not self._audio_buf:
            return
        tail = bytes(self._audio_buf)
        self._audio_buf.clear()
        if self._use_mulaw_wire:
            for frame in chunk_mulaw_frames(tail, sample_rate=8000):
                if self._stale_generation():
                    return
                await self._emit_wire_frame(frame)
        else:
            for frame in chunk_pcm16_frames(tail, sample_rate=voice.sample_rate):
                if self._stale_generation():
                    return
                await self._emit_wire_frame(frame)
