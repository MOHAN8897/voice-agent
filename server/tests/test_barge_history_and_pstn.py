import asyncio

import pytest

from server.agent.conversation_manager import ConversationManager
from server.services.echo_guard import (
    BARGE_ECHO_OVERLAP,
    is_barge_echo,
    is_barge_final_echo,
    is_likely_echo,
)
from server.services.pstn_playback import EstimatedPlaybackTracker, TelnyxQueuePlayback
from server.services.pstn_turn_tts import PstnTurnTtsSession
from server.services.pstn_voice_core import PstnVoiceLoop


def test_echo_matches_agent_words():
    assert is_likely_echo("how can I help you", "Hi, this is Priya. How can I help you?")


def test_echo_ignores_real_question():
    assert not is_likely_echo("what is the plot size", "Hi, this is Priya from Acme.")


def test_barge_echo_threshold_looser_than_final():
    # Mid-overlap may barge-reject at 0.55 while still below final 0.65 depending on text.
    assert BARGE_ECHO_OVERLAP < 0.65
    assert is_barge_echo("how can I help", "Hi, this is Priya. How can I help you today?")
    assert not is_barge_final_echo("what is plot size please", "Hi, this is Priya from Acme.")


def test_note_barge_truncates_last_assistant():
    cm = ConversationManager(max_messages=8)
    cm.add_turn("s", "hi", "This is a long greeting you never heard fully.")
    cm.note_barge("s", "This is a long")
    hist = cm.get_history("s")
    assert hist[-1]["role"] == "assistant"
    assert "interrupted" in hist[-1]["content"]
    assert "never heard" not in hist[-1]["content"]


def test_add_turn_uses_pending_barge_heard():
    cm = ConversationManager(max_messages=8)
    cm.note_barge("s2", "Hello there")
    cm.add_turn("s2", "wait", "A full reply the caller did not hear at all")
    hist = cm.get_history("s2")
    assert "Hello there" in hist[-1]["content"]
    assert "interrupted" in hist[-1]["content"]
    assert "did not hear" not in hist[-1]["content"]


def test_pstn_barge_commit_short_phrase_and_hold(monkeypatch):
    """Natural short barge + hold — no longer requires 3 whitespace words."""
    import time

    loop = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    monkeypatch.setattr("server.services.pstn_voice_core.ENABLE_PSTN_BARGE_IN", True)
    loop._tts_active = True
    loop._agent_speaking = True
    loop._partial_started_at = 0.0
    loop._tts_started_at = 1.0
    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    # First partial only starts the hold clock.
    assert loop._should_commit_barge("actually no") is False
    assert loop._partial_started_at == 10.0
    monkeypatch.setattr(time, "monotonic", lambda: 10.20)
    assert loop._should_commit_barge("actually no") is True
    # Too soon after speak start
    loop._partial_started_at = 0.0
    loop._tts_started_at = 10.0
    monkeypatch.setattr(time, "monotonic", lambda: 10.10)
    assert loop._should_commit_barge("I want two plants please") is False


def test_pstn_intro_phase_queues_not_barge(monkeypatch):
    loop = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    monkeypatch.setattr("server.services.pstn_voice_core.ENABLE_PSTN_BARGE_IN", True)
    loop._intro_phase = True
    loop._tts_active = True
    loop._tts_started_at = 1.0
    import time

    monkeypatch.setattr(time, "monotonic", lambda: 20.0)
    assert loop._should_commit_barge("I want two plants please") is False
    loop._queue_user_transcript("My name is Ravi", intro=True)
    assert loop._intro_queue == ["My name is Ravi"]
    loop._intro_phase = False
    loop._intro_queue.clear()
    loop._partial_started_at = 0.0
    loop._tts_started_at = 1.0
    monkeypatch.setattr(time, "monotonic", lambda: 20.0)
    assert loop._should_commit_barge("I want two plants please") is False
    monkeypatch.setattr(time, "monotonic", lambda: 20.20)
    assert loop._should_commit_barge("I want two plants please") is True


def test_estimated_playback_tracker_active_and_clear():
    tr = EstimatedPlaybackTracker(frame_ms=20.0, post_send_hold_ms=0.0)
    assert not tr.is_active()
    tr.note_sent_frames(5)
    assert tr.is_active()
    assert tr.queued_ms() == 100.0
    assert tr.clear() == 5
    assert not tr.is_active()


