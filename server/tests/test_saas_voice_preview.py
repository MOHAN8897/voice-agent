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
