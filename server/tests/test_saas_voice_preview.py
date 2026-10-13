import pytest
import wave
import io
from server.services.saas.voice_preview import (
    normalize_preview_text,
    pcm16_to_wav,
    resolve_preview_voice,
    resolve_openai_tts_voice,
    synthesize_preview,
)


def test_normalize_preview_text():
    assert normalize_preview_text("  Hello   world!  ") == "Hello world!"
    with pytest.raises(ValueError):
        normalize_preview_text("   ")


def test_pcm16_to_wav():
    dummy_pcm = b"\x00\x00" * 100
    wav_bytes = pcm16_to_wav(dummy_pcm, 24000)
    assert wav_bytes.startswith(b"RIFF")
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 24000
        assert wf.getnframes() == 100


def test_resolve_preview_voice():
    voice, label = resolve_preview_voice("marin")
    assert voice is not None
    assert label is not None

    voice, label = resolve_preview_voice("cedar")
    assert voice is not None

    voice, label = resolve_preview_voice("unknown_voice_123")
    assert voice is not None
    assert label == "default"


def test_resolve_openai_tts_voice():
    assert resolve_openai_tts_voice("marin") == "coral"
    assert resolve_openai_tts_voice("cedar") == "onyx"
    assert resolve_openai_tts_voice("ash") == "ash"
    assert resolve_openai_tts_voice(None) == "coral"


@pytest.mark.asyncio
async def test_synthesize_preview_returns_valid_wav():
    res = await synthesize_preview(
        text="నమస్కారం, మీరు ఎలా ఉన్నారు?",
        voice_id="marin",
        language="te-IN",
        speed=1.05,
    )
    assert "audio" in res
    audio = res["audio"]
    assert audio.startswith(b"RIFF")
    assert b"WAVE" in audio[:16]
    assert len(audio) > 1000
    assert res["voice"] is not None
    assert res["model"] is not None
