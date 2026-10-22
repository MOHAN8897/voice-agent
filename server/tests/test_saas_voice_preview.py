import pytest
import wave
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
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
    voice, label = resolve_preview_voice("marin", provider="openai")
    assert (voice, label) == ("marin", "Marin")
    voice, label = resolve_preview_voice("te-in-csagent-5", provider="gemini")
    assert voice == "te-in-csagent-5"
    assert "Telugu" in label
    with pytest.raises(ValueError, match="voice_not_in_active_catalog"):
        resolve_preview_voice("unknown_voice_123", provider="gemini")


def test_resolve_openai_tts_voice():
    assert resolve_openai_tts_voice("marin") == "coral"
    assert resolve_openai_tts_voice("cedar") == "onyx"
    assert resolve_openai_tts_voice("ash") == "ash"
    assert resolve_openai_tts_voice(None) == "coral"


@pytest.mark.asyncio
async def test_synthesize_preview_returns_valid_gemini_wav(monkeypatch):
    from server.services.saas import voice_preview

    audio = pcm16_to_wav(b"\x01\x00" * 240, 24000)

    async def synthesize(_line, _voice, _speed):
        return audio

    monkeypatch.setattr(voice_preview, "_synthesize_gemini", synthesize)
    res = await synthesize_preview(
        text="నమస్కారం, మీరు ఎలా ఉన్నారు?",
        voice_id="te-in-csagent-5",
        language="te-IN",
        speed=1.05,
        provider="gemini",
        model="gemini-3.8-live",
    )
    assert "audio" in res
    audio = res["audio"]
    assert audio.startswith(b"RIFF")
    assert b"WAVE" in audio[:16]
    assert len(audio) > 44
    assert res["voice"] is not None
    assert res["model"] == "gemini-3.8-flash-tts"
    assert res["stackModel"] == "gemini-3.8-live"


@pytest.mark.asyncio
async def test_synthesize_preview_sends_the_selected_gemini_voice_to_tts(monkeypatch):
    import base64
    import httpx

    from server.services.saas import voice_preview
    monkeypatch.setattr("server.providers.gemini_llm._api_key", lambda: "configured")
    audio = pcm16_to_wav(b"\x01\x00" * 240, 24000)
    captured = {}

    class FakeResponse:
        status_code = 200
        is_success = True

        @staticmethod
        def json():
            return {"output_audio": {"data": base64.b64encode(audio).decode("ascii")}}

    class FakeClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            captured.update({"url": url, "headers": headers, "body": json})
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    result = await voice_preview.synthesize_preview(
        "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?",
        voice_id="te-in-csagent-5",
        language="te-IN",
        provider="gemini",
        model="gemini-3.8-live",
    )

    assert result["voice"] == "te-in-csagent-5"
    assert result["audio"] == audio
    assert captured["url"].endswith("/v1beta/interactions")
    assert captured["headers"] == {"x-goog-api-key": "configured"}
    assert captured["body"]["model"] == "gemini-3.8-flash-tts"
    assert captured["body"]["generation_config"]["speech_config"] == [{"voice": "te-in-csagent-5"}]
    assert "నమస్కారం" in captured["body"]["input"][0]["content"][0]["text"]


