"""Call recording downloads as MP3 when ffmpeg is available."""
from __future__ import annotations

import shutil
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server.app as app_mod
from server.call.audio_archive import audio_archive
from server.call.audio_mp3 import convert_wav_to_mp3
from server.config.env import get_settings


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SAAS_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    audio_archive.reset_for_tests()
    yield TestClient(app_mod.app)
    audio_archive.reset_for_tests()
    get_settings.cache_clear()


def test_convert_wav_to_mp3_roundtrip(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    wav = tmp_path / "t.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<h", 0) * 800)
    mp3 = tmp_path / "t.mp3"
    assert convert_wav_to_mp3(wav, mp3)
    assert mp3.stat().st_size > 100


def test_download_endpoint_returns_mp3_when_ffmpeg(client, monkeypatch, tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    call_id = "mp3-dl"
    audio_archive.init(call_id)
    mix = audio_archive.mix_clear_path(call_id)
    with wave.open(str(mix), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<hh", 100, -100) * 400)
    r = client.get(f"/api/call/{call_id}/audio/mix_clear?download=1")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("audio/mpeg")
    assert r.content[:3] == b"ID3" or r.content[:2] == b"\xff\xfb"
