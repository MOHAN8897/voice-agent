"""Sarvam STT adapter — wraps existing sarvam_stt_service + sarvam_ws."""
from __future__ import annotations

from server.config.constants import constants, provider_language_code
from server.providers.base import STTAdapter, STTConfig, TranscriptResult
from server.services import sarvam_stt_service
from server.services.sarvam_ws import connect_stt_realtime


class SarvamSTTAdapter:
    provider_id = "sarvam"

    def supported_languages(self) -> list[str]:
        return list(constants.SUPPORTED_LANGUAGES.keys())

    async def transcribe_rest(self, audio: bytes, config: STTConfig) -> TranscriptResult:
        text = await sarvam_stt_service.transcribe_audio(audio, language_code=provider_language_code(config.language, provider="sarvam", stage="stt"))
        return TranscriptResult(text=text or "", language=config.language, is_final=True)

    def connect_realtime(self, config: STTConfig):
        vad = config.vad_config or {}
        return connect_stt_realtime(
            language_code=provider_language_code(config.language, provider="sarvam", stage="stt"),
            stream_type=config.stream_type,
            mode="transcribe",
            endpointing="vad",
            sample_rate=config.sample_rate,
            silence_duration_ms=vad.get("silence_duration_ms"),
            threshold=vad.get("threshold"),
            model=config.model,
        )
