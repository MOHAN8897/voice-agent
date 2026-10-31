"""Speaker-levelled call recordings: a quiet caller and a loud agent play at one level."""
from __future__ import annotations

import math
import os
import random
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from server.call import audio_archive as archive_mod
from server.call.audio_archive import _is_mpeg, audio_archive
from server.call.audio_levels import (
    CEILING_DBFS,
    TARGET_DBFS,
    level_interleaved_pcm16,
    level_speech_pcm16,
    speech_stats,
)
from server.config.env import get_settings

RATE = 16000


def _speech_like(seconds: float, speech_dbfs: float, *, noise_dbfs: float = -66.0, seed: int = 1):
    """Syllable-modulated harmonic bursts with gaps; returns (samples, gap ranges)."""
    rng = random.Random(seed)
    total = int(seconds * RATE)
    out = [rng.gauss(0, 1) * 32767 * 10 ** (noise_dbfs / 20) for _ in range(total)]
    speech = [0.0] * total
    gaps = []
    pos = int(0.5 * RATE)
    gaps.append((0, pos))
    while pos < total - RATE:
        length = int(rng.uniform(0.6, 1.4) * RATE)
        f0 = rng.uniform(110, 220)
        for i in range(min(length, total - pos)):
            t = i / RATE
            env = 0.5 - 0.5 * math.cos(2 * math.pi * 4.0 * t)  # ~4 syllables a second
            speech[pos + i] = env * sum(math.sin(2 * math.pi * f0 * k * t) / k for k in (1, 2, 3, 5))
        gap = int(rng.uniform(0.8, 1.5) * RATE)
        gaps.append((pos + length, min(total, pos + length + gap)))
        pos += length + gap
    active = [s for s in speech if s]
    rms = math.sqrt(sum(s * s for s in active) / len(active))
    scale = 32767 * 10 ** (speech_dbfs / 20) / rms
    for i, s in enumerate(speech):
        out[i] += s * scale
    return [max(-32768, min(32767, int(v))) for v in out], gaps


def _pcm(samples) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def _samples(pcm: bytes):
    return struct.unpack(f"<{len(pcm) // 2}h", pcm)


def _speech_db(samples, gaps) -> float:
    """RMS over the samples the generator put speech in (everything outside the gaps)."""
    in_gap = bytearray(len(samples))
    for start, end in gaps:
        in_gap[start:end] = b"" * (end - start)
    vals = [v for v, g in zip(samples, in_gap) if not g]
    return 20 * math.log10(math.sqrt(sum(v * v for v in vals) / len(vals)) / 32767)


def _gap_rms_db(samples, gaps) -> float:
    # Middle of each gap, clear of the onset/hangover windows around speech.
    vals = []
    for start, end in gaps:
        a, b = start + int(0.35 * RATE), end - int(0.15 * RATE)
        vals.extend(samples[a:b])
    return 20 * math.log10(math.sqrt(sum(v * v for v in vals) / len(vals)) / 32767)


def test_quiet_caller_and_loud_agent_end_within_two_db():
    caller, caller_gaps = _speech_like(12, -40.0, seed=3)
    agent, agent_gaps = _speech_like(12, -12.0, seed=4)
    assert _speech_db(agent, agent_gaps) - _speech_db(caller, caller_gaps) > 25  # the bug
    out_caller = _speech_db(_samples(level_speech_pcm16(_pcm(caller), RATE)), caller_gaps)
    out_agent = _speech_db(_samples(level_speech_pcm16(_pcm(agent), RATE)), agent_gaps)
    assert abs(out_caller - out_agent) <= 2.0
    assert abs(out_caller - TARGET_DBFS) <= 3.0
    assert abs(out_agent - TARGET_DBFS) <= 3.0


def test_levelled_audio_never_clips():
    hot, _ = _speech_like(8, -6.0, seed=5)  # peaks already slam full scale
    quiet, _ = _speech_like(8, -38.0, seed=6)
    quiet[RATE * 3] = 31000  # one click in quiet speech must not ride the boost into clipping
    ceiling = 32767 * 10 ** (CEILING_DBFS / 20) + 1
    for track in (hot, quiet):
        out = _samples(level_speech_pcm16(_pcm(track), RATE))
        assert max(abs(s) for s in out) <= ceiling


def test_click_does_not_block_gain_on_quiet_speech():
    quiet, _ = _speech_like(8, -38.0, seed=7)
    quiet[RATE * 4] = 30000
    assert speech_stats(level_speech_pcm16(_pcm(quiet), RATE), RATE)["speech_dbfs"] > -24.0


def test_line_noise_between_words_is_not_boosted():
    caller, gaps = _speech_like(12, -40.0, noise_dbfs=-60.0, seed=8)
    out = _samples(level_speech_pcm16(_pcm(caller), RATE))
    # Speech gained ~+20 dB; the hiss in the gaps may rise at most a few dB.
    assert _gap_rms_db(out, gaps) - _gap_rms_db(caller, gaps) <= 3.5
    silent = _pcm([0] * RATE)
    assert level_speech_pcm16(silent, RATE) == silent


def test_stereo_levels_each_channel_on_its_own():
    caller, caller_gaps = _speech_like(10, -38.0, seed=9)
    agent, agent_gaps = _speech_like(10, -14.0, seed=10)
    stereo = bytearray()
    for left, right in zip(caller, agent):
        stereo += struct.pack("<hh", left, right)
    out = _samples(level_interleaved_pcm16(bytes(stereo), RATE, 2))
    left = _speech_db(out[0::2], caller_gaps)
    right = _speech_db(out[1::2], agent_gaps)
    assert abs(left - right) <= 2.0


