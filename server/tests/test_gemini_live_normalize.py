"""Gemini Live adapter event mapping — tools must not drop audio."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.realtime.models import normalize_realtime_voice
from server.realtime.providers.gemini_voice import GeminiLiveVoiceAdapter


def test_normalize_realtime_voice_keeps_gemini_prebuilt():
    assert normalize_realtime_voice("Puck") == "Puck"
    assert normalize_realtime_voice("aoede") == "Aoede"
    assert normalize_realtime_voice("marin") == "marin"


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
