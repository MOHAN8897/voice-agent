from server.call.hangup_judge import agent_spoke_closing
from server.services.pstn_realtime_voice_core import (
    FAST_GOAL_COMPLETE_POST_FAREWELL_SEC,
    FAST_REFUSAL_POST_FAREWELL_SEC,
    PstnRealtimeVoiceLoop,
)


def test_telugu_thanks_goodbye_counts_as_closing():
    assert agent_spoke_closing("Sare, time ichinanduku thanks. Good day.")


def test_fast_hangup_close_listen_durations():
    from unittest.mock import AsyncMock

    from server.realtime.testing import FakeRealtimeVoiceAdapter

    loop = PstnRealtimeVoiceLoop(
        session_id="s",
        call_id=None,
        on_agent_wire=AsyncMock(),
        sample_rate=16000,
        tts_output_codec="linear16",
        adapter=FakeRealtimeVoiceAdapter(),
        stack_override={"pipeline": "realtime_voice"},
    )
    loop._firm_refusal_close = True
    assert loop._close_listen_sec() == FAST_REFUSAL_POST_FAREWELL_SEC
    loop._firm_refusal_close = False
    loop._fast_script_farewell = True
    assert loop._close_listen_sec() == FAST_GOAL_COMPLETE_POST_FAREWELL_SEC
