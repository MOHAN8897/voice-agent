"""Audio archive PCM capture and mix.wav generation."""
from __future__ import annotations

import struct
import wave

import pytest

from server.call.audio_archive import audio_archive
from server.config.env import get_settings


@pytest.fixture
def archive(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SARVAM_API_KEY", "sarvam-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    get_settings.cache_clear()
    audio_archive.reset_for_tests()
    yield audio_archive
    audio_archive.reset_for_tests()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_pcm_capture_and_mix(archive):
    call_id = "audio-1"
    archive.init(call_id)
    pcm = struct.pack("<" + "h" * 160, *([1000] * 160))
    await archive.append_user_pcm(call_id, pcm)
    await archive.append_agent_audio(call_id, b"ID3fake-mp3")
    status = await archive.flush(call_id)
    assert status["mix"] == "complete"
    user = archive.user_pcm_path(call_id)
    mix = archive.mix_path(call_id)
    agent = archive.agent_path(call_id)
    assert user.exists() and user.read_bytes() == pcm
    assert agent.exists() and agent.read_bytes().startswith(b"ID3")
    with wave.open(str(mix), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 160


@pytest.mark.asyncio
async def test_pcm_stereo_mix_left_user_right_agent(archive):
    call_id = "audio-pcm"
    archive.init(call_id)
    archive.set_agent_sample_rate(call_id, 16000)
    user = struct.pack("<" + "h" * 8, *([1000] * 8))
    agent = struct.pack("<" + "h" * 8, *([2000] * 8))
    await archive.append_user_pcm(call_id, user)
    await archive.append_agent_audio(call_id, agent)
    await archive.flush(call_id)
    assert archive.agent_pcm_path(call_id).exists()
    with wave.open(str(archive.mix_path(call_id)), "rb") as wf:
        frames = wf.readframes(1)
    left, right = struct.unpack("<hh", frames)
    assert left == 1000
    assert right == 2000
