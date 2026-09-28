"""Live OpenAI STT sidecar must not replace Gemini user_transcript for hangup control."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.services.pstn_realtime_voice_core import PstnRealtimeVoiceLoop


@pytest.mark.asyncio
async def test_gemini_user_transcript_not_dropped_when_sidecar_active():
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="call-tx-hangup",
        on_agent_wire=AsyncMock(),
        stack_override={
            "pipeline": "realtime_voice",
            "llm": {"provider": "gemini", "model": "gemini-3.8-live"},
            "transcription": {"live_enabled": True, "post_call_enabled": False},
        },
    )
    loop._live_model = "gemini-3.8-live"
    loop._caller_stt = MagicMock()
    loop._adapter = MagicMock()

    with patch.object(loop, "_should_drop_user_final", return_value=False):
        with patch.object(loop, "_arm_hangup_from_transcript_closing", new_callable=AsyncMock) as arm:
            with patch("server.call.call_ledger.call_ledger") as ledger:
                ledger.append_user_turn = AsyncMock(return_value={"seq": 1})
                await loop._handle_event(
                    {"type": "user_transcript", "text": "sare bye hang up cheyandi", "final": True}
                )
            arm.assert_awaited_once()

    ledger.append_user_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_sidecar_final_only_appends_ledger():
    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id="call-tx-sidecar",
        on_agent_wire=AsyncMock(),
        stack_override={
            "transcription": {"live_enabled": True, "post_call_enabled": False},
        },
    )
    with patch.object(loop, "_should_drop_user_final", return_value=False):
        with patch.object(loop, "_persist_live_transcript_ledger", return_value=True):
            with patch("server.call.call_ledger.call_ledger") as ledger:
                ledger.append_user_turn = AsyncMock(return_value={"seq": 2})
                await loop._on_caller_stt_final("caller said hello")
    ledger.append_user_turn.assert_awaited_once_with("call-tx-sidecar", "caller said hello")
