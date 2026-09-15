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
    user_wav = archive.file_for(call_id, "user")
    agent_wav = archive.file_for(call_id, "agent")
    assert user_wav is not None and user_wav.suffix == ".wav"
    assert agent_wav is not None and agent_wav.suffix == ".wav"


@pytest.mark.asyncio
async def test_flush_twice_does_not_wipe_pcm(archive):
    call_id = "audio-twice"
    archive.init(call_id)
    archive.set_agent_sample_rate(call_id, 16000)
    user = struct.pack("<" + "h" * 8, *([1000] * 8))
    agent = struct.pack("<" + "h" * 8, *([2000] * 8))
    await archive.append_user_pcm(call_id, user)
    await archive.append_agent_audio(call_id, agent)
    first = await archive.flush(call_id)
    second = await archive.flush(call_id)
    assert first["user"] == "complete"
    assert second["user"] == "complete"
    assert archive.user_pcm_path(call_id).read_bytes() == user
    with wave.open(str(archive.mix_path(call_id)), "rb") as wf:
        assert wf.getnframes() == 8


@pytest.mark.asyncio
async def test_sixteen_khz_agent_pcm_mix_is_not_stretched(archive):
    call_id = "audio-16k-agent"
    archive.init(call_id)
    archive.set_agent_sample_rate(call_id, 16000)
    agent = struct.pack("<" + "h" * 1600, *([400] * 1600))
    await archive.append_agent_audio(call_id, agent)
    await archive.flush(call_id)
    with wave.open(str(archive.mix_path(call_id)), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 1600


@pytest.mark.asyncio
async def test_clear_audio_is_louder_than_raw(archive):
    call_id = "audio-clear"
    archive.init(call_id)
    archive.set_agent_sample_rate(call_id, 16000)
    quiet = struct.pack("<" + "h" * 8, *([200] * 8))
    await archive.append_user_pcm(call_id, quiet)
    await archive.append_agent_audio(call_id, quiet)
    await archive.flush(call_id)
    assert archive.mix_clear_path(call_id).exists()
    assert archive.user_clear_path(call_id).exists()

    def peak(path) -> int:
        with wave.open(str(path), "rb") as wf:
            data = wf.readframes(wf.getnframes())
        samples = struct.unpack(f"<{len(data) // 2}h", data)
        return max(abs(s) for s in samples)

    assert peak(archive.mix_clear_path(call_id)) > peak(archive.mix_path(call_id))


def test_peak_normalize_ignores_click_spike():
    from server.call.audio_archive import _peak_normalize_pcm16

    samples = [400] * 200
    samples[50] = 30000
    pcm = struct.pack("<" + "h" * 200, *samples)
    out = _peak_normalize_pcm16(pcm)
    boosted = struct.unpack("<200h", out)
    assert abs(boosted[0]) > 2000
    assert abs(boosted[50]) == 32767


@pytest.mark.asyncio
async def test_clear_mix_folds_both_parties_and_is_louder(archive):
    call_id = "audio-fold"
    archive.init(call_id)
    archive.set_agent_sample_rate(call_id, 16000)
    user = struct.pack("<" + "h" * 16, *([500] * 16))
    agent = struct.pack("<" + "h" * 16, *([800] * 16))
    await archive.append_user_pcm(call_id, user)
    await archive.append_agent_audio(call_id, agent)
    await archive.flush(call_id)
    with wave.open(str(archive.mix_path(call_id)), "rb") as wf:
        raw = struct.unpack("<hh", wf.readframes(1))
    with wave.open(str(archive.mix_clear_path(call_id)), "rb") as wf:
        clear = struct.unpack("<hh", wf.readframes(1))
    assert raw == (500, 800)
    assert clear[0] > raw[0]
    assert clear[1] > raw[1]


@pytest.mark.asyncio
async def test_refresh_clear_tracks_rebuilds_old_quiet_mix(archive):
    call_id = "audio-refresh"
    archive.init(call_id)
    archive.set_agent_sample_rate(call_id, 16000)
    quiet = struct.pack("<" + "h" * 32, *([300] * 32))
    await archive.append_user_pcm(call_id, quiet)
    await archive.append_agent_audio(call_id, quiet)
    await archive.flush(call_id)
    archive._clear_gain_mark(call_id).unlink()
    archive.mix_clear_path(call_id).write_bytes(archive.mix_path(call_id).read_bytes())

    def peak(path) -> int:
        with wave.open(str(path), "rb") as wf:
            data = wf.readframes(wf.getnframes())
        samples = struct.unpack(f"<{len(data) // 2}h", data)
        return max(abs(s) for s in samples)

    assert peak(archive.mix_clear_path(call_id)) == peak(archive.mix_path(call_id))
    archive.refresh_clear_tracks(call_id)
    assert peak(archive.mix_clear_path(call_id)) > peak(archive.mix_path(call_id))
    archive.refresh_clear_tracks(call_id)


@pytest.mark.asyncio
async def test_clear_mix_does_not_bleed_agent_into_silent_caller(archive):
    call_id = "audio-no-bleed"
    archive.init(call_id)
    archive.set_agent_sample_rate(call_id, 16000)
    user = struct.pack("<" + "h" * 16, *([0] * 16))
    agent = struct.pack("<" + "h" * 16, *([800] * 16))
    await archive.append_user_pcm(call_id, user)
    await archive.append_agent_audio(call_id, agent)
    await archive.flush(call_id)
    with wave.open(str(archive.mix_clear_path(call_id)), "rb") as wf:
        left, right = struct.unpack("<hh", wf.readframes(1))
    assert left == 0
    assert abs(right) > abs(800)


@pytest.mark.asyncio
async def test_file_for_prefers_telnyx_recording(archive):
    call_id = "audio-telnyx"
    archive.init(call_id)
    archive.save_telnyx_recording(call_id, b"RIFF" + b"\x00" * 40, suffix=".wav")
    chosen = archive.file_for(call_id, "mix_clear")
    assert chosen is not None
    assert chosen.name.startswith("telnyx")


def _stereo_wav(left: list[int], right: list[int], rate: int = 8000) -> bytes:
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = b"".join(struct.pack("<hh", l, r) for l, r in zip(left, right))
        wf.writeframes(frames)
    return buf.getvalue()


def test_telnyx_review_folds_split_channels(archive):
    call_id = "audio-telnyx-fold"
    archive.init(call_id)
    wav = _stereo_wav([8000] * 160, [0] * 80 + [9000] * 80)
    archive.save_telnyx_recording(call_id, wav, suffix=".wav")
    review = archive.file_for(call_id, "mix_clear")
    assert review is not None
    assert review.name == "telnyx_review.wav"
    with wave.open(str(review), "rb") as wf:
        assert wf.getnchannels() == 2
        first = struct.unpack("<hh", wf.readframes(1))
        assert first[0] == first[1]
        assert abs(first[0]) > 1000
        wf.rewind()
        raw = wf.readframes(wf.getnframes())
    later = struct.unpack_from("<hh", raw, 80 * 4)
    assert later[0] == later[1]
    assert abs(later[0]) > abs(first[0])


def test_save_telnyx_keeps_larger_dual(archive):
    call_id = "audio-telnyx-keep"
    archive.init(call_id)
    bigger = _stereo_wav([1200] * 400, [800] * 400)
    smaller = _stereo_wav([100] * 40, [100] * 40)
    archive.save_telnyx_recording(call_id, bigger, suffix=".wav")
    kept = archive.telnyx_wav_path(call_id).stat().st_size
    archive.save_telnyx_recording(call_id, smaller, suffix=".wav")
    assert archive.telnyx_wav_path(call_id).stat().st_size == kept

