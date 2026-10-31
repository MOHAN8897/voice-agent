import asyncio
from unittest.mock import AsyncMock

import pytest

from server.services.saas import voice_sample_cache as cache
from server.services.saas import voice_preview


@pytest.mark.asyncio
async def test_sample_persists_and_concurrent_clicks_generate_once(tmp_path, monkeypatch):
    path = tmp_path / "sample.wav"
    monkeypatch.setattr(cache, "sample_path", lambda _parts: path)
    audio = voice_preview.pcm16_to_wav(b"\x01\x00" * 480, 24000)

    async def synthesize():
        await asyncio.sleep(.01)
        return audio

    generate = AsyncMock(side_effect=synthesize)
    results = await asyncio.gather(*(cache.get_or_create(["sample"], generate) for _ in range(4)))
    assert all(result[0] == audio for result in results)
    generate.assert_awaited_once()
    assert path.read_bytes() == audio
    another_generator = AsyncMock(side_effect=AssertionError("must use disk after first request"))
    assert await cache.get_or_create(["sample"], another_generator) == (audio, True)


@pytest.mark.asyncio
async def test_corrupt_sample_is_regenerated_and_failures_not_cached(tmp_path, monkeypatch):
    path = tmp_path / "sample.wav"
    path.write_bytes(b"broken")
    monkeypatch.setattr(cache, "sample_path", lambda _parts: path)
    with pytest.raises(RuntimeError, match="provider denied"):
        await cache.get_or_create(["sample"], AsyncMock(side_effect=RuntimeError("provider denied")))
    audio = voice_preview.pcm16_to_wav(b"\x01\x00" * 240, 24000)
    assert (await cache.get_or_create(["sample"], AsyncMock(return_value=audio)))[0] == audio
    assert path.read_bytes() == audio


@pytest.mark.asyncio
async def test_custom_tenant_greeting_does_not_enter_shared_cache(monkeypatch):
    generate = AsyncMock(return_value=voice_preview.pcm16_to_wav(b"\x01\x00" * 240, 24000))
    monkeypatch.setattr(voice_preview, "_synthesize_gemini", generate)
    monkeypatch.setattr(cache, "get_or_create", AsyncMock(side_effect=AssertionError("custom text must stay private")))
    for _ in range(2):
        result = await voice_preview.synthesize_preview("Private customer greeting", voice_id="te-in-csagent-5", provider="gemini", language="te-IN")
        assert not result["cacheable"]
    assert generate.await_count == 2


def test_cache_key_separates_provider_voice_language_and_speed(monkeypatch, tmp_path):
    monkeypatch.setattr("server.config.env.get_settings", lambda: type("Settings", (), {"data_dir": str(tmp_path)})())
    paths = {
        cache.sample_path(["gemini", "model", "voice-1", "te-IN", 1, "text"]),
        cache.sample_path(["gemini", "model", "voice-2", "te-IN", 1, "text"]),
        cache.sample_path(["gemini", "model", "voice-1", "hi-IN", 1, "text"]),
        cache.sample_path(["gemini", "model", "voice-1", "te-IN", .9, "text"]),
    }
    assert len(paths) == 4


@pytest.mark.asyncio
async def test_cache_write_failure_does_not_discard_generated_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "sample_path", lambda _parts: tmp_path / "sample.wav")
    monkeypatch.setattr(cache, "_write", lambda *_args: (_ for _ in ()).throw(OSError("disk full")))
    audio = voice_preview.pcm16_to_wav(b"\x01\x00" * 240, 24000)
    assert await cache.get_or_create(["sample"], AsyncMock(return_value=audio)) == (audio, False)


def test_truncated_wav_is_not_treated_as_a_stored_sample():
    audio = voice_preview.pcm16_to_wav(b"\x01\x00" * 240, 24000)
    assert cache.valid_wav(audio)
    assert not cache.valid_wav(audio[:-8])
