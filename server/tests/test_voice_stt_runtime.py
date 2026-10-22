"""Shared voice pipeline runtime helpers."""
from server.services.voice_stt_runtime import (
    DEFAULT_STT_SILENCE_MS,
    effective_stt_mode,
    effective_stt_silence_ms,
    effective_stt_stream_type,
)


def test_effective_stt_silence_default():
    assert DEFAULT_STT_SILENCE_MS == 400
    assert effective_stt_silence_ms({}) == DEFAULT_STT_SILENCE_MS
    assert effective_stt_silence_ms({}, explicit=350) == 350
    assert effective_stt_silence_ms({"sttSilenceMs": 500}) == 500


def test_effective_stt_stream_type_normalizes_invalid():
    assert effective_stt_stream_type("accurate") == "fast"
    assert effective_stt_stream_type("fast") == "fast"


def test_effective_stt_mode_transcribe_only():
    assert effective_stt_mode("translate") == "transcribe"
    assert effective_stt_mode("transcribe") == "transcribe"
