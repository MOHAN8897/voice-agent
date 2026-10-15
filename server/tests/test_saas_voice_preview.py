import pytest
import wave
import io
from types import SimpleNamespace
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


@pytest.mark.asyncio
async def test_synthesize_preview_passes_selected_language_to_gemini(monkeypatch):
    from server.services.saas import voice_preview
    from server.services.saas import voice_catalog

    settings = SimpleNamespace(openai_api_key=None)
    monkeypatch.setattr("server.config.env.get_settings", lambda: settings)
    monkeypatch.setattr(
        voice_catalog,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key="configured", enable_gemini=True),
    )
    monkeypatch.setattr("server.providers.gemini_llm._api_key", lambda: "configured")

    class FakeAdapter:
        def __init__(self):
            self.connect_kwargs = None
            self.response_instructions = None
            self.events = [
                {"type": "audio_delta", "pcm": b"\x01\x00" * 240},
                {"type": "response_done"},
            ]

        async def connect(self, **kwargs):
            self.connect_kwargs = kwargs

        async def wait_ready(self, timeout=6.0):
            return None

        async def start_response(self, *, instructions):
            self.response_instructions = instructions

        async def poll_event(self, timeout=0.5):
            return self.events.pop(0) if self.events else None

        async def close(self):
            return None

    adapter = FakeAdapter()
    monkeypatch.setattr(
        "server.realtime.providers.gemini_voice.GeminiLiveVoiceAdapter",
        lambda: adapter,
    )

    result = await voice_preview.synthesize_preview(
        "Hello, how can I help you?",
        voice_id="zephyr",
        language="hi-IN",
    )

    assert result["voice"] == "Zephyr"
    assert "hi-IN" in adapter.connect_kwargs["instructions"]
    assert "Hindi" in adapter.connect_kwargs["instructions"]
    assert "translate it faithfully" in adapter.connect_kwargs["instructions"]
    assert "hi-IN" in adapter.response_instructions


@pytest.mark.asyncio
async def test_direct_gemini_voice_does_not_fall_back_to_openai(monkeypatch):
    from server.services.saas import voice_catalog, voice_preview

    monkeypatch.setattr(
        "server.config.env.get_settings",
        lambda: SimpleNamespace(openai_api_key="configured-openai-key"),
    )
    monkeypatch.setattr(
        voice_catalog,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key="configured", enable_gemini=True),
    )
    monkeypatch.setattr("server.providers.gemini_llm._api_key", lambda: "configured")

    class FailedGeminiAdapter:
        async def connect(self, **_kwargs):
            raise RuntimeError("test Gemini outage")

        async def close(self):
            return None

    monkeypatch.setattr(
        "server.realtime.providers.gemini_voice.GeminiLiveVoiceAdapter",
        FailedGeminiAdapter,
    )

    with pytest.raises(RuntimeError, match="Gemini Live voice preview is unavailable"):
        await voice_preview.synthesize_preview(
            "नमस्ते",
            voice_id="zephyr",
            language="hi-IN",
        )

    with pytest.raises(RuntimeError, match="Gemini Live voice preview is unavailable"):
        await voice_preview.synthesize_preview(
            "నమస్కారం",
            voice_id="te-in-csagent-5",
            language="te-IN",
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
