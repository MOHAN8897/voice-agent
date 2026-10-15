"""Gemini Live adapter event mapping — tools must not drop audio."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.realtime.models import GEMINI_LIVE_LIBRARY_VOICES, GEMINI_LIVE_VOICES, normalize_realtime_voice
from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter, normalize_gemini_live_voice
from server.realtime.voice_manager import RealtimeVoiceManager


def test_normalize_realtime_voice_keeps_gemini_prebuilt():
    assert normalize_realtime_voice("Puck") == "Puck"
    assert normalize_realtime_voice("aoede") == "Aoede"
    assert normalize_realtime_voice("marin") == "marin"


@pytest.mark.parametrize("voice", GEMINI_LIVE_VOICES)
def test_all_gemini_live_voices_normalize_case_insensitively(voice):
    assert normalize_realtime_voice(voice.lower()) == voice
    assert normalize_gemini_live_voice(voice.lower()) == voice


@pytest.mark.parametrize("voice", GEMINI_LIVE_LIBRARY_VOICES)
def test_indic_gemini_library_voices_normalize_case_insensitively(voice):
    assert normalize_gemini_live_voice(voice.upper()) == voice


@pytest.mark.asyncio
async def test_voice_manager_passes_direct_gemini_voice_to_live_adapter():
    class CapturingAdapter:
        def __init__(self):
            self.connect_kwargs = None

        async def connect(self, **kwargs):
            self.connect_kwargs = kwargs

    adapter = CapturingAdapter()
    manager = RealtimeVoiceManager()
    stack = {
        "pipeline": "realtime_voice",
        "language": "hi-IN",
        "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
        "realtime_voice": {"voice": "alnilam"},
    }

    await manager.create(
        "gemini-direct-voice-test",
        instructions="Speak only in Hindi.",
        language="hi-IN",
        stack_override=stack,
        adapter=adapter,
    )

    assert adapter.connect_kwargs["model"] == "gemini-3.8-live"
    assert adapter.connect_kwargs["voice"] == "Alnilam"


@pytest.mark.asyncio
async def test_voice_manager_does_not_fallback_direct_gemini_voice_to_openai():
    attempts = []

    class FailedAdapter:
        async def connect(self, **kwargs):
            attempts.append(kwargs)
            raise RuntimeError("Gemini Live unavailable")

        async def close(self):
            return None

    manager = RealtimeVoiceManager(adapter_factory=lambda **_kwargs: FailedAdapter())
    stack = {
        "pipeline": "realtime_voice",
        "language": "hi-IN",
        "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
        "realtime_voice": {"voice": "alnilam"},
    }

    with pytest.raises(RuntimeError, match="Gemini Live unavailable"):
        await manager.create(
            "gemini-direct-voice-no-fallback-test",
            instructions="Speak only in Hindi.",
            language="hi-IN",
            stack_override=stack,
        )

    assert len(attempts) == 1
    assert attempts[0]["voice"] == "Alnilam"


@pytest.mark.asyncio
async def test_voice_manager_does_not_fallback_direct_indic_voice_to_openai():
    attempts = []

    class FailedAdapter:
        async def connect(self, **kwargs):
            attempts.append(kwargs)
            raise RuntimeError("Gemini Live unavailable")

        async def close(self):
            return None

    manager = RealtimeVoiceManager(adapter_factory=lambda **_kwargs: FailedAdapter())
    stack = {
        "pipeline": "realtime_voice",
        "language": "te-IN",
        "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
        "realtime_voice": {"voice": "te-in-csagent-5"},
    }

    with pytest.raises(RuntimeError, match="Gemini Live unavailable"):
        await manager.create(
            "gemini-indic-voice-no-fallback-test",
            instructions="Speak only in Telugu.",
            language="te-IN",
            stack_override=stack,
        )

    assert len(attempts) == 1
    assert attempts[0]["voice"] == "te-in-csagent-5"


def test_gemini_normalize_keeps_tool_call_and_audio_together():
    adapter = GeminiLiveVoiceAdapter()
    pcm = b"\x00\x01" * 80
    part = SimpleNamespace(inline_data=SimpleNamespace(data=pcm))
    content = SimpleNamespace(
        interrupted=False,
        input_transcription=None,
        output_transcription=None,
        model_turn=SimpleNamespace(parts=[part]),
        turn_complete=True,
        generation_complete=False,
    )
    fc = SimpleNamespace(name="call_action", args={"action": "continue"}, id="fc-1")
    message = SimpleNamespace(
        setup_complete=None,
        session_resumption_update=None,
        voice_activity=None,
        tool_call=SimpleNamespace(function_calls=[fc]),
        server_content=content,
        usage_metadata=None,
    )
    events = adapter._normalize(message)
    kinds = [event["type"] for event in events]
    assert "function_call" in kinds
    assert "audio_delta" in kinds
    assert "response_done" in kinds
    audio_ids = {event["response_id"] for event in events if event.get("type") == "audio_delta"}
    tool_ids = {event["response_id"] for event in events if event.get("type") == "function_call"}
    assert audio_ids == tool_ids
    assert adapter.needs_explicit_opening is True


def test_gemini_usage_from_live_message_splits_modalities():
    from server.realtime.providers.gemini_voice import _usage_from_message

    meta = SimpleNamespace(
        model_dump=lambda: {
            "prompt_token_count": 1000,
            "response_token_count": 80,
            "prompt_tokens_details": [
                {"modality": "TEXT", "token_count": 900},
                {"modality": "AUDIO", "token_count": 100},
            ],
            "response_tokens_details": [
                {"modality": "AUDIO", "token_count": 80},
            ],
        }
    )
    usage = _usage_from_message(SimpleNamespace(usage_metadata=meta))
    assert usage["input_tokens"] == 1000
    assert usage["output_tokens"] == 80
    assert usage["input_audio_tokens"] == 100
    assert usage["output_audio_tokens"] == 80
    assert usage["cached_tokens"] == 0


def test_gemini_usage_from_live_message_without_details_bills_output_audio():
    from server.realtime.providers.gemini_voice import _usage_from_message

    meta = SimpleNamespace(
        model_dump=lambda: {
            "prompt_token_count": 5904,
            "response_token_count": 180,
        }
    )
    usage = _usage_from_message(SimpleNamespace(usage_metadata=meta))
    assert usage["input_audio_tokens"] == 0
    assert usage["output_audio_tokens"] == 180
    assert usage["input_tokens"] == 5904


def test_gemini_start_response_accepts_audio_when_auto_response_off():
    adapter = GeminiLiveVoiceAdapter()
    adapter._auto_response = False
    adapter._accepting = True
    adapter._active_response_id = "r1"
    part = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x00\x01" * 16))
    content = SimpleNamespace(
        interrupted=False,
        input_transcription=None,
        output_transcription=None,
        model_turn=SimpleNamespace(parts=[part]),
        turn_complete=False,
        generation_complete=False,
    )
    message = SimpleNamespace(
        setup_complete=None,
        session_resumption_update=None,
        voice_activity=None,
        tool_call=None,
        server_content=content,
        usage_metadata=None,
    )
    events = adapter._normalize(message)
    assert any(event["type"] == "audio_delta" for event in events)


def test_gemini_usage_trailer_marks_usage_only():
    adapter = GeminiLiveVoiceAdapter()
    adapter._active_response_id = "r-done"
    adapter._accepting = True
    content = SimpleNamespace(
        interrupted=False,
        input_transcription=None,
        output_transcription=SimpleNamespace(text="lo cheppandi."),
        model_turn=None,
        turn_complete=True,
        generation_complete=False,
    )
    first = adapter._normalize(
        SimpleNamespace(
            setup_complete=None,
            session_resumption_update=None,
            voice_activity=None,
            tool_call=None,
            server_content=content,
            usage_metadata=None,
        )
    )
    dones = [event for event in first if event["type"] == "response_done"]
    assert len(dones) == 1
    assert dones[0].get("usage_only") is not True
    trailer = adapter._normalize(
        SimpleNamespace(
            setup_complete=None,
            session_resumption_update=None,
            voice_activity=None,
            tool_call=None,
            server_content=None,
            usage_metadata=SimpleNamespace(
                model_dump=lambda: {"prompt_token_count": 10, "response_token_count": 4}
            ),
        )
    )
    trail_dones = [event for event in trailer if event["type"] == "response_done"]
    assert len(trail_dones) == 1
    assert trail_dones[0].get("usage_only") is True
    assert trail_dones[0]["response_id"] == "r-done"


def test_gemini_note_opening_delivered_skips_clean_history():
    adapter = GeminiLiveVoiceAdapter()
    adapter.opening_history_clean = True
    adapter._session = object()
    assert adapter.opening_history_clean is True


@pytest.mark.asyncio
async def test_gemini_skips_activity_end_until_audio_sent():
    adapter = GeminiLiveVoiceAdapter()

    class Sess:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def send_realtime_input(self, **kwargs):
            self.calls.append(kwargs)

    adapter._session = Sess()
    await adapter.cancel_response()
    await adapter.set_auto_response(False)
    assert adapter._session.calls == []
    adapter._sent_realtime_audio = True
    await adapter.cancel_response()
    assert adapter._session.calls
    assert adapter._session.calls[0] == {"audio_stream_end": True}
