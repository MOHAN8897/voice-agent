from server.agent.conversation_manager import ConversationManager
from server.services.echo_guard import is_likely_echo
from server.services.pstn_voice_core import PstnVoiceLoop


def test_echo_matches_agent_words():
    assert is_likely_echo("how can I help you", "Hi, this is Priya. How can I help you?")


def test_echo_ignores_real_question():
    assert not is_likely_echo("what is the plot size", "Hi, this is Priya from Acme.")


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


def test_pstn_barge_commit_requires_three_words_and_hold(monkeypatch):
    loop = PstnVoiceLoop(session_id="s", call_id=None, on_agent_wire=lambda _: None)
    monkeypatch.setattr("server.services.pstn_voice_core.ENABLE_PSTN_BARGE_IN", True)
    loop._agent_speaking = True
    loop._tts_started_at = 0.0
    assert loop._should_commit_barge("haan ok") is False
    # First 3-word partial only starts the hold clock.
    loop._tts_started_at = 1.0
    import time

    monkeypatch.setattr(time, "monotonic", lambda: 10.0)
    loop._tts_started_at = 1.0
    assert loop._should_commit_barge("I want two plants please") is False
    monkeypatch.setattr(time, "monotonic", lambda: 10.25)
    assert loop._should_commit_barge("I want two plants please") is True
