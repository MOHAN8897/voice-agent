from server.call.hangup_judge import (
    agent_spoke_closing,
    agent_spoke_disqualification_close,
    caller_polite_thanks_only,
)
from server.services.pstn_realtime_voice_core import (
    FAST_GOAL_COMPLETE_POST_FAREWELL_SEC,
    FAST_REFUSAL_POST_FAREWELL_SEC,
    PstnRealtimeVoiceLoop,
)


def test_telugu_thanks_goodbye_counts_as_closing():
    assert agent_spoke_closing("Sare, time ichinanduku thanks. Good day.")


def test_thank_you_for_your_time_counts_as_closing():
    assert agent_spoke_closing(
        "Since you don't have a vehicle yourself, I will thank you for your time today."
    )


def test_have_a_great_day_counts_as_closing():
    assert agent_spoke_closing("You're welcome. Have a great day.")


def test_polite_thanks_only_ack():
    assert caller_polite_thanks_only("Yeah, thank you.")
    assert caller_polite_thanks_only("Okay then, thank you.")
    assert not caller_polite_thanks_only("What are the things you will do?")


def test_disqualification_close_detected():
    spoken = (
        "Thank you, Mohan. Yes, we service cars, including BMWs. "
        "Since you don't have a vehicle yourself, I will thank you for your time today."
    )
    assert agent_spoke_disqualification_close(spoken)
    assert agent_spoke_closing(spoken)


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
    # Close listen is transport-driven (0s); fast-hangup flags affect other paths only.
    loop._firm_refusal_close = True
    assert loop._close_listen_sec() == 0.0
    loop._firm_refusal_close = False
    loop._fast_script_farewell = True
    assert loop._close_listen_sec() == 0.0
