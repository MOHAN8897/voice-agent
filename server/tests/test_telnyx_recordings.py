"""Telnyx saved-recording URL parsing for history playback."""
from __future__ import annotations

from server.services.telnyx_recordings import _recording_url


def test_recording_url_prefers_wav():
    url, suffix = _recording_url(
        {
            "recording_urls": {
                "mp3": "https://example.com/a.mp3",
                "wav": "https://example.com/a.wav",
            }
        }
    )
    assert suffix == ".wav"
    assert url.endswith(".wav")


def test_recording_url_falls_back_to_mp3():
    url, suffix = _recording_url({"recording_urls": {"mp3": "https://example.com/a.mp3"}})
    assert suffix == ".mp3"
    assert url.endswith(".mp3")


def test_recording_url_accepts_public_urls():
    url, suffix = _recording_url(
        {"public_recording_urls": {"wav": "https://example.com/public.wav"}}
    )
    assert suffix == ".wav"
    assert "public.wav" in url


def test_recording_url_accepts_download_urls():
    url, suffix = _recording_url(
        {"download_urls": {"wav": "https://example.com/stored.wav"}}
    )
    assert suffix == ".wav"
    assert "stored.wav" in url
