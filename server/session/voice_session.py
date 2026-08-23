"""
Voice Session Controller — server/session/voice_session.py
Owns state machine IDLE→LISTENING→PROCESSING_STT→THINKING→GENERATING_TTS→PLAYING→IDLE
Exposes orchestrated voice turn with latency measurement and barge-in hooks (Phase 5).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Optional

from server.services.openai_brain_service import generate_response
from server.services.sarvam_stt_service import transcribe
from server.services.sarvam_tts_service import synthesize
from server.services.tts_config import resolve_tts_config
from server.session.session_state import SessionState
from server.utils.errors import AppError
from server.utils.logger import log_perf, log_voice
from server.utils.metrics import metrics


@dataclass
class TurnResult:
    transcript: str
    language_code: str
    brain_text: str
    audio_bytes: bytes | None = None
    language_context: dict | None = None
    usage: dict | None = None
    stt_ms: int = 0
    brain_ms: int = 0
    tts_ms: int = 0
    e2e_ms: int = 0
    request_ids: dict = field(default_factory=dict)
    state: SessionState = SessionState.IDLE
    error: str | None = None


class VoiceSessionController:
    """
    Orchestrates: audio_bytes (wav/webm) → STT → Brain → TTS
    Used by POST /api/voice/turn (Phase 3 end-to-end) and by future WS handler.
    """

    def __init__(self):
        self._abort = False

    def abort(self):
        self._abort = True

    def reset(self):
        self._abort = False

    async def run_turn(
        self,
        *,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
        language_code: str = "te-IN",
        stt_mode: str = "transcribe",
        stt_model: str | None = None,
        session_id: str = "default",
        brain_prompt: str | None = None,
        user_instructions: str | None = None,
        business_instructions: str | None = None,
        tts_speaker: Optional[str] = None,
        tts_model: str | None = None,
        tts_temperature: float | None = None,
        openai_model: str | None = None,
        openai_temperature: float | None = None,
        openai_reasoning_effort: str | None = None,
        openai_max_tokens: int | None = None,
        synthesize_audio: bool = True,
        on_state: Optional[Callable[[SessionState], None]] = None,
    ) -> TurnResult:
        t0 = time.perf_counter()
        result = TurnResult(transcript="", language_code=language_code, brain_text="")

        def emit(state: SessionState):
            result.state = state
            if on_state:
                try:
                    on_state(state)
                except Exception:
                    pass
            log_voice("State change", state=state.value, session=session_id)

        try:
            emit(SessionState.PROCESSING_STT)
            t_stt0 = time.perf_counter()
            stt_res = await transcribe(
                audio_bytes=audio_bytes,
                filename=filename,
                content_type=content_type,
                language_code=language_code,
                mode=stt_mode,
                model=stt_model,
            )
            result.stt_ms = int((time.perf_counter() - t_stt0) * 1000)
            result.transcript = stt_res["transcript"]
            result.language_code = stt_res["language_code"]
            result.request_ids["stt"] = stt_res.get("request_id")

            if not result.transcript:
                result.error = "empty_transcript"
                emit(SessionState.IDLE)
                result.e2e_ms = int((time.perf_counter() - t0) * 1000)
                return result

            if self._abort:
                emit(SessionState.INTERRUPTED)
                return result

            emit(SessionState.THINKING)
            t_brain0 = time.perf_counter()
            brain_res = await generate_response(
                transcript=result.transcript,
                language_code=result.language_code,
                session_id=session_id,
                brain_prompt=brain_prompt,
                user_instructions=user_instructions,
                business_instructions=business_instructions,
                openai_model=openai_model,
                temperature=openai_temperature,
                reasoning_effort=openai_reasoning_effort,
                max_output_tokens=openai_max_tokens,
            )
            result.brain_ms = int((time.perf_counter() - t_brain0) * 1000)
            result.brain_text = brain_res["text"]
            result.language_context = brain_res.get("language_context")
            result.usage = brain_res.get("usage")
            result.request_ids["brain"] = brain_res.get("request_id")

            if self._abort:
                emit(SessionState.INTERRUPTED)
                return result

            if synthesize_audio and result.brain_text:
                emit(SessionState.GENERATING_TTS)
                t_tts0 = time.perf_counter()
                resolved_lang = (result.language_context or {}).get("responseLanguage", "te-IN")
                tts_cfg = resolve_tts_config(
                    session_id,
                    language_code=resolved_lang,
                    speaker=tts_speaker,
                    model=tts_model,
                    temperature=tts_temperature,
                )
                tts_res = await synthesize(
                    text=result.brain_text,
                    language_code=resolved_lang,
                    speaker=tts_cfg["speaker"],
                    model=tts_cfg["model"],
                    pace=tts_cfg["pace"],
                    temperature=tts_cfg.get("temperature"),
                    session_id=session_id,
                )
                result.tts_ms = int((time.perf_counter() - t_tts0) * 1000)
                result.audio_bytes = tts_res["audio_bytes"]
                result.request_ids["tts"] = tts_res.get("request_id")
                emit(SessionState.PLAYING)
            else:
                emit(SessionState.IDLE)

            result.e2e_ms = int((time.perf_counter() - t0) * 1000)
            log_perf(
                "voice_turn",
                sttMs=result.stt_ms,
                brainMs=result.brain_ms,
                ttsMs=result.tts_ms,
                e2eMs=result.e2e_ms,
                transcriptChars=len(result.transcript),
                responseChars=len(result.brain_text),
                audioBytes=len(result.audio_bytes or b""),
                session=session_id,
            )
            # Record metrics (industry standard: p50/p95 tracking)
            try:
                metrics.record_turn(result.stt_ms, result.brain_ms, result.tts_ms, result.e2e_ms)
            except Exception:
                pass
            # Caller handles PLAYING→IDLE after playback; we leave in PLAYING so UI can show
            return result

        except Exception as e:
            result.error = str(e)[:500]
            emit(SessionState.ERROR)
            result.e2e_ms = int((time.perf_counter() - t0) * 1000)
            # Record error for metrics
            try:
                provider = "voice_turn"
                if isinstance(e, AppError):
                    provider = e.provider or provider
                    metrics.record_error(provider, e.code.value)
                else:
                    metrics.record_error(provider, type(e).__name__)
            except Exception:
                pass
            raise