@pytest.mark.asyncio
async def test_gemini_preview_does_not_fall_back_to_openai_on_permission_error(monkeypatch):
    import httpx
    from server.services.saas import voice_preview

    monkeypatch.setattr("server.providers.gemini_llm._api_key", lambda: "configured")
    monkeypatch.setattr(
        "server.config.env.get_settings",
        lambda: (_ for _ in ()).throw(AssertionError("OpenAI must not be consulted")),
    )

    class FakeResponse:
        status_code = 403
        is_success = False

        @staticmethod
        def json():
            return {"error": {"status": "PERMISSION_DENIED"}}

    class FakeClient:
        def __init__(self, *, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    with pytest.raises(RuntimeError, match="permission_denied"):
        await voice_preview.synthesize_preview(
            "नमस्ते",
            voice_id="te-in-csagent-5",
            language="hi-IN",
            provider="gemini",
        )


@pytest.mark.asyncio
async def test_voice_preview_route_explains_gemini_project_access_denial(monkeypatch):
    from fastapi import HTTPException
    from server.routes import app_telephony
    from server.services.saas import voice_preview

    monkeypatch.setattr("server.auth.rbac.role_has_permission", lambda *_args: True)

    async def denied_preview(*_args, **_kwargs):
        raise RuntimeError("1008 None. Your project has been denied access. Please contact support.")

    monkeypatch.setattr(voice_preview, "synthesize_preview", denied_preview)

    with pytest.raises(HTTPException) as caught:
        await app_telephony.voice_preview(
            SimpleNamespace(
                text="நமஸ்காரம்",
                voiceId="te-in-csagent-5",
                language="te-IN",
                speed=None,
            ),
            SimpleNamespace(role="subscriber"),
        )

    assert caught.value.status_code == 502
    assert caught.value.detail["error"]["code"] == "voice_preview_unavailable"
    assert "Google denied this project access" in caught.value.detail["error"]["message"]


@pytest.mark.asyncio
async def test_voice_preview_route_reports_quota_without_provider_fallback(monkeypatch):
    from fastapi import HTTPException
    from server.routes import app_telephony
    from server.services.saas import voice_preview

    monkeypatch.setattr("server.auth.rbac.role_has_permission", lambda *_args: True)
    monkeypatch.setattr(voice_preview, "synthesize_preview", AsyncMock(side_effect=voice_preview.VoicePreviewRateLimited(120)))
    with pytest.raises(HTTPException) as caught:
        await app_telephony.voice_preview(
            SimpleNamespace(text="Public sample", voiceId="te-in-csagent-5", language="te-IN", speed=None),
            SimpleNamespace(role="subscriber"),
        )
    assert caught.value.status_code == 429
    assert caught.value.headers["Retry-After"] == "120"
    assert caught.value.detail["error"]["code"] == "voice_preview_rate_limited"


@pytest.mark.asyncio
async def test_synthesize_preview_supports_sarvam(monkeypatch):
    from server.services.saas import voice_preview

    audio = voice_preview.pcm16_to_wav(b"\x02\x00" * 300, 24000)

    async def mock_sarvam(line, voice, speed, language=None):
        assert voice == "shubh"
        assert speed == 1.0
        return audio

    monkeypatch.setattr(voice_preview, "_synthesize_sarvam", mock_sarvam)
    result = await voice_preview.synthesize_preview(
        "నమస్కారం",
        voice_id="shubh",
        language="te-IN",
        provider="sarvam",
    )
    assert result["voice"] == "shubh"
    assert result["audio"] == audio
    assert result["model"] == "bulbul:v3"


@pytest.mark.asyncio
async def test_synthesize_preview_supports_low_gemini_tts(monkeypatch):
    from server.services.saas import voice_preview

    audio = voice_preview.pcm16_to_wav(b"\x03\x00" * 300, 24000)

    async def mock_gemini_tts(line, voice, speed, language=None, model=None):
        assert voice == "Zephyr"
        assert speed == 1.0
        assert language == "te-IN"
        return audio

    monkeypatch.setattr(voice_preview, "_synthesize_gemini_tts", mock_gemini_tts)
    result = await voice_preview.synthesize_preview(
        "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?",
        voice_id="Zephyr",
        language="te-IN",
        tier="low",
    )
    assert result["voice"] == "Zephyr"
    assert result["audio"] == audio
    assert result["model"] == "gemini-3.8-flash-lite-tts"


@pytest.mark.asyncio
async def test_synthesize_preview_supports_medium_sarvam_tts(monkeypatch):
    from server.services.saas import voice_preview

    audio = voice_preview.pcm16_to_wav(b"\x02\x00" * 200, 16000)

    async def mock_sarvam(line, voice, speed, language=None):
        assert voice == "shubh"
        assert speed == 1.0
        assert language == "te-IN"
        return audio

    monkeypatch.setattr(voice_preview, "_synthesize_sarvam", mock_sarvam)
    result = await voice_preview.synthesize_preview(
        "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?",
        voice_id="shubh",
        language="te-IN",
        tier="medium",
    )
    assert result["voice"] == "shubh"
    assert result["audio"] == audio
    assert result["model"] == "bulbul:v3"


@pytest.mark.asyncio
async def test_voice_preview_route_with_tier_and_alias(monkeypatch):
    from server.routes import app_telephony
    from server.services.saas import voice_preview, voice_stack_profiles

    monkeypatch.setattr("server.auth.rbac.role_has_permission", lambda *_args: True)
    voice_stack_profiles._REVERSE_ALIAS_CACHE["voc_test_low_alias"] = {
        "tier": "low",
        "provider": "gemini",
        "model": "gemini-3.8-flash-lite-tts",
        "providerVoiceId": "Zephyr",
        "label": "Voice 1",
        "languages": ["te-IN"],
    }

    dummy_audio = voice_preview.pcm16_to_wav(b"\x01\x00" * 200, 16000)
    monkeypatch.setattr(
        voice_preview,
        "synthesize_preview",
        AsyncMock(return_value={
            "audio": dummy_audio,
            "voice": "Zephyr",
            "label": "Voice 1",
            "model": "gemini-3.8-flash-lite-tts",
            "stackModel": "",
            "truncated": False,
            "cacheable": False,
            "cacheHit": False,
        }),
    )

    resp = await app_telephony.voice_preview(
        SimpleNamespace(
            text="నమస్కారం",
            voiceId="voc_test_low_alias",
            language="te-IN",
            speed=1.0,
            tier="low",
        ),
        SimpleNamespace(role="subscriber"),
    )
    assert resp.status_code == 200
    assert resp.headers["X-Voice-Name"] == "Voice 1"
    assert resp.headers["X-Voice-Label"] == "Voice 1"
    assert resp.body == dummy_audio


def test_find_static_sample_locates_sarvam_and_gemini_wavs():
    from server.services.saas.voice_preview import find_static_sample
    from server.services.saas.voice_sample_cache import valid_wav

    shubh_audio = find_static_sample("shubh", "te-IN")
    assert shubh_audio is not None
    assert valid_wav(shubh_audio)

    zephyr_audio = find_static_sample("zephyr", "te-IN")
    assert zephyr_audio is not None
    assert valid_wav(zephyr_audio)

    priya_audio = find_static_sample("priya", "hi-IN")
    assert priya_audio is not None
    assert valid_wav(priya_audio)


@pytest.mark.asyncio
async def test_synthesize_preview_serves_from_stored_sample_with_zero_api_calls(monkeypatch, tmp_path):
    from server.services.saas import voice_preview
    from server.config.env import get_settings
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))

    res = await voice_preview.synthesize_preview(
        "నమస్కారం. మీకు ఎలా సహాయం చేయగలను?",
        voice_id="shubh",
        language="te-IN",
        tier="medium",
    )
    assert res["voice"] == "shubh"
    assert res["model"] == "bulbul:v3"
    assert res["cacheable"] is True
    assert res["cacheHit"] is True
    assert len(res["audio"]) > 1000
    assert res["audio"].startswith(b"RIFF")