def test_estimated_playback_hold_after_send():
    tr = EstimatedPlaybackTracker(frame_ms=20.0, post_send_hold_ms=200.0)
    tr.note_sent_frames(1)
    tr._queued_frames = 0  # frames drained but hold remains
    assert tr.is_active()
    tr.clear()
    assert not tr.is_active()


def test_telnyx_queue_playback_wraps_queue():
    q: list[int] = [1, 2, 3]

    def drain() -> int:
        n = len(q)
        q.clear()
        return n

    pb = TelnyxQueuePlayback(queue_size=lambda: len(q), drain=drain, sending=lambda: False)
    assert pb.is_active()
    assert pb.queued_ms() == 60.0
    assert pb.clear() == 3
    assert not pb.is_active()
    pb.set_current_generation("g1")
    pb.invalidate_generation("g1")
    assert not pb.is_generation_valid("g1")


def test_emission_blocked_after_interrupt():
    loop = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    loop.current_generation_id = "gen-a"
    assert not loop.emission_blocked()
    loop._interrupted_generation = "gen-a"
    assert loop.emission_blocked()


def test_tts_flush_skipped_when_interrupted():
    session = PstnTurnTtsSession.__new__(PstnTurnTtsSession)
    session._interrupted = True
    session._voice = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    session._audio_buf = bytearray(b"\x00" * 40)
    session._use_mulaw_wire = False
    import asyncio

    asyncio.run(session._flush_audio_tail())
    # Interrupt path clears buffer and must not emit.
    assert len(session._audio_buf) == 0


def test_think_cancel_during_thinking_phase(monkeypatch):
    loop = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    from server.services.pstn_voice_core import PHASE_THINKING

    loop._phase = PHASE_THINKING
    loop._tts_active = False
    import time

    monkeypatch.setattr(time, "monotonic", lambda: 5.0)
    # Short backchannel must never think-cancel.
    assert loop._should_think_cancel("Yeah yeah") is False
    assert loop._should_think_cancel("ok ok sure") is False
    # Substantive continuation arms hold, then cancels after hold window.
    assert loop._should_think_cancel("I need more info please book") is False
    monkeypatch.setattr(time, "monotonic", lambda: 5.5)
    assert loop._should_think_cancel("I need more info please book") is True
    loop._tts_active = True
    assert loop._should_think_cancel("I need more info please book") is False


def test_substantive_transcript_gate():
    from server.services.transcript_gate import is_substantive_transcript

    assert not is_substantive_transcript("ok")
    assert is_substantive_transcript("I want two")
    assert is_substantive_transcript("hello there")
    # Barge finals allow shorter.
    assert is_substantive_transcript("haan", after_barge=True)
    assert not is_substantive_transcript("ok", after_barge=False)


@pytest.mark.asyncio
async def test_listen_coalesce_delays_then_launches(monkeypatch):
    launched: list[str] = []
    loop = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    monkeypatch.setattr(
        "server.services.pstn_voice_core.PSTN_LISTEN_COALESCE_S",
        0.05,
    )
    monkeypatch.setattr(
        "server.services.pstn_voice_core.PSTN_LISTEN_COALESCE_PARTIAL_GRACE_S",
        0.0,
    )
    loop._launch_turn = lambda text: launched.append(text)  # type: ignore[method-assign]
    from server.services.pstn_voice_core import PHASE_LISTENING

    loop._phase = PHASE_LISTENING
    loop._arm_listen_coalesce("I need a plot near the lake")
    assert launched == []
    assert loop._coalesce_transcript is not None
    # Continuation resets timer with newer text.
    loop._arm_listen_coalesce("I need a plot near the lake please book it")
    await asyncio.sleep(0.12)
    assert launched == ["I need a plot near the lake please book it"]
    assert loop._coalesce_transcript is None


@pytest.mark.asyncio
async def test_think_cancel_merges_inflight_transcript():
    loop = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    from server.services.pstn_voice_core import PHASE_THINKING

    loop._phase = PHASE_THINKING
    loop._current_turn_transcript = "Yeah yeah"
    await loop._think_cancel("I like it please book a visit")
    assert loop._pending_transcript
    assert "Yeah yeah" in loop._pending_transcript
    assert "like it" in loop._pending_transcript.lower()


@pytest.mark.asyncio
async def test_listen_coalesce_drops_thin_final():
    launched: list[str] = []
    loop = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    loop._launch_turn = lambda text: launched.append(text)  # type: ignore[method-assign]
    loop._arm_listen_coalesce("ok")
    assert loop._coalesce_task is None
    assert launched == []
