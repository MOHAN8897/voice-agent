"""Telnyx saved-recording URL parsing and delayed attach for history playback."""
from __future__ import annotations

from pathlib import Path

import pytest

from server.call.audio_archive import audio_archive
from server.config.env import get_settings
from server.services.telnyx_recordings import (
    _recording_url,
    attach_pending_recording,
    ingest_recording_saved,
)


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


@pytest.mark.asyncio
async def test_ingest_stashes_until_internal_call_id(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ENABLE_CALL_ARCHIVE", "true")
    get_settings.cache_clear()
    audio_archive.reset_for_tests()

    async def fake_download(_url: str) -> bytes:
        return b"RIFF" + b"\x00" * 40

    monkeypatch.setattr("server.services.telnyx_recordings._download_recording", fake_download)

    from server.services.telnyx_client import telnyx_call_registry

    previous = dict(telnyx_call_registry._calls)
    try:
        telnyx_call_registry._calls.clear()
        telnyx_call_registry.upsert("ctl-pending", {"status": "answered"})
        await ingest_recording_saved(
            "ctl-pending",
            {"recording_urls": {"wav": "https://example.com/a.wav"}, "channels": "dual"},
        )
        row = telnyx_call_registry.get("ctl-pending") or {}
        pending = row.get("pending_recording")
        assert isinstance(pending, dict)
        assert Path(str(pending.get("path") or "")).is_file()
        assert audio_archive.file_for("call-pending", "mix") is None

        telnyx_call_registry.upsert("ctl-pending", {"internal_call_id": "call-pending"})
        await attach_pending_recording("ctl-pending", "call-pending")
        chosen = audio_archive.file_for("call-pending", "mix")
        assert chosen is not None
        assert chosen.name.startswith("telnyx")
        leftover = (telnyx_call_registry.get("ctl-pending") or {}).get("pending_recording")
        assert leftover in (None, {})
    finally:
        telnyx_call_registry._calls = previous
        audio_archive.reset_for_tests()
        get_settings.cache_clear()