def test_raw_pcm_opening_on_minus_one_is_not_mistaken_for_mp3():
    assert not _is_mpeg(b"\xff\xff\xff\xff\x00\x00\x00\x00" * 100)
    assert not _is_mpeg(b"\xff\xff\x01\x00" * 100)
    # Two back-to-back MPEG-1 Layer III frames (128 kbps, 44.1 kHz -> 417 bytes).
    frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
    assert _is_mpeg(frame * 2)
    assert _is_mpeg(b"ID3\x04\x00")


@pytest.fixture
def archive(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    audio_archive.reset_for_tests()
    yield audio_archive
    audio_archive.reset_for_tests()
    get_settings.cache_clear()


def _write_carrier_wav(path, caller, agent, rate=RATE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"".join(struct.pack("<hh", a, b) for a, b in zip(caller, agent)))


def _channel_levels(path, left_gaps, right_gaps):
    with wave.open(str(path), "rb") as wf:
        out = _samples(wf.readframes(wf.getnframes()))
    return _speech_db(out[0::2], left_gaps), _speech_db(out[1::2], right_gaps)


def test_balanced_mix_from_carrier_recording_keeps_original(archive, monkeypatch):
    call_id = "balanced-carrier"
    caller, caller_gaps = _speech_like(10, -38.0, seed=11)
    agent, agent_gaps = _speech_like(10, -14.0, seed=12)
    raw = archive_mod.call_dir(call_id) / "vobiz_recording.wav"
    _write_carrier_wav(raw, caller, agent, rate=8000)
    original_bytes = raw.read_bytes()

    out = archive.ensure_balanced_mix(call_id)
    assert out is not None and out.name == "conversation_balanced.wav"
    assert raw.read_bytes() == original_bytes
    left, right = _channel_levels(out, caller_gaps, agent_gaps)
    assert abs(left - right) <= 2.0
    assert archive.levels_for(call_id, out) == ("vobiz", "balanced")

    # Cached until the version marker is bumped, then rebuilt lazily.
    stamp = out.stat().st_mtime_ns
    assert archive.ensure_balanced_mix(call_id).stat().st_mtime_ns == stamp
    monkeypatch.setattr(archive_mod, "_BALANCE_VERSION", 99)
    os.utime(out, ns=(stamp - 10**9, stamp - 10**9))
    rebuilt = archive.ensure_balanced_mix(call_id)
    assert rebuilt.stat().st_mtime_ns > stamp - 10**9
    assert (archive_mod.call_dir(call_id) / ".balanced_v99").exists()
    assert not (archive_mod.call_dir(call_id) / ".balanced_v1").exists()


@pytest.mark.asyncio
async def test_new_call_mix_clear_is_balanced(archive):
    call_id = "balanced-local"
    archive.init(call_id)
    archive.set_agent_sample_rate(call_id, 16000)
    caller, caller_gaps = _speech_like(8, -40.0, seed=13)
    agent, agent_gaps = _speech_like(8, -12.0, seed=14)
    await archive.append_user_pcm(call_id, _pcm(caller))
    await archive.append_agent_audio(call_id, _pcm(agent))
    await archive.flush(call_id)
    raw_left, raw_right = _channel_levels(archive.mix_path(call_id), caller_gaps, agent_gaps)
    assert raw_right - raw_left > 25
    path = archive.ensure_balanced_mix(call_id)
    assert path == archive.mix_clear_path(call_id)
    left, right = _channel_levels(path, caller_gaps, agent_gaps)
    assert abs(left - right) <= 2.0
    assert archive.levels_for(call_id, path) == ("local", "balanced")


def test_legacy_agent_track_saved_as_fake_mp3_is_recovered(archive):
    call_id = "legacy-fake-mp3"
    directory = archive_mod.call_dir(call_id)
    directory.mkdir(parents=True, exist_ok=True)
    caller, caller_gaps = _speech_like(6, -30.0, seed=15)
    agent, agent_gaps = _speech_like(6, -20.0, seed=16)
    agent[0] = -1  # opens on 0xFFFF, which the old check took for an MP3 sync word
    archive_mod._write_pcm16_wav(archive.user_wav_path(call_id), _pcm(caller), RATE)
    archive.agent_mp3_path(call_id).write_bytes(_pcm(agent))
    archive.refresh_clear_tracks(call_id)
    left, right = _channel_levels(archive.mix_clear_path(call_id), caller_gaps, agent_gaps)
    assert right > -30.0
    assert abs(left - right) <= 2.0


def test_audio_route_serves_balanced_by_default(archive):
    import server.app as app_mod
    from server.call.call_ledger import call_ledger

    call_id = "balanced-route"
    caller, _ = _speech_like(6, -38.0, seed=17)
    agent, _ = _speech_like(6, -14.0, seed=18)
    _write_carrier_wav(archive_mod.call_dir(call_id) / "vobiz_recording.wav", caller, agent, rate=8000)
    call_ledger.write_meta(call_id, {"call_id": call_id})
    client = TestClient(app_mod.app)

    played = client.get(f"/api/call/{call_id}/audio/mix")
    assert played.status_code == 200
    assert played.headers["X-Recording-Levels"] == "balanced"
    assert played.headers["X-Recording-Source"] == "vobiz"

    raw = client.get(f"/api/call/{call_id}/audio/mix?original=1")
    assert raw.status_code == 200
    assert raw.headers["X-Recording-Levels"] == "original"

    status = client.get(f"/api/call/{call_id}/audio-status").json()
    assert status["levels"] == "balanced"
